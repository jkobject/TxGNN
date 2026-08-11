from pathlib import Path

import pandas as pd

from manage_db.build_staged_disease_tissue_context import (
    COMORBIDITY_RELATION,
    DISEASE_TISSUE_RELATION,
    HPA_CANCER_MAPPINGS,
    PHENOTYPE_TISSUE_RELATION,
    SOURCE_AUDIT_COLUMNS,
    audit_non_edge_sources,
    build_hpa_disease_tissue,
    validate_outputs,
    parse_args,
)


def _synthetic_hpa_frame() -> pd.DataFrame:
    columns = {"Gene": ["GENE1", "GENE2"]}
    for mapping in HPA_CANCER_MAPPINGS:
        columns[f"Cancer prognostics - {mapping.hpa_label} (TCGA)"] = ["unprognostic (1.0e-1)", "favourable prognostic (1.0e-3)"]
    return pd.DataFrame(columns)


def test_hpa_cancer_context_builder_stages_only_explicitly_mapped_edges() -> None:
    hpa = _synthetic_hpa_frame()
    disease_ids = {mapping.disease_id for mapping in HPA_CANCER_MAPPINGS if mapping.disease_id}
    tissue_ids = {mapping.tissue_id for mapping in HPA_CANCER_MAPPINGS if mapping.tissue_id}

    edges, evidence, rejected, audit_rows = build_hpa_disease_tissue(
        hpa,
        release="HPA test",
        disease_ids=disease_ids,
        tissue_ids=tissue_ids,
    )

    accepted = [mapping for mapping in HPA_CANCER_MAPPINGS if mapping.accepted]
    rejected_mappings = [mapping for mapping in HPA_CANCER_MAPPINGS if not mapping.accepted]
    assert len(edges) == len(accepted)
    assert set(edges["relation"]) == {DISEASE_TISSUE_RELATION}
    assert set(edges["x_type"]) == {"disease"}
    assert set(edges["y_type"]) == {"tissue"}
    assert len(rejected) == len(rejected_mappings)
    assert {"composite", "multiple anatomical sites"} <= set(
        " ".join(rejected["reject_reason"].astype(str)).split("; ")
    ) or all(rejected["reject_reason"].astype(str).str.len() > 0)
    edge_keys = set(edges["relation"] + "|" + edges["x_id"] + "|" + edges["y_id"])
    evidence_keys = set(evidence["relation"] + "|" + evidence["x_id"] + "|" + evidence["y_id"])
    assert edge_keys <= evidence_keys
    assert len(audit_rows) == len(HPA_CANCER_MAPPINGS)


def test_source_audit_blocks_phenotype_tissue_and_comorbidity_without_direct_source(tmp_path: Path) -> None:
    hp = tmp_path / "hp.obo"
    hp.write_text("[Term]\nid: HP:0000001\nname: All\n[Term]\nid: HP:0000077\nname: Abnormality of the kidney\n", encoding="utf-8")
    hpoa = tmp_path / "phenotype.hpoa"
    hpoa.write_text("#header\ndatabase_id\tdisease_name\tqualifier\thpo_id\treference\tevidence\tonset\tfrequency\tsex\tmodifier\taspect\tbiocuration\nOMIM:1\tDisease\t\tHP:0000077\tPMID:1\tPCS\t\t\t\t\tP\tHPO:test\n", encoding="utf-8")
    uberon = tmp_path / "uberon.obo"
    uberon.write_text("[Term]\nid: UBERON:0002113\nname: kidney\n", encoding="utf-8")

    rows = audit_non_edge_sources(hp, hpoa, uberon, "test")
    audit = pd.DataFrame(rows, columns=SOURCE_AUDIT_COLUMNS)

    phenotype_rows = audit[audit["candidate_relation"] == PHENOTYPE_TISSUE_RELATION]
    assert set(phenotype_rows["decision"]) == {"no_edge", "supporting_mapping_only"}
    assert any("disease->phenotype" in reason for reason in phenotype_rows["reason"])
    comorbidity_rows = audit[audit["candidate_relation"] == COMORBIDITY_RELATION]
    assert len(comorbidity_rows) == 1
    assert comorbidity_rows.iloc[0]["decision"] == "no_edge"


def test_validation_requires_endpoint_and_evidence_support() -> None:
    hpa = _synthetic_hpa_frame()
    disease_ids = {mapping.disease_id for mapping in HPA_CANCER_MAPPINGS if mapping.disease_id}
    tissue_ids = {mapping.tissue_id for mapping in HPA_CANCER_MAPPINGS if mapping.tissue_id}
    edges, evidence, rejected, audit_rows = build_hpa_disease_tissue(
        hpa,
        release="HPA test",
        disease_ids=disease_ids,
        tissue_ids=tissue_ids,
    )
    audit_rows.extend(
        [
            {"source": "HPO", "source_dataset": "hp.obo", "source_url": "", "candidate_relation": PHENOTYPE_TISSUE_RELATION, "decision": "no_edge", "reason": "no direct source", "rows_or_terms_checked": 1, "release": "", "notes": ""},
            {"source": "EHR", "source_dataset": "none", "source_url": "", "candidate_relation": COMORBIDITY_RELATION, "decision": "no_edge", "reason": "no clean source", "rows_or_terms_checked": 0, "release": "", "notes": ""},
        ]
    )
    source_audit = pd.DataFrame(audit_rows, columns=SOURCE_AUDIT_COLUMNS)

    validation = validate_outputs(edges, evidence, disease_ids, tissue_ids, source_audit, rejected)

    assert validation["ok"] is True
    assert validation["checks"]["endpoint_antijoin"]["ok"] is True
    assert validation["checks"]["evidence_support"]["ok"] is True
    assert validation["checks"]["no_forbidden_phenotype_anatomy_inference"]["ok"] is True


def test_default_download_cache_is_pipeline_local() -> None:
    args = parse_args([])

    assert args.cache_dir == "artifacts/cache/disease-tissue-context"
    assert args.node_root == "data/kg/nodes"
    assert "main/raw" not in args.cache_dir
