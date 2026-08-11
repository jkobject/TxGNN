import csv
import zipfile
from pathlib import Path

import pandas as pd

from manage_db.build_hpa_cellular_components import build_artifacts


def _write_hpa_zip(path: Path) -> None:
    fields = [
        "Gene",
        "Ensembl",
        "Uniprot",
        "HPA evidence",
        "Reliability (IF)",
        "Reliability (IH)",
        "Subcellular location",
        "Subcellular main location",
        "Subcellular additional location",
        "Secretome location",
    ]
    rows = [
        {
            "Gene": "GENE1",
            "Ensembl": "ENSG000001",
            "Uniprot": "P11111",
            "HPA evidence": "Evidence at protein level",
            "Reliability (IF)": "Enhanced",
            "Reliability (IH)": "Approved",
            "Subcellular location": "Nucleoplasm,Annulus",
            "Subcellular main location": "Nucleoplasm",
            "Subcellular additional location": "Annulus",
            "Secretome location": "Secreted to blood",
        },
        {
            "Gene": "GENE2",
            "Ensembl": "ENSG000002",
            "Uniprot": "P22222",
            "HPA evidence": "Evidence at transcript level",
            "Reliability (IF)": "Approved",
            "Reliability (IH)": "Approved",
            "Subcellular location": "Cytosol",
            "Subcellular main location": "Cytosol",
            "Subcellular additional location": "",
            "Secretome location": "",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        with zf.open("proteinatlas.tsv", "w") as fh:
            wrapper = fh
            text = "\t".join(fields) + "\n"
            wrapper.write(text.encode())
            for row in rows:
                wrapper.write(("\t".join(row.get(field, "") for field in fields) + "\n").encode())


def test_build_hpa_cellular_component_stage_preserves_mapping_and_evidence(tmp_path: Path) -> None:
    hpa_zip = tmp_path / "proteinatlas.tsv.zip"
    _write_hpa_zip(hpa_zip)
    protein_nodes = tmp_path / "protein.parquet"
    pd.DataFrame(
        [
            {"id": "ENSP000001", "uniprot_id": "P11111"},
            {"id": "ENSP000002", "uniprot_id": "P22222"},
        ]
    ).to_parquet(protein_nodes, index=False)

    out = tmp_path / "stage"
    manifest = build_artifacts(
        hpa_zip=hpa_zip,
        protein_nodes=protein_nodes,
        output_dir=out,
        hpa_release="HPA test",
        created_at="2026-06-22",
    )

    nodes = pd.read_parquet(out / "nodes" / "cellular_component.parquet")
    edges = pd.read_parquet(out / "edges" / "protein_located_in_cellular_component.parquet")
    evidence = pd.read_parquet(out / "evidence" / "protein_located_in_cellular_component.parquet")

    assert "GO:0005654" in set(nodes["id"])  # Nucleoplasm
    assert "GO:0005829" in set(nodes["id"])  # Cytosol
    assert "HPA_SL:annulus" in set(nodes["id"])
    assert "HPA_SL:secreted_to_blood" in set(nodes["id"])
    assert set(edges["x_type"]) == {"protein"}
    assert set(edges["y_type"]) == {"cellular_component"}
    assert set(evidence["edge_key"]).issuperset(
        {f"protein_located_in_cellular_component|{row.x_id}|{row.y_id}" for row in edges.itertuples()}
    )
    assert manifest["validation"]["checks"]["evidence_support"]["edges_without_evidence"] == 0
    assert manifest["validation"]["counts"]["hpa_local_nodes"] >= 2
    annulus = nodes[nodes["id"].eq("HPA_SL:annulus")].iloc[0]
    assert annulus["mapping_method"] == "hpa_local_fallback"
    assert "No gene-to-protein projection" not in manifest["source_policy"]
    assert "no gene-to-protein projection" in manifest["source_policy"]


def _write_go_obo(path: Path) -> None:
    path.write_text(
        """
data-version: releases/2026-06-22

[Term]
id: GO:0005654
name: nucleoplasm
namespace: cellular_component

[Term]
id: GO:0005829
name: cytosol
namespace: cellular_component

[Term]
id: GO:0005634
name: nucleus
namespace: cellular_component

[Term]
id: GO:0060107
name: annulus
namespace: cellular_component

[Term]
id: GO:0030692
name: Noc4p-Nop14p complex
namespace: cellular_component

[Term]
id: GO:0005708
name: obsolete mitotic chromosome
namespace: cellular_component
is_obsolete: true

[Term]
id: GO:0097224
name: obsolete sperm connecting piece
namespace: cellular_component
is_obsolete: true

[Term]
id: GO:0110165
name: cellular anatomical entity
namespace: cellular_component

[Term]
id: GO:0097225
name: sperm midpiece
namespace: cellular_component

[Term]
id: GO:0097228
name: sperm principal piece
namespace: cellular_component
""".lstrip()
    )


def test_review_blocker_labels_are_demoted_and_broad_hierarchy_edges_are_dropped(tmp_path: Path) -> None:
    fields = [
        "Gene",
        "Ensembl",
        "Uniprot",
        "HPA evidence",
        "Reliability (IF)",
        "Reliability (IH)",
        "Subcellular location",
        "Subcellular main location",
        "Subcellular additional location",
        "Secretome location",
    ]
    row = {
        "Gene": "GENE1",
        "Ensembl": "ENSG000001",
        "Uniprot": "P11111",
        "HPA evidence": "Evidence at protein level",
        "Reliability (IF)": "Enhanced",
        "Reliability (IH)": "Approved",
        "Subcellular location": "Nucleoli rim,Mitotic chromosome,Rods & Rings,Annulus,Connecting piece,Mid piece,Principal piece",
        "Subcellular main location": "Nucleoli rim,Mitotic chromosome,Rods & Rings",
        "Subcellular additional location": "Annulus,Connecting piece,Mid piece,Principal piece",
        "Secretome location": "",
    }
    hpa_zip = tmp_path / "proteinatlas.tsv.zip"
    with zipfile.ZipFile(hpa_zip, "w") as zf:
        with zf.open("proteinatlas.tsv", "w") as fh:
            fh.write(("\t".join(fields) + "\n").encode())
            fh.write(("\t".join(row.get(field, "") for field in fields) + "\n").encode())
    protein_nodes = tmp_path / "protein.parquet"
    pd.DataFrame([{"id": "ENSP000001", "uniprot_id": "P11111"}]).to_parquet(protein_nodes, index=False)
    go_obo = tmp_path / "go.obo"
    _write_go_obo(go_obo)

    out = tmp_path / "stage"
    manifest = build_artifacts(
        hpa_zip=hpa_zip,
        protein_nodes=protein_nodes,
        output_dir=out,
        go_obo=go_obo,
        hpa_release="HPA test",
        created_at="2026-06-22",
    )

    nodes = pd.read_parquet(out / "nodes" / "cellular_component.parquet")
    hierarchy = pd.read_parquet(out / "edges" / "cellular_component_subtype_of_cellular_component.parquet")
    hierarchy_evidence = pd.read_parquet(out / "evidence" / "cellular_component_subtype_of_cellular_component.parquet")

    blocked_go_ids = {"GO:0030692", "GO:0005708", "GO:0097224", "GO:0110165", "GO:0060107"}
    assert blocked_go_ids.isdisjoint(set(nodes["id"]))
    assert "HPA_SL:nucleoli_rim" in set(nodes["id"])
    assert "HPA_SL:mitotic_chromosome" in set(nodes["id"])
    assert "HPA_SL:rods_rings" in set(nodes["id"])
    assert "HPA_SL:annulus" in set(nodes["id"])
    assert "HPA_SL:connecting_piece" in set(nodes["id"])
    assert not nodes["name"].astype(str).str.lower().str.startswith("obsolete").any()
    assert "broad_sperm_flagellum_context" not in set(hierarchy_evidence["predicate"].astype(str))
    assert not (
        hierarchy["y_id"].astype(str).eq("GO:0072372")
        | hierarchy["y_id"].astype(str).eq("HPA_SL:primary_cilium")
    ).any()
    assert manifest["validation"]["checks"]["go_term_semantics"]["invalid_go_nodes"] == 0
    assert manifest["validation"]["checks"]["hierarchy_semantics"]["broad_context_edges"] == 0


def test_validation_rejects_obsolete_manual_go_override(tmp_path: Path, monkeypatch) -> None:
    import manage_db.build_hpa_cellular_components as hpa

    hpa_zip = tmp_path / "proteinatlas.tsv.zip"
    _write_hpa_zip(hpa_zip)
    protein_nodes = tmp_path / "protein.parquet"
    pd.DataFrame([{"id": "ENSP000001", "uniprot_id": "P11111"}]).to_parquet(protein_nodes, index=False)
    go_obo = tmp_path / "go.obo"
    _write_go_obo(go_obo)
    monkeypatch.setitem(hpa.HPA_LABEL_OVERRIDES, "Annulus", {"go_id": "GO:0005708", "confidence": "exact_manual", "category": "sperm_structure"})

    try:
        hpa.build_artifacts(
            hpa_zip=hpa_zip,
            protein_nodes=protein_nodes,
            output_dir=tmp_path / "stage",
            go_obo=go_obo,
            hpa_release="HPA test",
            created_at="2026-06-22",
        )
    except ValueError as exc:
        assert "go term semantic validation failed" in str(exc)
    else:
        raise AssertionError("obsolete manual GO override was not rejected")


def test_validation_rejects_reviewed_wrong_manual_go_override(tmp_path: Path, monkeypatch) -> None:
    import manage_db.build_hpa_cellular_components as hpa

    hpa_zip = tmp_path / "proteinatlas.tsv.zip"
    _write_hpa_zip(hpa_zip)
    protein_nodes = tmp_path / "protein.parquet"
    pd.DataFrame([{"id": "ENSP000001", "uniprot_id": "P11111"}]).to_parquet(protein_nodes, index=False)
    go_obo = tmp_path / "go.obo"
    _write_go_obo(go_obo)
    monkeypatch.setitem(hpa.HPA_LABEL_OVERRIDES, "Annulus", {"go_id": "GO:0030692", "confidence": "exact_manual", "category": "sperm_structure"})

    try:
        hpa.build_artifacts(
            hpa_zip=hpa_zip,
            protein_nodes=protein_nodes,
            output_dir=tmp_path / "stage",
            go_obo=go_obo,
            hpa_release="HPA test",
            created_at="2026-06-22",
        )
    except ValueError as exc:
        assert "go term semantic validation failed" in str(exc)
        assert "rejected_hpa_go_mapping" in str(exc)
    else:
        raise AssertionError("known wrong manual GO override was not rejected")


def test_uniprot_ensp_ambiguity_audit_counts_source_rows_and_expanded_edges(tmp_path: Path) -> None:
    hpa_zip = tmp_path / "proteinatlas.tsv.zip"
    _write_hpa_zip(hpa_zip)
    protein_nodes = tmp_path / "protein.parquet"
    pd.DataFrame(
        [
            {"id": "ENSP000001", "uniprot_id": "P11111"},
            {"id": "ENSP000001-2", "uniprot_id": "P11111"},
            {"id": "ENSP000002", "uniprot_id": "P22222"},
        ]
    ).to_parquet(protein_nodes, index=False)

    manifest = build_artifacts(
        hpa_zip=hpa_zip,
        protein_nodes=protein_nodes,
        output_dir=tmp_path / "stage",
        hpa_release="HPA test",
        created_at="2026-06-22",
    )

    audit = manifest["validation"]["protein_mapping"]["hpa_uniprot_expansion_audit"]
    assert audit["ambiguous_hpa_source_rows"] == 1
    assert audit["ambiguous_hpa_label_assignments"] == 5
    assert audit["ambiguous_hpa_expanded_protein_rows"] == 10
    assert audit["ambiguous_hpa_distinct_protein_component_edges"] == 6
    assert "all ENSP" in audit["current_policy"]
    assert "canonical ENSP" in audit["promotion_recommendation"]


def test_default_download_inputs_use_pipeline_local_cache() -> None:
    import manage_db.build_hpa_cellular_components as hpa

    args = hpa.build_parser().parse_args([])

    assert args.hpa_zip == "artifacts/cache/hpa-cellular-components/hpa/proteinatlas.tsv.zip"
    assert args.go_obo == "artifacts/cache/hpa-cellular-components/go/go-basic.obo"
    assert args.uniprot_subcell == "artifacts/cache/hpa-cellular-components/uniprot/subcell.txt"
    assert "main/raw" not in " ".join([args.hpa_zip, args.go_obo, args.uniprot_subcell])
