from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from manage_db import remap_crm_support_reader as reader


def _write_fixture(root: Path) -> None:
    sidecar = root / "features" / "remap_crm_tf_enhancer_support.parquet"
    nodes = root / "nodes"
    sidecar.parent.mkdir(parents=True)
    nodes.mkdir(parents=True)
    frames: list[pd.DataFrame] = []

    frames.append(pd.DataFrame(
        [
            {
                "feature_table": "remap_crm_tf_enhancer_support",
                "support_entity_type": "tf",
                "tf_gene_id": "NCBI:1",
                "tf_symbol_sample": "A1BG",
                "enhancer_id": None,
                "enhancer_chromosome": None,
                "enhancer_start": None,
                "enhancer_end": None,
                "support_entity_id": "NCBI:1",
                "support_entity_label": "A1BG",
                "crm_support_rows": 7,
                "crm_interval_count": 3,
                "evidence_type": "crm_aggregated_support",
                "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
                "relation_under_review": "tf_binds_enhancer",
                "support_scope": "full_unbounded_all_chromosomes_crm",
                "source": "ReMap",
                "source_release": "2022",
                "source_url": "https://remap.univ-amu.fr/",
                "genome_build": "GRCh38/hg38",
                "liftover_performed": False,
                "aggregation_policy": "fixture",
                "provenance_caveat": "fixture",
                "source_task_id": "t_5968ce32",
                "promotion_task_id": "t_f2a2952e",
                "source_report": "fixture",
                "readiness_decision_doc": "fixture",
            },
            {
                "feature_table": "remap_crm_tf_enhancer_support",
                "support_entity_type": "enhancer",
                "tf_gene_id": None,
                "tf_symbol_sample": "A1BG",
                "enhancer_id": "EH:chr1:100-200",
                "enhancer_chromosome": "chr1",
                "enhancer_start": 100,
                "enhancer_end": 200,
                "support_entity_id": "EH:chr1:100-200",
                "support_entity_label": "chr1:100-200",
                "crm_support_rows": 5,
                "crm_interval_count": 2,
                "evidence_type": "crm_aggregated_support",
                "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
                "relation_under_review": "tf_binds_enhancer",
                "support_scope": "full_unbounded_all_chromosomes_crm",
                "source": "ReMap",
                "source_release": "2022",
                "source_url": "https://remap.univ-amu.fr/",
                "genome_build": "GRCh38/hg38",
                "liftover_performed": False,
                "aggregation_policy": "fixture",
                "provenance_caveat": "fixture",
                "source_task_id": "t_5968ce32",
                "promotion_task_id": "t_f2a2952e",
                "source_report": "fixture",
                "readiness_decision_doc": "fixture",
            },
            {
                "feature_table": "remap_crm_tf_enhancer_support",
                "support_entity_type": "enhancer",
                "tf_gene_id": None,
                "tf_symbol_sample": "GATA1",
                "enhancer_id": "EH:chr1:300-400",
                "enhancer_chromosome": "chr1",
                "enhancer_start": 300,
                "enhancer_end": 400,
                "support_entity_id": "EH:chr1:300-400",
                "support_entity_label": "chr1:300-400",
                "crm_support_rows": 2,
                "crm_interval_count": 1,
                "evidence_type": "crm_aggregated_support",
                "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
                "relation_under_review": "tf_binds_enhancer",
                "support_scope": "full_unbounded_all_chromosomes_crm",
                "source": "ReMap",
                "source_release": "2022",
                "source_url": "https://remap.univ-amu.fr/",
                "genome_build": "GRCh38/hg38",
                "liftover_performed": False,
                "aggregation_policy": "fixture",
                "provenance_caveat": "fixture",
                "source_task_id": "t_5968ce32",
                "promotion_task_id": "t_f2a2952e",
                "source_report": "fixture",
                "readiness_decision_doc": "fixture",
            },
        ],
        columns=reader.SUMMARY_COLUMNS,
    ))

    frames.append(pd.DataFrame(
        [
            {
                "feature_table": "remap_crm_tf_enhancer_support",
                "support_entity_type": "tf",
                "tf_gene_id": "NCBI:2",
                "tf_symbol_sample": "A2M",
                "enhancer_id": None,
                "enhancer_chromosome": None,
                "enhancer_start": None,
                "enhancer_end": None,
                "support_entity_id": "NCBI:2",
                "support_entity_label": "A2M",
                "crm_support_rows": 1,
                "crm_interval_count": 1,
                "evidence_type": "crm_aggregated_support",
                "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
                "relation_under_review": "tf_binds_enhancer",
                "support_scope": "full_unbounded_all_chromosomes_crm",
                "source": "ReMap",
                "source_release": "2022",
                "source_url": "https://remap.univ-amu.fr/",
                "genome_build": "GRCh38/hg38",
                "liftover_performed": False,
                "aggregation_policy": "fixture",
                "provenance_caveat": "fixture",
                "source_task_id": "t_5968ce32",
                "promotion_task_id": "t_f2a2952e",
                "source_report": "fixture",
                "readiness_decision_doc": "fixture",
            }
        ],
        columns=reader.SUMMARY_COLUMNS,
    ))

    frames.append(pd.DataFrame(
        [
            {
                "feature_table": "remap_crm_tf_enhancer_support",
                "support_entity_type": "tf",
                "tf_gene_id": "NCBI:1",
                "tf_symbol_sample": "A1BG",
                "enhancer_id": None,
                "enhancer_chromosome": None,
                "enhancer_start": None,
                "enhancer_end": None,
                "support_entity_id": "NCBI:1",
                "support_entity_label": "A1BG",
                "crm_support_rows": 12,
                "crm_interval_count": 5,
                "evidence_type": "crm_aggregated_support",
                "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
                "relation_under_review": "tf_binds_enhancer",
                "support_scope": "full_unbounded_all_chromosomes_crm",
                "source": "ReMap",
                "source_release": "2022",
                "source_url": "https://remap.univ-amu.fr/",
                "genome_build": "GRCh38/hg38",
                "liftover_performed": False,
                "aggregation_policy": "fixture",
                "provenance_caveat": "fixture",
                "source_task_id": "t_5968ce32",
                "promotion_task_id": "t_f2a2952e",
                "source_report": "fixture",
                "readiness_decision_doc": "fixture",
            },
            {
                "feature_table": "remap_crm_tf_enhancer_support",
                "support_entity_type": "tf",
                "tf_gene_id": "NCBI:2",
                "tf_symbol_sample": "A2M",
                "enhancer_id": None,
                "enhancer_chromosome": None,
                "enhancer_start": None,
                "enhancer_end": None,
                "support_entity_id": "NCBI:2",
                "support_entity_label": "A2M",
                "crm_support_rows": 1,
                "crm_interval_count": 1,
                "evidence_type": "crm_aggregated_support",
                "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
                "relation_under_review": "tf_binds_enhancer",
                "support_scope": "full_unbounded_all_chromosomes_crm",
                "source": "ReMap",
                "source_release": "2022",
                "source_url": "https://remap.univ-amu.fr/",
                "genome_build": "GRCh38/hg38",
                "liftover_performed": False,
                "aggregation_policy": "fixture",
                "provenance_caveat": "fixture",
                "source_task_id": "t_5968ce32",
                "promotion_task_id": "t_f2a2952e",
                "source_report": "fixture",
                "readiness_decision_doc": "fixture",
            },
        ],
        columns=reader.TF_GLOBAL_COLUMNS,
    ))
    frames[0].loc[frames[0]["support_entity_type"] == "tf", "enhancer_chromosome"] = "chr1"
    frames[1].loc[frames[1]["support_entity_type"] == "tf", "enhancer_chromosome"] = "chrX"
    pd.concat(frames, ignore_index=True).to_parquet(sidecar, index=False)

    pd.DataFrame([{"id": "NCBI:1"}, {"id": "NCBI:2"}]).to_parquet(nodes / "gene.parquet", index=False)
    pd.DataFrame([{"id": "EH:chr1:100-200"}, {"id": "EH:chr1:300-400"}]).to_parquet(
        nodes / "enhancer.parquet", index=False
    )


def test_list_chromosomes_orders_available_shards(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    assert reader.list_chromosomes(prefix=prefix) == ["1", "X"]


def test_read_chromosome_filters_by_tf_symbol_and_enhancer(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    by_tf = reader.read_chromosome_support(
        "chr1",
        prefix=prefix,
        tf_symbol="A1BG",
        columns=["support_entity_type", "tf_symbol_sample", "enhancer_id"],
    )
    assert len(by_tf) == 2
    assert set(by_tf["support_entity_type"]) == {"tf", "enhancer"}

    by_enhancer = reader.read_chromosome_support(
        "1",
        prefix=prefix,
        enhancer_id="EH:chr1:100-200",
        columns=["enhancer_id", "support_semantics", "relation_under_review"],
    )
    assert by_enhancer.to_dict(orient="records") == [
        {
            "enhancer_id": "EH:chr1:100-200",
            "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
            "relation_under_review": "tf_binds_enhancer",
        }
    ]


def test_read_tf_global_summary_filter(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    result = reader.read_tf_global_summary(prefix=prefix, tf_gene_id="NCBI:2")

    assert list(result["tf_symbol_sample"]) == ["A2M", "A2M"]
    assert set(result["promotion_task_id"]) == {"t_f2a2952e"}


def test_read_tf_global_summary_tf_gene_filter_keeps_requested_projection(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    result = reader.read_tf_global_summary(
        prefix=prefix,
        tf_gene_id="NCBI:2",
        columns=["tf_symbol_sample"],
        limit=1,
    )

    assert result.to_dict(orient="records") == [{"tf_symbol_sample": "A2M"}]


def test_read_tf_global_summary_tf_symbol_filter_keeps_requested_projection(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    result = reader.read_tf_global_summary(
        prefix=prefix,
        tf_symbol="A1BG",
        columns=["tf_gene_id"],
        limit=1,
    )

    assert result.to_dict(orient="records") == [{"tf_gene_id": "NCBI:1"}]


def test_bounded_endpoint_check_over_loaded_subset(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"
    loaded = reader.read_chromosome_support("1", prefix=prefix, tf_symbol="A1BG")

    result = reader.check_loaded_endpoint_membership(loaded, kg_root=tmp_path)

    assert result["loaded_rows"] == 2
    assert result["tf_gene_ids_checked"] == 1
    assert result["tf_gene_endpoint_antijoin"] == 0
    assert result["enhancer_ids_checked"] == 1
    assert result["enhancer_endpoint_antijoin"] == 0
    assert "not observed binding" in result["semantics"]


def test_cli_list_and_read_json(tmp_path: Path, capsys) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    assert reader.main(["--prefix", str(prefix), "list-chromosomes"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["chromosomes"] == ["1", "X"]

    assert (
        reader.main(
            [
                "--prefix",
                str(prefix),
                "read-chromosome",
                "--chromosome",
                "1",
                "--enhancer-id",
                "EH:chr1:100-200",
                "--columns",
                "enhancer_id,support_semantics",
                "--format",
                "json",
            ]
        )
        == 0
    )
    records = json.loads(capsys.readouterr().out)
    assert records == [
        {
            "enhancer_id": "EH:chr1:100-200",
            "support_semantics": "support_only_compact_crm_aggregate;not_observed_binding;not_graph_edge",
        }
    ]


def test_status_reports_support_only_semantics(tmp_path: Path, capsys) -> None:
    _write_fixture(tmp_path)
    prefix = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    assert reader.main(["--prefix", str(prefix), "status"]) == 0
    status = json.loads(capsys.readouterr().out)

    assert status["source"] == "local_cache"
    assert "support-only feature/QA" in status["semantics"]
    assert "not observed binding" in status["semantics"]


def test_compacted_sidecar_supports_bounded_chromosome_reads(tmp_path: Path) -> None:
    compact = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"
    compact.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {"enhancer_chromosome": "chr1", "tf_symbol_sample": "A1BG", "enhancer_id": "EH:1"},
            {"enhancer_chromosome": "chr2", "tf_symbol_sample": "GATA1", "enhancer_id": "EH:2"},
        ]
    ).to_parquet(compact, index=False)

    result = reader.read_chromosome_support(
        "1",
        prefix=compact,
        columns=["tf_symbol_sample", "enhancer_id"],
        limit=1,
    )

    assert result.to_dict(orient="records") == [{"tf_symbol_sample": "A1BG", "enhancer_id": "EH:1"}]
    assert reader.chromosome_shard_path("1", prefix=compact) == str(compact)


def test_default_sidecar_is_single_direct_gcs_object() -> None:
    assert reader.DEFAULT_GCS_PATH == "gs://jouvencekb/main/features/remap_crm_tf_enhancer_support.parquet"
    assert reader.default_prefix() == reader.DEFAULT_GCS_PATH
    assert "/mnt/gcs/" not in reader.DEFAULT_KG_ROOT


def test_support_queries_reject_explicit_unbounded_reads(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    compact = tmp_path / "features" / "remap_crm_tf_enhancer_support.parquet"

    with pytest.raises(ValueError, match="bounded limit"):
        reader.read_chromosome_support("1", prefix=compact, limit=None)
    with pytest.raises(ValueError, match="bounded limit"):
        reader.read_tf_global_summary(prefix=compact, limit=None)
