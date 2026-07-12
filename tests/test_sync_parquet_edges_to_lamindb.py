from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from manage_db import sync_parquet_edges_to_lamindb as sync


REL = "disease_associated_gene"


def _fixture(root: Path, *, edges: int = 2, evidence: int = 2) -> None:
    (root / "edges").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    edge_rows = [{"x_id": f"G:{i}", "x_type": "gene", "y_id": f"D:{i}", "y_type": "disease", "relation": REL, "source": "fixture", "credibility": 1} for i in range(edges)]
    evidence_rows = [{"x_id": f"G:{i}", "x_type": "gene", "y_id": f"D:{i}", "y_type": "disease", "relation": REL, "source": "fixture", "evidence_type": "record", "source_dataset": "fixture", "source_record_id": str(i), "evidence_score": 1.0, "predicate": REL, "direction": "forward"} for i in range(evidence)]
    pd.DataFrame(edge_rows).to_parquet(root / "edges" / f"{REL}.parquet", index=False)
    pd.DataFrame(evidence_rows).to_parquet(root / "evidence" / f"{REL}.parquet", index=False)


class Query:
    def __init__(self, rows: list[dict[str, Any]]): self.rows = rows
    def values(self, *fields: str): return [{field: row.get(field) for field in fields} for row in self.rows]


class Manager:
    def __init__(self): self.records: dict[str, dict[str, Any]] = {}
    def bulk_create(self, objects, *, batch_size, update_conflicts, update_fields, unique_fields):
        assert update_conflicts
        for obj in objects:
            self.records[vars(obj)[unique_fields[0]]] = dict(vars(obj))
        return objects
    def filter(self, **lookups):
        rows = list(self.records.values())
        for lookup, values in lookups.items():
            field = lookup.removesuffix("__in")
            rows = [row for row in rows if row.get(field) in set(values)]
        return Query(rows)


class Model:
    objects = Manager()
    def __init__(self, **kwargs): self.__dict__.update(kwargs)


class Edge(Model): pass
class Evidence(Model): pass


def _fake_lamin(monkeypatch, *, mismatch: bool = False) -> None:
    Edge.objects, Evidence.objects = Manager(), Manager()
    monkeypatch.setattr(sync, "_connect_lamin", lambda _: None)
    monkeypatch.setattr(sync, "_configure_sqlite_timeout", lambda: None)
    monkeypatch.setattr(sync, "_registry_models", lambda: (Edge, Evidence))
    monkeypatch.setattr(sync, "_transaction_atomic", lambda: contextlib.nullcontext())
    if mismatch:
        monkeypatch.setattr(sync, "_verify_selected", lambda *args, **kwargs: (0, 1))


def test_streaming_reader_never_uses_full_parquet_read(monkeypatch, tmp_path: Path) -> None:
    _fixture(tmp_path)
    original = sync.pq.ParquetFile
    class NoRead(original):
        def read(self, *args, **kwargs): raise AssertionError("full parquet materialization is forbidden")
    monkeypatch.setattr(sync.pq, "ParquetFile", NoRead)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=0, evidence_limit=0, chunk_size=1)
    assert (result.edge_rows_selected, result.evidence_rows_selected) == (2, 2)


def test_limit_zero_means_all_remaining_in_dry_run(tmp_path: Path) -> None:
    _fixture(tmp_path, edges=2, evidence=1)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_offset=1, edge_limit=0, evidence_limit=0, chunk_size=1)
    assert (result.edge_rows_selected, result.evidence_rows_selected) == (1, 1)


def test_finite_limit_exhausted_by_resume_is_not_unbounded(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, resume_chunk=1, write=True, verify_selected_live=True)
    assert result.status == "no_verified_subchunks"
    assert result.chunks == []
    assert Edge.objects.records == Evidence.objects.records == {}


@pytest.mark.parametrize(("edges", "evidence", "expected"), [(2, 1, (2, 1)), (1, 2, (1, 2))])
def test_asymmetric_streams_advance_only_nonempty_cursor(tmp_path: Path, monkeypatch, edges: int, evidence: int, expected: tuple[int, int]) -> None:
    _fixture(tmp_path, edges=edges, evidence=evidence)
    _fake_lamin(monkeypatch)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=0, evidence_limit=0, chunk_size=1, write=True, verify_selected_live=True)
    assert (result.durable_edge_current_offset, result.durable_evidence_current_offset) == expected
    assert [(c.edge_rows_selected, c.evidence_rows_selected) for c in result.chunks][-1] in {(1, 0), (0, 1)}


def test_mismatch_emits_no_telemetry_or_durable_offset(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch, mismatch=True)
    telemetry = tmp_path / "progress.jsonl"
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry)
    assert result.status == "verification_failed"
    assert result.chunks == []
    assert result.durable_edge_current_offset is None
    assert not telemetry.exists()


def test_unverified_write_is_rejected_before_upsert(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    with pytest.raises(RuntimeError, match="verify_selected_live"):
        sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, write=True)
    assert Edge.objects.records == {}


def test_direct_api_cannot_bypass_global_lock_with_other_telemetry_path(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    called = False
    original = sync._sync_relation_pass
    def observe(*args, **kwargs):
        nonlocal called
        called = True
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, "_sync_relation_pass", observe)
    with sync._single_writer_guard("jkobject/jouvencekb"):
        with pytest.raises(RuntimeError, match="global Lamin sync lock"):
            sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, write=True, verify_selected_live=True, telemetry_path=tmp_path / "other.jsonl")
    assert called is False


def test_registry_models_fails_closed_without_activated_registry(monkeypatch) -> None:
    import sys
    monkeypatch.setitem(sys.modules, "django.apps", None)
    with pytest.raises(RuntimeError, match="activated lnschema_txgnn"):
        sync._registry_models()


def test_cli_parses_progress_and_all_remaining_contract() -> None:
    args = sync.build_parser().parse_args(["gs://jouvencekb/kg/v2", "--relation", REL, "--edge-limit", "0", "--evidence-limit", "0", "--progress-jsonl", "x.jsonl"])
    assert (args.edge_limit, args.evidence_limit, args.progress_jsonl) == (0, 0, "x.jsonl")
