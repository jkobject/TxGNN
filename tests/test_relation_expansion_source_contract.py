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


def test_current_raw_availability_requires_immutable_object_identity() -> None:
    required = {"uri", "generation", "crc32c_base64", "size"}
    for relation, row in _rows().items():
        if "current-raw-available" not in row["availability_statuses"]:
            continue
        assert row["raw_objects"], relation
        assert any(required <= set(obj) for obj in row["raw_objects"]), relation


def test_cell_ontology_source_is_refetch_required_and_uberon_is_not_cl() -> None:
    for relation in ["cell_type_found_in_tissue", "cell_type_subtype_of_cell_type"]:
        row = _rows()[relation]
        text = json.dumps(row)
        assert "current-raw-available" not in row["availability_statuses"]
        assert "remote-refetch-required" in row["availability_statuses"]
        assert "releases/2026-06-08" in text
        assert "CL OBO" in text
    tissue = _rows()["cell_type_found_in_tissue"]
    assert tissue["raw_objects"][0]["role"] == "endpoint vocabulary only; not the CL assertion source"


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


def test_molecule_gap_contract_is_now_release_pinned_but_remains_review_gated() -> None:
    expected_predicates = {
        "molecule_associated_phenotype": ["side effect"],
        "molecule_contraindicates_disease": ["contraindication"],
        "molecule_parent_of_molecule": ["parent of"],
        "molecule_synergizes_molecule": ["synergizes with"],
        "molecule_treats_disease": ["indication", "off-label use", "linked to"],
    }
    for relation, predicates in expected_predicates.items():
        row = _rows()[relation]
        assert row["availability_statuses"] == ["remote-refetch-required"]
        assert row["release_version"] == "TxGNN/DeepPurpose Dataverse v6.0, published 2023-06-07"
        assert row["raw_objects"][0]["dataverse_file_id"] == "7144484"
        assert row["raw_objects"][0]["md5"] == "aac8191d4fbc5bf09cdf8c3c78b4e75f"
        assert row["source_predicates"] == predicates
        assert row["builder_status"] == "immutable task-scoped builder present; full parity remains review-required"
        assert "independent review" in row["missing_artifacts"]