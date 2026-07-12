"""Fail-closed, bounded streaming sync of canonical KG Parquets into LaminDB.

Writes are deliberately conservative: every write uses the instance-global lock,
verifies exactly the selected keys before emitting durable telemetry, and never
uses relation-wide counts in the write path.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import kg_edge_pilot, kg_storage
from .sync_parquet_nodes_to_lamindb import _configure_sqlite_timeout, _connect_lamin, _db_retry

DEFAULT_KG_ROOT = kg_edge_pilot.DEFAULT_KG_ROOT
DEFAULT_RELATIONS = kg_edge_pilot.DEFAULT_RELATIONS
DEFAULT_EDGE_LIMIT = 25
DEFAULT_EVIDENCE_LIMIT = 25
DEFAULT_CHUNK_SIZE = 5_000
DEFAULT_BATCH_SIZE = 1_000
DEFAULT_SOURCE_BATCH_SIZE = 65_536
_EXPECTED_INSTANCE = "jkobject/jouvencekb"

EDGE_UPDATE_FIELDS = ["x_id", "x_type", "y_id", "y_type", "relation", "display_relation", "source", "credibility", "metadata"]
EVIDENCE_UPDATE_FIELDS = ["edge_key", "relation", "x_id", "x_type", "y_id", "y_type", "evidence_type", "source", "source_dataset", "source_record_id", "paper_id", "dataset_id", "study_id", "evidence_score", "predicate", "direction", "metadata"]


@dataclass(frozen=True)
class RelationWindow:
    relation: str
    edge_offset: int = 0
    edge_limit: int = DEFAULT_EDGE_LIMIT
    evidence_offset: int = 0
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT
    chunk_size: int = DEFAULT_CHUNK_SIZE


@dataclass
class LiveEdgeSyncChunk:
    relation: str
    chunk_index: int
    edge_offset: int
    edge_limit: int
    evidence_offset: int
    evidence_limit: int
    edge_rows_available: int
    edge_rows_selected: int
    evidence_rows_available: int
    evidence_rows_selected: int
    edge_upserts: int = 0
    evidence_upserts: int = 0
    durable_edge_current_offset: int | None = None
    durable_evidence_current_offset: int | None = None
    status: str = "dry_run"


@dataclass
class LiveEdgeSyncSummary:
    relation: str
    edge_offset: int = 0
    edge_limit: int = DEFAULT_EDGE_LIMIT
    evidence_offset: int = 0
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT
    chunk_size: int = DEFAULT_CHUNK_SIZE
    resume_chunk: int = 0
    max_chunks: int | None = None
    idempotence_passes: int = 1
    edge_rows_available: int = 0
    edge_rows_selected: int = 0
    evidence_rows_available: int = 0
    evidence_rows_selected: int = 0
    edge_upserts: int = 0
    evidence_upserts: int = 0
    selected_live_edges_found: int | None = None
    selected_live_evidence_found: int | None = None
    source_live_mismatch_count: int | None = None
    durable_edge_current_offset: int | None = None
    durable_evidence_current_offset: int | None = None
    chunks: list[LiveEdgeSyncChunk] = field(default_factory=list)
    status: str = "dry_run"
    status_detail: str | None = None


class _VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class _WriterCapability:
    """Unforgeable-by-identity capability valid only in its owning guard scope."""

    lamin_instance: str
    owner_thread: int


_writer_capability_state_lock = threading.Lock()
_active_writer_capability: _WriterCapability | None = None


def _has_active_writer_capability(token: object | None) -> bool:
    """Accept only the capability issued to the currently active guard scope."""
    with _writer_capability_state_lock:
        return (
            isinstance(token, _WriterCapability)
            and token is _active_writer_capability
            and token.owner_thread == threading.get_ident()
        )


@contextlib.contextmanager
def _single_writer_guard(lamin_instance: str) -> Iterator[object]:
    """Acquire a host-global lock keyed solely by the target Lamin instance."""
    global _active_writer_capability
    if lamin_instance != _EXPECTED_INSTANCE:
        raise ValueError(f"expected exact Lamin instance {_EXPECTED_INSTANCE!r}, got {lamin_instance!r}")
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("fail closed: fcntl writer lock is unavailable") from exc
    digest = hashlib.sha256(lamin_instance.encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / f"txgnn-lamindb-{digest}.lock"
    handle = path.open("a+")
    capability = _WriterCapability(lamin_instance=lamin_instance, owner_thread=threading.get_ident())
    capability_activated = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another writer holds the global Lamin sync lock for {lamin_instance}") from exc
        with _writer_capability_state_lock:
            if _active_writer_capability is not None:
                raise RuntimeError("another writer capability is already active in this process")
            _active_writer_capability = capability
            capability_activated = True
        yield capability
    finally:
        try:
            # Revoke the capability while the lock is still held so a retained
            # object cannot authorize a later write after scope exit.
            if capability_activated:
                with _writer_capability_state_lock:
                    if _active_writer_capability is capability:
                        _active_writer_capability = None
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _registry_models() -> tuple[Any, Any]:
    """Resolve models from the activated Django registry, never hand-mirrored tables."""
    try:
        from django.apps import apps
        edge = apps.get_model("lnschema_txgnn", "KGEdge", require_ready=True)
        evidence = apps.get_model("lnschema_txgnn", "KGEdgeEvidence", require_ready=True)
    except Exception as exc:
        raise RuntimeError("fail closed: activated lnschema_txgnn KGEdge/KGEdgeEvidence models are unavailable") from exc
    if edge is None or evidence is None or edge._meta.app_label != "lnschema_txgnn" or evidence._meta.app_label != "lnschema_txgnn":
        raise RuntimeError("fail closed: resolved models are not activated lnschema_txgnn models")
    return edge, evidence


def _transaction_atomic():
    try:
        from django.db import transaction
        return transaction.atomic()
    except Exception:  # pragma: no cover
        return contextlib.nullcontext()


def _clean_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _metadata_dict(value: object) -> dict[str, Any] | None:
    value = _clean_value(value)
    if value is None:
        return None
    if isinstance(value, dict):
        out = dict(value)
    else:
        out = json.loads(str(value)) if str(value) else {}
        if not isinstance(out, dict):
            out = {"value": out}
    out.pop("edge_key", None)
    out.pop("evidence_key", None)
    return out or None


def _row_dict(row: Mapping[str, Any], *, base_columns: Iterable[str]) -> dict[str, Any]:
    out = {column: _clean_value(row.get(column)) for column in base_columns}
    out["metadata"] = _metadata_dict(row.get("metadata_json"))
    return out


def _edge_defaults(row: Mapping[str, Any]) -> dict[str, Any]:
    return _row_dict(row, base_columns=kg_edge_pilot.EDGE_BASE_COLUMNS)


def _evidence_defaults(row: Mapping[str, Any]) -> dict[str, Any]:
    return _row_dict(row, base_columns=kg_edge_pilot.EVIDENCE_BASE_COLUMNS)


def _parquet_metadata(kg_root: str | Path, subdir: str, relation: str) -> tuple[Any | None, int]:
    root = kg_storage.open_kg_root(str(kg_root))
    path = root._join(subdir, f"{relation}.parquet")
    if not root.fs.exists(path):
        return None, 0
    with root.fs.open(path, "rb") as handle:
        return (None, pq.ParquetFile(handle).metadata.num_rows)


def _empty_edge_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["edge_key", *kg_edge_pilot.EDGE_BASE_COLUMNS, "metadata_json"])


def _empty_evidence_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"])


def _transform_edge(batch: pa.RecordBatch) -> pd.DataFrame:
    frame = batch.to_pandas()
    if frame.empty:
        return _empty_edge_frame()
    missing = [c for c in ("x_id", "x_type", "y_id", "y_type", "relation") if c not in frame]
    if missing:
        raise ValueError(f"edge parquet missing required columns: {missing}")
    for col in kg_edge_pilot.EDGE_BASE_COLUMNS:
        if col not in frame:
            frame[col] = None
    frame["edge_key"] = [kg_edge_pilot.edge_key_for(relation=str(r.relation), x_type=str(r.x_type), x_id=str(r.x_id), y_type=str(r.y_type), y_id=str(r.y_id)) for r in frame.itertuples()]
    frame["metadata_json"] = [kg_edge_pilot._metadata_json(r, [*kg_edge_pilot.EDGE_BASE_COLUMNS, "edge_key"]) for _, r in frame.iterrows()]
    return frame[["edge_key", *kg_edge_pilot.EDGE_BASE_COLUMNS, "metadata_json"]]


def _transform_evidence(batch: pa.RecordBatch, absolute_offset: int) -> pd.DataFrame:
    frame = batch.to_pandas()
    if frame.empty:
        return _empty_evidence_frame()
    for col in kg_edge_pilot.EVIDENCE_BASE_COLUMNS:
        if col not in frame:
            frame[col] = None
    frame["edge_key"] = [kg_edge_pilot.edge_key_for(relation=str(r.relation), x_type=str(r.x_type), x_id=str(r.x_id), y_type=str(r.y_type), y_id=str(r.y_id)) for r in frame.itertuples()]
    frame["evidence_key"] = [kg_edge_pilot.evidence_key_for(row, ordinal=absolute_offset + i) for i, (_, row) in enumerate(frame.iterrows())]
    frame["metadata_json"] = [kg_edge_pilot._metadata_json(r, kg_edge_pilot.EVIDENCE_BASE_COLUMNS) for _, r in frame.iterrows()]
    return frame[["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"]]


def _iter_selected_batches(kg_root: str | Path, subdir: str, relation: str, *, offset: int, limit: int, chunk_size: int, transform: Callable[[pa.RecordBatch, int], pd.DataFrame]) -> Iterator[tuple[int, pd.DataFrame]]:
    if offset < 0 or limit < 0 or chunk_size <= 0:
        raise ValueError("offset/limit/chunk_size must be non-negative and chunk_size > 0")
    root = kg_storage.open_kg_root(str(kg_root))
    path = root._join(subdir, f"{relation}.parquet")
    if not root.fs.exists(path):
        return
    remaining_offset, remaining_limit, absolute = offset, (None if limit == 0 else limit), offset
    with root.fs.open(path, "rb") as handle:
        parquet = pq.ParquetFile(handle)
        for batch in parquet.iter_batches(batch_size=min(DEFAULT_SOURCE_BATCH_SIZE, chunk_size)):
            if remaining_limit == 0:
                break
            length = batch.num_rows
            if remaining_offset >= length:
                remaining_offset -= length
                continue
            start = remaining_offset
            take = length - start if remaining_limit is None else min(length - start, remaining_limit)
            if take:
                sliced = batch.slice(start, take)
                yield absolute, transform(sliced, absolute)
                absolute += take
                if remaining_limit is not None:
                    remaining_limit -= take
            remaining_offset = 0


def build_edge_frame(kg_root: str | Path, relation: str, *, limit: int, offset: int = 0) -> tuple[pd.DataFrame, int]:
    frames = [f for _, f in _iter_selected_batches(kg_root, "edges", relation, offset=offset, limit=limit, chunk_size=DEFAULT_SOURCE_BATCH_SIZE, transform=lambda b, _: _transform_edge(b))]
    _, total = _parquet_metadata(kg_root, "edges", relation)
    return (pd.concat(frames, ignore_index=True) if frames else _empty_edge_frame(), total)


def build_evidence_frame(kg_root: str | Path, relation: str, *, limit: int, offset: int = 0) -> tuple[pd.DataFrame, int]:
    frames = [f for _, f in _iter_selected_batches(kg_root, "evidence", relation, offset=offset, limit=limit, chunk_size=DEFAULT_SOURCE_BATCH_SIZE, transform=_transform_evidence)]
    _, total = _parquet_metadata(kg_root, "evidence", relation)
    return (pd.concat(frames, ignore_index=True) if frames else _empty_evidence_frame(), total)


def _selected_count(total: int, offset: int, limit: int) -> int:
    available = max(0, total - offset)
    return available if limit == 0 else min(available, limit)


def _clean_records(frame: pd.DataFrame, defaults_fn: Callable[[Mapping[str, Any]], dict[str, Any]], key_field: str) -> list[dict[str, Any]]:
    return [{**defaults_fn(row), key_field: row[key_field]} for row in frame.where(pd.notna(frame), None).to_dict(orient="records") if row.get(key_field) is not None]


def _bulk_upsert_rows(model: Any, key_field: str, frame: pd.DataFrame, defaults_fn: Callable[[Mapping[str, Any]], dict[str, Any]], *, update_fields: Sequence[str], batch_size: int) -> int:
    records = _clean_records(frame, defaults_fn, key_field)
    if not records:
        return 0
    objects = [model(**record) for record in records]
    _db_retry(f"bulk upsert {model.__name__}", lambda: model.objects.bulk_create(objects, batch_size=batch_size, update_conflicts=True, update_fields=list(update_fields), unique_fields=[key_field]))
    return len(objects)


def _fetch_by_keys(model: Any, key_field: str, keys: Sequence[str], values: Sequence[str], *, batch_size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(keys), batch_size):
        batch = list(keys[start : start + batch_size])
        if batch:
            rows.extend(list(_db_retry(f"fetch {model.__name__} keys", lambda: model.objects.filter(**{f"{key_field}__in": batch}).values(*values)) or []))
    return rows


def _verify_selected(model: Any, key_field: str, frame: pd.DataFrame, fields: Sequence[str], *, batch_size: int) -> tuple[int, int]:
    source = {str(row[key_field]): row for row in frame.to_dict(orient="records")}
    live = _fetch_by_keys(model, key_field, list(source), [key_field, *fields], batch_size=batch_size)
    mismatches = len(source) - len(live)
    for row in live:
        src = source.get(str(row.get(key_field)))
        mismatches += int(src is None or any(_clean_value(src.get(field)) != _clean_value(row.get(field)) for field in fields))
    return len(live), mismatches


def _append_telemetry(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _sync_relation_pass(*, kg_root: str | Path, window: RelationWindow, write: bool, resume_chunk: int, max_chunks: int | None, batch_size: int, verify_selected_live: bool, telemetry_path: Path | None, _token: object | None = None) -> LiveEdgeSyncSummary:
    if resume_chunk < 0:
        raise ValueError("resume_chunk must be >= 0")
    if write and (not verify_selected_live or not _has_active_writer_capability(_token)):
        raise RuntimeError("fail closed: writes require selected-live verification and an active writer capability")
    _, edge_total = _parquet_metadata(kg_root, "edges", window.relation)
    _, evidence_total = _parquet_metadata(kg_root, "evidence", window.relation)
    summary = LiveEdgeSyncSummary(relation=window.relation, edge_offset=window.edge_offset, edge_limit=window.edge_limit, evidence_offset=window.evidence_offset, evidence_limit=window.evidence_limit, chunk_size=window.chunk_size, resume_chunk=resume_chunk, max_chunks=max_chunks, edge_rows_available=edge_total, evidence_rows_available=evidence_total, edge_rows_selected=_selected_count(edge_total, window.edge_offset, window.edge_limit), evidence_rows_selected=_selected_count(evidence_total, window.evidence_offset, window.evidence_limit))
    if not write:
        return summary
    edge_iter = _iter_selected_batches(kg_root, "edges", window.relation, offset=window.edge_offset, limit=window.edge_limit, chunk_size=window.chunk_size, transform=lambda b, _: _transform_edge(b))
    evidence_iter = _iter_selected_batches(kg_root, "evidence", window.relation, offset=window.evidence_offset, limit=window.evidence_limit, chunk_size=window.chunk_size, transform=_transform_evidence)
    KGEdge, KGEdgeEvidence = _registry_models()
    durable_edge, durable_evidence = window.edge_offset, window.evidence_offset
    processed = 0
    for index, pair in enumerate(zip_longest(edge_iter, evidence_iter, fillvalue=None)):
        if index < resume_chunk:
            for item in pair:
                if item is not None:
                    absolute, frame = item
                    if frame is not None:
                        if item is pair[0]: durable_edge = absolute + len(frame)
                        else: durable_evidence = absolute + len(frame)
            continue
        if max_chunks is not None and processed >= max_chunks:
            break
        edge_item, evidence_item = pair
        edge_absolute, edge_frame = edge_item if edge_item is not None else (durable_edge, _empty_edge_frame())
        evidence_absolute, evidence_frame = evidence_item if evidence_item is not None else (durable_evidence, _empty_evidence_frame())
        if edge_frame.empty and evidence_frame.empty:
            continue
        try:
            with _transaction_atomic():
                edge_upserts = _bulk_upsert_rows(KGEdge, "edge_key", edge_frame, _edge_defaults, update_fields=EDGE_UPDATE_FIELDS, batch_size=batch_size)
                evidence_upserts = _bulk_upsert_rows(KGEdgeEvidence, "evidence_key", evidence_frame, _evidence_defaults, update_fields=EVIDENCE_UPDATE_FIELDS, batch_size=batch_size)
                found_edges, edge_mismatches = _verify_selected(KGEdge, "edge_key", edge_frame, ["x_id", "x_type", "y_id", "y_type", "relation", "source", "credibility"], batch_size=batch_size)
                found_evidence, evidence_mismatches = _verify_selected(KGEdgeEvidence, "evidence_key", evidence_frame, ["edge_key", "x_id", "x_type", "y_id", "y_type", "relation", "source", "source_dataset", "source_record_id", "evidence_score", "predicate", "direction"], batch_size=batch_size)
                if edge_mismatches or evidence_mismatches:
                    raise _VerificationError(f"selected-live mismatch edges={edge_mismatches} evidence={evidence_mismatches}")
        except Exception as exc:
            summary.status = "verification_failed"
            summary.status_detail = str(exc)
            summary.source_live_mismatch_count = None if not isinstance(exc, _VerificationError) else 1
            return summary
        # Advance a cursor only for rows selected from that side.
        if not edge_frame.empty:
            durable_edge = edge_absolute + len(edge_frame)
        if not evidence_frame.empty:
            durable_evidence = evidence_absolute + len(evidence_frame)
        chunk = LiveEdgeSyncChunk(relation=window.relation, chunk_index=index, edge_offset=edge_absolute, edge_limit=len(edge_frame), evidence_offset=evidence_absolute, evidence_limit=len(evidence_frame), edge_rows_available=edge_total, edge_rows_selected=len(edge_frame), evidence_rows_available=evidence_total, evidence_rows_selected=len(evidence_frame), edge_upserts=edge_upserts, evidence_upserts=evidence_upserts, durable_edge_current_offset=durable_edge, durable_evidence_current_offset=durable_evidence, status="selected-live-verified")
        if telemetry_path is not None:
            _append_telemetry(telemetry_path, asdict(chunk))
        summary.chunks.append(chunk)
        summary.edge_upserts += edge_upserts
        summary.evidence_upserts += evidence_upserts
        summary.selected_live_edges_found = (summary.selected_live_edges_found or 0) + found_edges
        summary.selected_live_evidence_found = (summary.selected_live_evidence_found or 0) + found_evidence
        summary.source_live_mismatch_count = 0
        summary.durable_edge_current_offset = durable_edge
        summary.durable_evidence_current_offset = durable_evidence
        processed += 1
    summary.status = "bounded live sync verified" if summary.chunks else "no_verified_subchunks"
    return summary


def _sync_relation_with_token(*, lamin_instance: str, token: object, **kwargs: Any) -> LiveEdgeSyncSummary:
    return _sync_relation_pass(_token=token, **kwargs)


def sync_relation_to_lamindb(*, kg_root: str | Path, relation: str, edge_limit: int = DEFAULT_EDGE_LIMIT, evidence_limit: int = DEFAULT_EVIDENCE_LIMIT, edge_offset: int = 0, evidence_offset: int = 0, chunk_size: int = DEFAULT_CHUNK_SIZE, resume_chunk: int = 0, max_chunks: int | None = None, batch_size: int = DEFAULT_BATCH_SIZE, lamin_instance: str = _EXPECTED_INSTANCE, write: bool = False, idempotence_passes: int = 1, verify_selected_live: bool = False, telemetry_path: str | Path | None = None) -> LiveEdgeSyncSummary:
    if idempotence_passes < 1:
        raise ValueError("idempotence_passes must be >= 1")
    window = RelationWindow(relation, edge_offset, edge_limit, evidence_offset, evidence_limit, chunk_size)
    common = dict(kg_root=kg_root, window=window, write=write, resume_chunk=resume_chunk, max_chunks=max_chunks, batch_size=batch_size, verify_selected_live=verify_selected_live, telemetry_path=Path(telemetry_path) if telemetry_path else None)
    if not write:
        return _sync_relation_pass(**common)
    if not verify_selected_live:
        raise RuntimeError("fail closed: write requires verify_selected_live=True")
    _connect_lamin(lamin_instance)
    _configure_sqlite_timeout()
    with _single_writer_guard(lamin_instance) as token:
        summary = _sync_relation_with_token(lamin_instance=lamin_instance, token=token, **common)
        summary.idempotence_passes = idempotence_passes
        for _ in range(1, idempotence_passes):
            summary = _sync_relation_with_token(lamin_instance=lamin_instance, token=token, **common)
            summary.idempotence_passes = idempotence_passes
        return summary


def sync_parquet_edges_to_lamindb(kg_root: str | Path = DEFAULT_KG_ROOT, *, relations: Sequence[str] = DEFAULT_RELATIONS, lamin_instance: str = _EXPECTED_INSTANCE, **kwargs: Any) -> list[LiveEdgeSyncSummary]:
    # Each direct relation API independently acquires the instance lock. This is
    # intentionally simple and cannot be bypassed by a user-provided flag/path.
    return [sync_relation_to_lamindb(kg_root=kg_root, relation=relation, lamin_instance=lamin_instance, **kwargs) for relation in relations]


def summaries_to_json(summaries: Sequence[LiveEdgeSyncSummary]) -> str:
    return json.dumps([asdict(item) for item in summaries], indent=2, sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed bounded Lamin KG edge/evidence sync")
    parser.add_argument("kg_root", nargs="?", default=str(DEFAULT_KG_ROOT))
    parser.add_argument("--relation", action="append", dest="relations")
    parser.add_argument("--edge-offset", type=int, default=0)
    parser.add_argument("--edge-limit", type=int, default=DEFAULT_EDGE_LIMIT, help="0 means all remaining")
    parser.add_argument("--evidence-offset", type=int, default=0)
    parser.add_argument("--evidence-limit", type=int, default=DEFAULT_EVIDENCE_LIMIT, help="0 means all remaining")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--resume-chunk", type=int, default=0)
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--verify-selected-live", action="store_true")
    parser.add_argument("--progress-jsonl")
    parser.add_argument("--lamin-instance", default=_EXPECTED_INSTANCE)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summaries = sync_parquet_edges_to_lamindb(args.kg_root, relations=args.relations or list(DEFAULT_RELATIONS), edge_offset=args.edge_offset, edge_limit=args.edge_limit, evidence_offset=args.evidence_offset, evidence_limit=args.evidence_limit, chunk_size=args.chunk_size, resume_chunk=args.resume_chunk, max_chunks=args.max_chunks, batch_size=args.batch_size, verify_selected_live=args.verify_selected_live, telemetry_path=args.progress_jsonl, lamin_instance=args.lamin_instance, write=args.write)
    print(summaries_to_json(summaries) if args.json else pd.DataFrame([asdict(item) for item in summaries]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
