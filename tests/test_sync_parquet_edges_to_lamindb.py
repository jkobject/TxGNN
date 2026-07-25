from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from manage_db import sync_parquet_edges_to_lamindb as live_sync


def _write_edge_fixture(root: Path) -> None:
    (root / "edges").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "x_id": "NCBI:672",
                "x_type": "gene",
                "y_id": "EFO:0000305",
                "y_type": "disease",
                "relation": "disease_associated_gene",
                "display_relation": "associated gene",
                "source": "OpenTargets",
                "credibility": 3,
                "score": 0.88,
            },
            {
                "x_id": "NCBI:672",
                "x_type": "gene",
                "y_id": "MONDO:0019391",
                "y_type": "disease",
                "relation": "disease_associated_gene",
                "display_relation": "associated gene",
                "source": "TxGNN",
                "credibility": 1,
                "score": None,
            },
            {
                "x_id": "NCBI:675",
                "x_type": "gene",
                "y_id": "EFO:0000311",
                "y_type": "disease",
                "relation": "disease_associated_gene",
                "display_relation": "associated gene",
                "source": "OpenTargets",
                "credibility": 2,
                "score": 0.44,
            },
        ]
    ).to_parquet(root / "edges" / "disease_associated_gene.parquet", index=False)
    pd.DataFrame(
        [
            {
                "edge_key": "legacy-key-is-recomputed",
                "relation": "disease_associated_gene",
                "x_id": "NCBI:672",
                "x_type": "gene",
                "y_id": "EFO:0000305",
                "y_type": "disease",
                "evidence_type": "database_record",
                "source": "OpenTargets",
                "source_dataset": "reactome",
                "source_record_id": "fixture-record-0",
                "paper_id": None,
                "dataset_id": None,
                "study_id": None,
                "evidence_score": 0.88,
                "predicate": "disease_associated_gene",
                "direction": "forward",
                "release": "fixture",
            },
            {
                "edge_key": "legacy-key-is-recomputed",
                "relation": "disease_associated_gene",
                "x_id": "NCBI:672",
                "x_type": "gene",
                "y_id": "MONDO:0019391",
                "y_type": "disease",
                "evidence_type": "database_record",
                "source": "OpenTargets",
                "source_dataset": "eva",
                "source_record_id": "fixture-record-1",
                "paper_id": None,
                "dataset_id": None,
                "study_id": None,
                "evidence_score": 0.42,
                "predicate": "disease_associated_gene",
                "direction": "forward",
                "release": "fixture",
            },
        ]
    ).to_parquet(root / "evidence" / "disease_associated_gene.parquet", index=False)
    pd.DataFrame(
        [
            {
                "x_id": "GTEx:lung",
                "x_type": "tissue",
                "y_id": "NCBI:1",
                "y_type": "gene",
                "relation": "tissue_expresses_gene",
                "display_relation": "expresses",
                "source": "GTEx",
                "credibility": 2,
            }
        ]
    ).to_parquet(root / "edges" / "tissue_expresses_gene.parquet", index=False)


class FakeValuesQuerySet:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def count(self) -> int:
        return len(self.rows)

    def values(self, *fields: str):
        return [{field: row.get(field) for field in fields} for row in self.rows]


class FakeManager:
    def __init__(self):
        self.records: dict[str, dict[str, Any]] = {}
        self.bulk_calls: list[dict[str, Any]] = []

    def update_or_create(self, defaults: dict[str, Any], **lookup: str):
        key_field, key = next(iter(lookup.items()))
        record = dict(defaults)
        record[key_field] = key
        created = key not in self.records
        self.records[key] = record
        return record, created

    def bulk_create(
        self,
        objects: list[Any],
        *,
        batch_size: int,
        update_conflicts: bool,
        update_fields: list[str],
        unique_fields: list[str],
    ):
        self.bulk_calls.append(
            {
                "batch_size": batch_size,
                "update_conflicts": update_conflicts,
                "update_fields": update_fields,
                "unique_fields": unique_fields,
                "rows": len(objects),
            }
        )
        key_field = unique_fields[0]
        for obj in objects:
            record = dict(vars(obj))
            self.records[record[key_field]] = record
        return objects

    def filter(self, **lookups: Any):
        rows = list(self.records.values())
        for lookup, expected in lookups.items():
            if lookup.endswith("__in"):
                field = lookup[: -len("__in")]
                expected_set = set(expected)
                rows = [row for row in rows if row.get(field) in expected_set]
            else:
                rows = [row for row in rows if row.get(lookup) == expected]
        return FakeValuesQuerySet(rows)


class FakeModel:
    objects = FakeManager()

    def __init__(self, **kwargs: Any):
        self.__dict__.update(kwargs)


class FakeKGEdge(FakeModel):
    pass


class FakeKGEdgeEvidence(FakeModel):
    pass


def _patch_fake_lamin(monkeypatch) -> None:
    FakeKGEdge.objects = FakeManager()
    FakeKGEdgeEvidence.objects = FakeManager()
    monkeypatch.setattr(live_sync, "_connect_lamin", lambda _: None)
    monkeypatch.setattr(live_sync, "_configure_sqlite_timeout", lambda: None)
    monkeypatch.setattr(live_sync, "_registry_models", lambda: (FakeKGEdge, FakeKGEdgeEvidence))
    monkeypatch.setattr(live_sync, "_transaction_atomic", lambda: contextlib.nullcontext())


def test_limited_parquet_reader_streams_batches_before_bounded_window(monkeypatch) -> None:
    batches_seen: list[list[str]] = []

    class FakeFS:
        def exists(self, path: str) -> bool:
            return path.endswith("edges/large_relation.parquet")

        def open(self, path: str, mode: str):
            assert mode == "rb"
            return contextlib.nullcontext(object())

    class FakeRoot:
        fs = FakeFS()

        def _join(self, subdir: str, name: str) -> str:
            return f"{subdir}/{name}"

    class FakeMetadata:
        num_rows = 100

    class FakeParquetFile:
        metadata = FakeMetadata()
        schema_arrow = pa.schema([("x_id", pa.string()), ("score", pa.int64())])

        def __init__(self, handle: object):
            self.handle = handle

        def read(self):  # pragma: no cover - fails if the old whole-file path is used
            raise AssertionError("bounded reader must not call ParquetFile.read()")

        def iter_batches(self, *, batch_size: int):
            assert batch_size == 10
            for start in range(0, 100, 10):
                values = [str(idx) for idx in range(start, start + 10)]
                batches_seen.append(values)
                yield pa.record_batch(
                    [pa.array(values), pa.array(range(start, start + 10))],
                    names=["x_id", "score"],
                )

    monkeypatch.setattr(live_sync.kg_storage, "open_kg_root", lambda _: FakeRoot())
    monkeypatch.setattr(live_sync.pq, "ParquetFile", FakeParquetFile)

    frame, total = live_sync._read_limited_parquet(
        "memory://kg",
        "edges",
        "large_relation",
        limit=7,
        offset=25,
        batch_size=10,
    )

    assert total == 100
    assert frame["x_id"].tolist() == ["25", "26", "27", "28", "29", "30", "31"]
    assert batches_seen == [
        [str(idx) for idx in range(0, 10)],
        [str(idx) for idx in range(10, 20)],
        [str(idx) for idx in range(20, 30)],
        [str(idx) for idx in range(30, 40)],
    ]


def test_live_sync_dry_run_does_not_touch_models(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kg"
    _write_edge_fixture(root)
    _patch_fake_lamin(monkeypatch)

    summaries = live_sync.sync_parquet_edges_to_lamindb(
        root,
        relations=["disease_associated_gene"],
        edge_limit=1,
        evidence_limit=1,
        write=False,
    )

    assert summaries[0].status == "dry_run"
    assert summaries[0].edge_rows_available == 3
    assert summaries[0].edge_rows_selected == 1
    assert summaries[0].evidence_rows_available == 2
    assert summaries[0].evidence_rows_selected == 1
    assert FakeKGEdge.objects.records == {}
    assert FakeKGEdgeEvidence.objects.records == {}


def test_live_sync_write_uses_bulk_upsert_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kg"
    _write_edge_fixture(root)
    _patch_fake_lamin(monkeypatch)

    summaries = live_sync.sync_parquet_edges_to_lamindb(
        root,
        relations=["disease_associated_gene"],
        edge_limit=2,
        evidence_limit=1,
        chunk_size=1,
        write=True,
        idempotence_passes=2,
    )

    summary = summaries[0]
    assert summary.status == "bounded live sync bulk accepted"
    assert summary.edge_upserts == 2
    assert summary.evidence_upserts == 1
    assert summary.edge_count_after == 2
    assert summary.evidence_count_after == 1
    assert len(summary.chunks) == 2
    assert len(FakeKGEdge.objects.records) == 2
    assert len(FakeKGEdgeEvidence.objects.records) == 1
    assert all(call["update_conflicts"] for call in FakeKGEdge.objects.bulk_calls)
    assert all(call["unique_fields"] == ["edge_key"] for call in FakeKGEdge.objects.bulk_calls)
    assert all(call["unique_fields"] == ["evidence_key"] for call in FakeKGEdgeEvidence.objects.bulk_calls)

    edge = next(row for row in FakeKGEdge.objects.records.values() if row["source"] == "OpenTargets")
    assert edge["x_id"] == "NCBI:672"
    assert edge["x_type"] == "gene"
    assert edge["y_id"] == "EFO:0000305"
    assert edge["y_type"] == "disease"
    assert edge["relation"] == "disease_associated_gene"
    assert edge["metadata"] == {"score": 0.88}

    evidence = next(iter(FakeKGEdgeEvidence.objects.records.values()))
    assert evidence["edge_key"] != "legacy-key-is-recomputed"
    assert evidence["source_dataset"] == "reactome"
    assert evidence["source_record_id"] == "fixture-record-0"
    assert evidence["metadata"] == {"release": "fixture"}


def test_live_sync_resume_and_window_arguments_select_expected_rows(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kg"
    _write_edge_fixture(root)
    _patch_fake_lamin(monkeypatch)

    summaries = live_sync.sync_parquet_edges_to_lamindb(
        root,
        relations=["disease_associated_gene"],
        edge_offset=1,
        edge_limit=2,
        evidence_offset=1,
        evidence_limit=1,
        chunk_size=1,
        resume_chunk=1,
        write=True,
    )

    summary = summaries[0]
    assert summary.edge_rows_available == 3
    assert summary.edge_rows_selected == 2
    assert summary.evidence_rows_available == 2
    assert summary.evidence_rows_selected == 1
    assert [chunk.chunk_index for chunk in summary.chunks] == [1]
    assert [chunk.edge_offset for chunk in summary.chunks] == [2]
    assert len(FakeKGEdge.objects.records) == 1
    assert next(iter(FakeKGEdge.objects.records.values()))["x_id"] == "NCBI:675"
    assert len(FakeKGEdgeEvidence.objects.records) == 0


def test_live_sync_handles_relation_without_evidence_file(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kg"
    _write_edge_fixture(root)
    _patch_fake_lamin(monkeypatch)

    summaries = live_sync.sync_parquet_edges_to_lamindb(
        root,
        relations=["tissue_expresses_gene"],
        edge_limit=1,
        evidence_limit=1,
        write=True,
    )

    summary = summaries[0]
    assert summary.edge_upserts == 1
    assert summary.evidence_upserts == 0
    assert summary.evidence_rows_available == 0
    assert summary.evidence_rows_selected == 0
    assert len(FakeKGEdge.objects.records) == 1
    assert FakeKGEdgeEvidence.objects.records == {}


def test_live_sync_explicit_skip_evidence_never_reads_present_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "kg"
    _write_edge_fixture(root)
    _patch_fake_lamin(monkeypatch)

    summaries = live_sync.sync_parquet_edges_to_lamindb(
        root,
        relations=["disease_associated_gene"],
        edge_limit=1,
        evidence_limit=1,
        skip_evidence=True,
        write=True,
    )

    summary = summaries[0]
    assert summary.edge_upserts == 1
    assert summary.evidence_upserts == 0
    assert summary.evidence_rows_available == 0
    assert summary.evidence_rows_selected == 0
    assert FakeKGEdgeEvidence.objects.records == {}


def test_live_sync_selected_window_source_live_check(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kg"
    _write_edge_fixture(root)
    _patch_fake_lamin(monkeypatch)

    summaries = live_sync.sync_parquet_edges_to_lamindb(
        root,
        relations=["disease_associated_gene"],
        edge_limit=2,
        evidence_limit=1,
        write=True,
        verify_selected_live=True,
    )

    summary = summaries[0]
    assert summary.selected_live_edges_found == 2
    assert summary.selected_live_evidence_found == 1
    assert summary.source_live_mismatch_count == 0


def test_live_sync_cli_accepts_resume_window_idempotence_arguments() -> None:
    parser = live_sync.build_parser()
    args = parser.parse_args(
        [
            "gs://example/kg",
            "--relation",
            "disease_associated_gene",
            "--edge-offset",
            "10",
            "--edge-limit",
            "20",
            "--evidence-offset",
            "30",
            "--evidence-limit",
            "40",
            "--chunk-size",
            "5",
            "--resume-chunk",
            "2",
            "--max-chunks",
            "3",
            "--idempotence-passes",
            "2",
            "--verify-selected-live",
            "--json",
        ]
    )

    assert args.edge_offset == 10
    assert args.edge_limit == 20
    assert args.evidence_offset == 30
    assert args.evidence_limit == 40
    assert args.chunk_size == 5
    assert args.resume_chunk == 2
    assert args.max_chunks == 3
    assert args.idempotence_passes == 2
    assert args.verify_selected_live is True
    assert args.json is True


def test_live_sync_cli_accepts_explicit_skip_evidence() -> None:
    parser = live_sync.build_parser()

    args = parser.parse_args(
        [
            "gs://example/kg",
            "--relation",
            "cell_line_derived_from_tissue",
            "--edge-limit",
            "5",
            "--skip-evidence",
        ]
    )

    assert args.skip_evidence is True
