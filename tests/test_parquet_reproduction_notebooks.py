from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import nbformat
from nbclient import NotebookClient

from reproduce.build_parquet_reproduction_registry import STATUSES, build_registry
from reproduce.generate_parquet_reproduction_notebooks import build_notebook, build_readme, validate_registry

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "docs/parquet-catalog/inventory.json"
REGISTRY_PATH = ROOT / "reproduce/parquet_reproduction_lineage.json"
NOTEBOOK_DIR = ROOT / "notebooks/reproduce"
REQUIRED_RECORD_FIELDS = {
    "layer",
    "name",
    "notebook",
    "catalog_page",
    "canonical_uri",
    "meaning",
    "non_meaning",
    "source_family",
    "source_family_label",
    "native_inputs",
    "release",
    "acquisition_and_preconditions",
    "fields",
    "keys",
    "mappings_and_joins",
    "transformations_and_filters",
    "deduplication_and_evidence",
    "quarantines_exclusions_missing",
    "problems_and_decisions",
    "producer_builder",
    "full_worker_rebuild_command",
    "rebuild_command_evidenced",
    "safe_bounded_replay",
    "qc",
    "migration_receipt",
    "reproducibility_status",
    "provenance_gaps",
    "reproducibility_limits",
    "links",
}


def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def identity(row: dict) -> tuple[str, str]:
    return row["layer"], row["name"]


def test_registry_is_exact_deterministic_catalog_denominator() -> None:
    catalog = json.loads(CATALOG_PATH.read_text())
    payload = registry()
    assert payload == build_registry()
    validate_registry(payload)
    expected = {(row["layer"], row["name"]) for row in catalog["datasets"]}
    actual = [identity(row) for row in payload["records"]]
    assert len(actual) == len(set(actual)) == 110
    assert set(actual) == expected
    assert payload["record_count"] == catalog["dataset_count"] == 110


def test_records_are_complete_conservative_and_reconcile_catalog_and_receipts() -> None:
    catalog = {identity(row): row for row in json.loads(CATALOG_PATH.read_text())["datasets"]}
    counts = Counter()
    gaps = []
    for row in registry()["records"]:
        assert REQUIRED_RECORD_FIELDS <= row.keys(), identity(row)
        assert row["reproducibility_status"] in STATUSES
        counts[row["reproducibility_status"]] += 1
        if row["reproducibility_status"] == "provenance-gap":
            gaps.append(identity(row))
            assert row["provenance_gaps"]
        source = catalog[identity(row)]
        assert row["canonical_uri"] == source["uri"]
        assert row["fields"] == source["fields"]
        assert row["keys"] == source["keys"]
        assert row["qc"]["rows"] == source["rows"]
        assert row["qc"]["schema_hash"] == source["schema_hash"]
        assert row["qc"]["generation"] == source["objects"][0]["generation"]
        assert row["migration_receipt"]["verified"] is True
        assert row["migration_receipt"]["destination_generation"] == row["qc"]["generation"]
        if row["reproducibility_status"] == "fully-replayable":
            assert row["native_inputs"] and row["producer_builder"]
            assert row["full_worker_rebuild_command"] and row["rebuild_command_evidenced"]
    assert counts == {
        "documented-not-replayed": 6,
        "historical-builder-only": 94,
        "provenance-gap": 10,
    }
    assert gaps


def test_tracked_links_and_evidenced_builders_exist() -> None:
    for row in registry()["records"]:
        assert (ROOT / row["catalog_page"]).is_file()
        for link in row["links"]:
            if link.startswith(("docs/", "reproduce/", "manage_db/", "tests/")):
                assert (ROOT / link).exists(), (identity(row), link)
        builder = row["producer_builder"]
        if builder is not None:
            assert (ROOT / builder).is_file(), (identity(row), builder)
        command = row["full_worker_rebuild_command"]
        assert row["rebuild_command_evidenced"] is (command is not None)
        if command:
            assert command.startswith("uv run python -m ")
            assert "<task-id>" in command


def test_generated_path_set_and_bytes_are_exact() -> None:
    payload = registry()
    expected_paths = {ROOT / row["notebook"] for row in payload["records"]}
    assert set(NOTEBOOK_DIR.glob("*.ipynb")) == expected_paths
    assert (NOTEBOOK_DIR / "README.md").read_text() == build_readme(payload)
    for row in payload["records"]:
        path = ROOT / row["notebook"]
        assert path.read_text() == nbformat.writes(build_notebook(row)), path
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        assert all(cell.execution_count is None and cell.outputs == [] for cell in notebook.cells if cell.cell_type == "code")


def test_notebooks_have_required_sections_and_no_machine_specific_or_secret_material() -> None:
    required_sections = {
        "Objective and meaning",
        "Native inputs, release, acquisition and environment",
        "Expected schema and identifiers",
        "Keys, mappings and joins",
        "Cleaning, normalization, transformations and filters",
        "Deduplication and assertion/evidence semantics",
        "Quarantines, exclusions and missing data",
        "Problems encountered and decisions",
        "Producer / builder",
        "Full worker rebuild command",
        "Migration receipt",
        "QC, bounded replay and verification",
        "Reproducibility limits",
        "Linked code, tests, reports and historical notebooks",
    }
    forbidden = (
        "/Users/",
        "/home/",
        "/mnt/gcs",
        "jkobject@gmail.com",
        "JOUVENCE_BILLING_PROJECT=",
        "GOOGLE_APPLICATION_CREDENTIALS=",
        "BEGIN PRIVATE KEY",
    )
    for path in NOTEBOOK_DIR.glob("*.ipynb"):
        notebook = nbformat.read(path, as_version=4)
        markdown = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")
        code = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
        assert all(f"## {section}" in markdown for section in required_sections), path
        assert not any(token in markdown or token in code for token in forbidden), path
        assert not re.search(r"(?i)(password|api[_-]?key|secret)\s*=\s*['\"][^'\"]+", code), path
        assert "subprocess" not in code and "os.system" not in code
        assert "JOUVENCE_LIVE_GCS" in code and "requester_pays" in code
        assert "version_aware=True" in code and "pinned_path" in code
        assert "assert " not in code


def test_representative_notebook_from_every_layer_executes_offline(tmp_path: Path) -> None:
    selected = {
        "nodes": "nodes__dataset.ipynb",  # provenance-gap
        "edges": "edges__mutation_in_gene.ipynb",
        "evidence": "evidence__protein_interacts_protein.ipynb",
        "features": "features__molecule_fingerprint.ipynb",  # documented-not-replayed
        "embedding": "embedding__gene_text_sbiobert_snli_multinli_stsb.ipynb",
    }
    for layer, name in selected.items():
        notebook = nbformat.read(NOTEBOOK_DIR / name, as_version=4)
        executed = NotebookClient(
            notebook,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(tmp_path)}},
        ).execute()
        code_cells = [cell for cell in executed.cells if cell.cell_type == "code"]
        assert all(cell.execution_count is not None for cell in code_cells), layer
        assert any(output.get("data", {}).get("text/plain", "").find("SKIPPED") >= 0 for output in code_cells[-1].outputs), layer


def test_generator_check_passes_in_subprocess() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "reproduce/generate_parquet_reproduction_notebooks.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
