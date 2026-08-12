import json
import subprocess
import sys
from pathlib import Path

from scripts.build_relation_expansion_source_contract import (
    AVAILABILITY_STATUSES,
    CONTRACT_RELATIONS,
    EXPRESSION_RELATIONS,
    NONCANONICAL_RELATIONS,
    PROVENANCE_GAPS,
    build_contract,
)

ROOT = Path(__file__).resolve().parents[1]
JSON_CONTRACT = ROOT / "docs/relation-expansion-source-contract.json"
MARKDOWN_CONTRACT = ROOT / "docs/relation-expansion-source-contract.md"


def _rows() -> dict[str, dict]:
    return {row["relation"]: row for row in build_contract()["relations"]}


def test_contract_is_deterministic_and_covers_every_requested_relation() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_relation_expansion_source_contract.py", "--check"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(JSON_CONTRACT.read_text()) == build_contract()
    assert len(CONTRACT_RELATIONS) == 33
    assert set(_rows()) == CONTRACT_RELATIONS
    assert len(NONCANONICAL_RELATIONS) == 24
    assert PROVENANCE_GAPS <= set(_rows())


def test_every_row_has_closed_source_mapping_execution_fields() -> None:
    required = {
        "preferred_sources", "availability_statuses", "release_version",
        "license_access", "raw_objects", "historical_identity",
        "builder_status", "assertion_policy", "mapping_rejection_policy",
        "evidence_fields", "execution_placement", "next_rebuild_card",
        "missing_artifacts",
    }
    for relation, row in _rows().items():
        assert required <= set(row), relation
        assert row["preferred_sources"], relation
        assert row["availability_statuses"], relation
        assert set(row["availability_statuses"]) <= AVAILABILITY_STATUSES
        for field in required - {"raw_objects", "missing_artifacts"}:
            assert row[field], f"{relation}: {field}"


def test_remap_is_not_mislabeled_completed_by_crm_sidecar() -> None:
    remap = _rows()["tf_binds_enhancer"]
    text = json.dumps(remap).lower()
    assert "1,224,536" in text and "6,356,561" in text
    assert "not final topology" in text
    assert "current-raw-available" not in remap["availability_statuses"]


def test_prism_deleted_work_is_preserved_but_never_current() -> None:
    prism = _rows()["cell_line_responds_to_molecule"]
    assert "historical-artifact-deleted" in prism["availability_statuses"]
    assert "current-raw-available" not in prism["availability_statuses"]
    assert [obj["figshare_file_id"] for obj in prism["raw_objects"]] == [
        "36794595", "36794610", "36794613", "36794616", "36794619"
    ]
    assert all(len(obj["md5"]) == 32 for obj in prism["raw_objects"])
    text = json.dumps(prism)
    assert "3d65b66e15df03abb8c08e08de6e127134d31bcc" in text
    assert "31,349" in text and "31,952" in text
    assert "names prohibited" in text
    assert "historical GCS staging is not restorable" in text
    recovery = build_contract()["policies"]["gcs_recovery"]
    assert "2678400s" in recovery
    assert "2026-08-12T09:27:50.492Z" in recovery
    assert "not retroactive" in recovery
    assert "matched no objects" in recovery


def test_organism_has_gene_forbids_fabricated_row_evidence() -> None:
    row = _rows()["organism_has_gene"]
    assert row["availability_statuses"] == ["accepted-no-row-evidence"]
    assert "no row-level evidence" in row["assertion_policy"]
    assert "no fabricated evidence parquet" in row["execution_placement"]


def test_expression_contract_requires_numeric_context_quantiles() -> None:
    for relation in EXPRESSION_RELATIONS:
        row = _rows()[relation]
        text = json.dumps(row).lower()
        for token in ["retain every existing edge", "non-zero", "numeric_expression", "low|medium|high", "q_low_cutoff", "q_high_cutoff", "never pool incomparable modalities"]:
            assert token in text, (relation, token)


def test_tf_regulates_gene_is_derived_only() -> None:
    row = _rows()["tf_regulates_gene"]
    text = json.dumps(row).lower()
    assert "not an observed direct relation" in text
    assert "tf_binds_enhancer" in text
    assert "enhancer_regulates_gene" in text
    assert "edges_inferred/evidence_inferred" in text


def test_markdown_partner_links_machine_contract() -> None:
    text = MARKDOWN_CONTRACT.read_text()
    assert "relation-expansion-source-contract.json" in text
    assert "no data or canonical write authorization" in text