import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from manage_db.kg_schema import RELATIONS
from scripts.build_relation_evidence_ledger import (
    DEFAULT_CATALOG,
    PROVENANCE_GAPS,
    build_ledger,
)

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/relation-evidence-ledger.json"
CURRENT_DOCS = [
    ROOT / "TODO.md",
    ROOT / "todo.d/04_relations.md",
    ROOT / "docs/relation_coverage_current.md",
    ROOT / "docs/relation_backlog_prioritized.md",
    ROOT / "docs/kg_schema_overview.md",
]


def test_ledger_matches_schema_and_flat_catalog() -> None:
    ledger = build_ledger()
    summary = ledger["summary"]
    assert summary == json.loads(LEDGER.read_text())["summary"]
    assert len(ledger["relations"]) == 67
    assert len({row["relation"] for row in ledger["relations"]}) == 67
    assert {row["relation"] for row in ledger["relations"]} == {
        relation.name for relation in RELATIONS
    }
    assert summary["canonical_edge_tables"] == 43
    assert summary["canonical_evidence_tables"] == 22
    assert summary["canonical_edges_without_evidence"] == 21
    assert summary["schema_relations_without_canonical_edge"] == 24
    assert summary["evidence_without_edge"] == 0
    assert sum(summary["no_evidence_routes"].values()) == 21
    assert sum(summary["noncanonical_classifications"].values()) == 24


def test_five_provenance_gaps_cannot_disappear_or_be_false_promoted() -> None:
    rows = {row["relation"]: row for row in build_ledger()["relations"]}
    assert PROVENANCE_GAPS == {
        "molecule_associated_phenotype",
        "molecule_contraindicates_disease",
        "molecule_parent_of_molecule",
        "molecule_synergizes_molecule",
        "molecule_treats_disease",
    }
    for relation in PROVENANCE_GAPS:
        assert rows[relation]["provenance_status"] == "provenance-gap"
        assert rows[relation]["accepted_status"] == (
            "canonical-present-provenance-unresolved"
        )
    assert rows["molecule_treats_disease"]["canonical_evidence"] is not None
    assert rows["molecule_treats_disease"]["no_evidence_route"] is None


def test_organism_has_gene_is_structural_without_fabricated_evidence() -> None:
    rows = {row["relation"]: row for row in build_ledger()["relations"]}
    row = rows["organism_has_gene"]
    assert row["canonical_evidence"] is None
    assert row["no_evidence_route"] == "accepted-no-evidence-structural/ontological"
    assert "table-level source/release provenance" in row["next_bounded_action"]
    assert "never fabricate row evidence" in row["next_bounded_action"]


def test_evidence_without_edge_fails_closed(tmp_path: Path) -> None:
    catalog = json.loads(DEFAULT_CATALOG.read_text())
    orphan = next(
        dataset for dataset in catalog["datasets"] if dataset.get("layer") == "evidence"
    ).copy()
    orphan["name"] = "tf_regulates_gene"
    orphan["id"] = "evidence__tf_regulates_gene"
    catalog["datasets"].append(orphan)
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(ValueError, match="evidence without edge"):
        build_ledger(path)


def test_generated_outputs_are_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_relation_evidence_ledger.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_check_rejects_stale_generated_output(tmp_path: Path) -> None:
    json_output = tmp_path / "ledger.json"
    markdown_output = tmp_path / "coverage.md"
    json_output.write_text("{}\n")
    markdown_output.write_text("stale\n")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_relation_evidence_ledger.py",
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "generated output is stale" in (result.stderr + result.stdout)


def test_current_facing_docs_use_flat_layout_and_current_denominators() -> None:
    forbidden = (
        "/Users/jkobject/mnt/gcs/jouvencekb-kg/v2",
        "gs://jouvencekb/kg/v2",
        ".omoc/reports/",
    )
    combined = "\n".join(path.read_text() for path in CURRENT_DOCS)
    assert all(token not in combined for token in forbidden)
    for token in ("43", "22", "21", "24"):
        assert token in combined
    assert "40 canonical" not in combined
    assert "Canonical edge relations present in `v2/edges`: `40`" not in combined
    assert "Canonical edge relations with matching `v2/evidence` file: `18`" not in combined


def test_updated_markdown_links_resolve() -> None:
    paths = CURRENT_DOCS + [ROOT / "docs/README.md"]
    for path in paths:
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("http://", "https://", "#")):
                continue
            local_target = target.split("#", 1)[0]
            assert (path.parent / local_target).exists(), f"{path}: {target}"
