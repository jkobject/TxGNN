from __future__ import annotations

import pandas as pd
import pytest

from manage_db.kg_migrate import load_gene_id_map, migrate_edges, migrate_nodes


def test_migrate_nodes_emits_storage_schema_columns() -> None:
    nodes = pd.DataFrame(
        [
            {
                "node_index": 1,
                "node_id": "7157",
                "node_type": "gene/protein",
                "node_name": "TP53",
                "node_source": "NCBI",
            }
        ]
    )

    migrated, index_to_id = migrate_nodes(nodes, gene_id_map={"7157": "ENSG00000141510"})

    assert index_to_id == {1: "ENSG00000141510"}
    row = migrated.iloc[0]
    assert row["id"] == "ENSG00000141510"
    assert row["node_type"] == "gene"
    assert row["ncbi_gene_id"] == "7157"
    assert row["gene_name"] == "TP53"


def test_migrate_nodes_fails_closed_without_authoritative_gene_map() -> None:
    nodes = pd.DataFrame(
        [
            {
                "node_index": 1,
                "node_id": "7157",
                "node_type": "gene/protein",
                "node_name": "TP53",
                "node_source": "NCBI",
            }
        ]
    )

    with pytest.raises(ValueError, match="requires a pinned"):
        migrate_nodes(nodes)


def test_migrate_edges_canonicalizes_bidirectional_txdata_relations() -> None:
    nodes = pd.DataFrame(
        [
            {"node_index": 1, "node_id": "1", "node_type": "drug", "node_name": "D", "node_source": "DrugBank"},
            {"node_index": 2, "node_id": "2", "node_type": "disease", "node_name": "A", "node_source": "MONDO"},
        ]
    )
    migrated_nodes, index_to_id = migrate_nodes(nodes)

    edges = pd.DataFrame(
        [
            {"x_index": 1, "y_index": 2, "relation": "indication", "display_relation": "indication"},
            {"x_index": 2, "y_index": 1, "relation": "drug_disease", "display_relation": "drug disease"},
        ]
    )

    migrated_edges, unmapped = migrate_edges(edges, nodes, index_to_id)

    assert unmapped == []
    assert set(migrated_edges["relation"]) == {"molecule_treats_disease"}
    assert set(migrated_edges["x_type"]) == {"molecule"}
    assert set(migrated_edges["y_type"]) == {"disease"}
    assert set(migrated_edges["x_id"]) == {migrated_nodes[migrated_nodes["node_type"] == "molecule"].iloc[0]["id"]}
    assert set(migrated_edges["y_id"]) == {migrated_nodes[migrated_nodes["node_type"] == "disease"].iloc[0]["id"]}


def test_migrate_edges_uses_parent_predicate_for_exposure_hierarchy() -> None:
    nodes = pd.DataFrame(
        [
            {"node_index": 1, "node_id": "D006539", "node_type": "exposure", "node_name": "parent", "node_source": "CTD"},
            {"node_index": 2, "node_id": "D006540", "node_type": "exposure", "node_name": "child", "node_source": "CTD"},
        ]
    )
    _, index_to_id = migrate_nodes(nodes)
    edges = pd.DataFrame(
        [
            {
                "x_index": 1,
                "y_index": 2,
                "relation": "exposure_exposure",
                "display_relation": "parent of",
            }
        ]
    )

    migrated, unmapped = migrate_edges(edges, nodes, index_to_id)

    assert unmapped == []
    assert migrated["relation"].tolist() == ["molecule_parent_of_molecule"]


def test_load_gene_id_map_whitelists_only_two_accepted_statuses(tmp_path) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame(
        [
            {"ncbi_gene_id": "1", "canonical_ensembl_gene_id": "ENSG000001", "mapping_status": "accepted_1to1"},
            {"ncbi_gene_id": "2", "canonical_ensembl_gene_id": "ENSG000002", "mapping_status": "retired_replaced_1to1"},
            {"ncbi_gene_id": "3", "canonical_ensembl_gene_id": None, "mapping_status": "unmapped"},
        ]
    ).to_csv(path, index=False)

    assert load_gene_id_map(path) == {"1": "ENSG000001", "2": "ENSG000002"}


@pytest.mark.parametrize("status", ["unmapped", "ambiguous_one_to_many", "unexpected_status"])
def test_load_gene_id_map_rejects_nonnull_canonical_id_for_other_status(
    tmp_path, status: str
) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame(
        [{"ncbi_gene_id": "1", "canonical_ensembl_gene_id": "ENSG000001", "mapping_status": status}]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="non-accepted statuses with canonical ENSG IDs"):
        load_gene_id_map(path)


@pytest.mark.parametrize("canonical_id", [None, "ENSG123.4", "ENSGabc", "ENSMUSG123"])
def test_load_gene_id_map_requires_strict_ensg_for_accepted_status(
    tmp_path, canonical_id: str | None
) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame(
        [{"ncbi_gene_id": "1", "canonical_ensembl_gene_id": canonical_id, "mapping_status": "accepted_1to1"}]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="strict ENSG identifiers"):
        load_gene_id_map(path)
