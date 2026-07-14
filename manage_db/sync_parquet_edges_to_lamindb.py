"""Fail-closed, bounded streaming sync of canonical KG Parquets into LaminDB.

Writes are deliberately conservative: every write uses the instance-global lock,
verifies exactly the selected keys before emitting durable telemetry, and never
uses relation-wide counts in the write path.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import resource
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
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
_STAGE_FSYNC = os.fsync
_STAGE_REPLACE = os.replace

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
    run_id: str
    record_id: str
    relation: str
    source_edge_offset: int
    source_edge_limit: int
    source_evidence_offset: int
    source_evidence_limit: int
    sync_pass_index: int
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
    last_progress_at: str | None = None
    elapsed_seconds: float | None = None
    edge_rows_per_second: float | None = None
    evidence_rows_per_second: float | None = None
    process_rss_bytes: int | None = None
    disk_free_bytes: int | None = None
    iowait_seconds: float | None = None
    iowait_status: str = "unavailable"
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


class _TelemetryDurabilityError(RuntimeError):
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


def _iter_selected_batches(
    kg_root: str | Path,
    subdir: str,
    relation: str,
    *,
    offset: int,
    limit: int,
    chunk_size: int,
    transform: Callable[[pa.RecordBatch, int], pd.DataFrame],
    on_first_source_stage: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Iterator[tuple[int, pd.DataFrame]]:
    if offset < 0 or limit < 0 or chunk_size <= 0:
        raise ValueError("offset/limit/chunk_size must be non-negative and chunk_size > 0")
    root = kg_storage.open_kg_root(str(kg_root))
    path = root._join(subdir, f"{relation}.parquet")
    if not root.fs.exists(path):
        return
    remaining_offset, remaining_limit, absolute = offset, (None if limit == 0 else limit), offset
    with root.fs.open(path, "rb") as handle:
        parquet = pq.ParquetFile(handle)
        first_selected_row_group = True
        first_yield = True
        buffered_batches: list[pa.RecordBatch] = []
        buffered_rows = 0
        for row_group_index in range(parquet.metadata.num_row_groups):
            if remaining_limit == 0:
                break
            row_group_rows = parquet.metadata.row_group(row_group_index).num_rows
            if remaining_offset >= row_group_rows:
                remaining_offset -= row_group_rows
                continue
            if first_selected_row_group and on_first_source_stage is not None:
                on_first_source_stage(
                    f"{subdir.removesuffix('s')}_row_group_seek",
                    {
                        "row_group_index": row_group_index,
                        "row_group_rows": row_group_rows,
                        "offset_within_row_group": remaining_offset,
                    },
                )
            first_selected_row_group = False
            for batch in parquet.iter_batches(
                batch_size=min(DEFAULT_SOURCE_BATCH_SIZE, chunk_size),
                row_groups=[row_group_index],
            ):
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
                    if first_yield and on_first_source_stage is not None:
                        on_first_source_stage(
                            f"{subdir.removesuffix('s')}_first_row_group_yield",
                            {"row_group_index": row_group_index, "rows": take},
                        )
                    first_yield = False
                    consumed = 0
                    while consumed < take:
                        piece_rows = min(chunk_size - buffered_rows, take - consumed)
                        buffered_batches.append(sliced.slice(consumed, piece_rows))
                        buffered_rows += piece_rows
                        consumed += piece_rows
                        if buffered_rows == chunk_size:
                            combined = pa.Table.from_batches(buffered_batches).combine_chunks().to_batches(max_chunksize=chunk_size)[0]
                            yield absolute, transform(combined, absolute)
                            absolute += buffered_rows
                            buffered_batches = []
                            buffered_rows = 0
                    if remaining_limit is not None:
                        remaining_limit -= take
                remaining_offset = 0
        if buffered_rows:
            combined = pa.Table.from_batches(buffered_batches).combine_chunks().to_batches(max_chunksize=buffered_rows)[0]
            yield absolute, transform(combined, absolute)


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


def _iowait_seconds() -> tuple[float | None, str]:
    """Return Linux aggregate iowait time, or an explicit production-gate failure value."""
    if platform.system() != "Linux":
        return None, "unavailable"
    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()
        ticks = int(fields[5])
        return ticks / os.sysconf("SC_CLK_TCK"), "available"
    except (IndexError, OSError, ValueError):
        return None, "unavailable"


def _telemetry_metrics() -> dict[str, Any]:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if platform.system() == "Darwin" else rss * 1024
    iowait_seconds, iowait_status = _iowait_seconds()
    return {
        "process_rss_bytes": rss_bytes,
        "disk_free_bytes": shutil.disk_usage(".").free,
        "iowait_seconds": iowait_seconds,
        "iowait_status": iowait_status,
    }


def _stage_path_for(telemetry_path: Path) -> Path:
    return telemetry_path.with_suffix(f"{telemetry_path.suffix}.stages.json")


def _fsync_stage_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path, flags)
    try:
        _STAGE_FSYNC(directory_fd)
    finally:
        os.close(directory_fd)


class _ChunkStageTelemetry:
    """Atomically persist the active stage for the currently executing chunk."""

    def __init__(
        self,
        *,
        telemetry_path: Path,
        kg_root: str | Path,
        window: RelationWindow,
        lamin_instance: str,
        task_id: str,
        run_id: str,
    ) -> None:
        self.path = _stage_path_for(telemetry_path)
        self.source_identity = {
            "root": str(kg_root),
            "relation": window.relation,
            "edge_uri": f"{str(kg_root).rstrip('/')}/edges/{window.relation}.parquet",
            "evidence_uri": f"{str(kg_root).rstrip('/')}/evidence/{window.relation}.parquet",
        }
        self.window = window
        self.lamin_instance = lamin_instance
        self.task_id = task_id
        self.run_id = run_id
        self.stage_identity = {
            "source_identity": self.source_identity,
            "source_window": asdict(window),
            "lamin_instance": lamin_instance,
            "task_id": task_id,
            "run_id": run_id,
        }
        canonical_identity = json.dumps(
            self.stage_identity, sort_keys=True, separators=(",", ":")
        )
        self.stage_identity_sha256 = hashlib.sha256(
            canonical_identity.encode("utf-8")
        ).hexdigest()
        self.records: list[dict[str, Any]] = []
        self.active_chunk_index: int | None = None
        self.stage_sequence = 0
        self.previous_stage_sequence_sha256: str | None = None

    def emit(
        self,
        stage: str,
        *,
        chunk_index: int,
        edge_offset: int,
        evidence_offset: int,
        edge_rows: int = 0,
        evidence_rows: int = 0,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if self.active_chunk_index != chunk_index:
            self.active_chunk_index = chunk_index
            self.records = []
        self.stage_sequence += 1
        stage_sequence_identity = {
            "stage_identity_sha256": self.stage_identity_sha256,
            "previous_stage_sequence_sha256": self.previous_stage_sequence_sha256,
            "stage_sequence": self.stage_sequence,
            "stage": stage,
            "chunk_index": chunk_index,
            "edge_offset": edge_offset,
            "evidence_offset": evidence_offset,
            "edge_rows": edge_rows,
            "evidence_rows": evidence_rows,
        }
        canonical_sequence = json.dumps(
            stage_sequence_identity, sort_keys=True, separators=(",", ":")
        )
        stage_sequence_sha256 = hashlib.sha256(
            canonical_sequence.encode("utf-8")
        ).hexdigest()
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "stage_sequence": self.stage_sequence,
            "chunk_index": chunk_index,
            "edge_offset": edge_offset,
            "evidence_offset": evidence_offset,
            "edge_rows": edge_rows,
            "evidence_rows": evidence_rows,
            "source_identity": self.source_identity,
            "stage_identity": self.stage_identity,
            "stage_identity_sha256": self.stage_identity_sha256,
            "stage_sequence_identity": stage_sequence_identity,
            "stage_sequence_sha256": stage_sequence_sha256,
            "lamin_instance": self.lamin_instance,
            "task_id": self.task_id,
            "run_id": self.run_id,
            **_telemetry_metrics(),
        }
        if details:
            record["details"] = dict(details)
        self.records.append(record)
        self.previous_stage_sequence_sha256 = stage_sequence_sha256
        payload = {
            "schema_version": 3,
            "active_chunk_index": chunk_index,
            "active_stage": stage,
            "records": self.records,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.pending")
        try:
            with pending.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                _STAGE_FSYNC(handle.fileno())
            _STAGE_REPLACE(pending, self.path)
            _fsync_stage_directory(self.path.parent)
        except OSError as exc:
            pending.unlink(missing_ok=True)
            raise _TelemetryDurabilityError(
                f"chunk stage telemetry failed for {self.path.resolve()}: {exc}"
            ) from exc


def _ack_path_for(telemetry_path: Path) -> Path:
    return telemetry_path.with_suffix(f"{telemetry_path.suffix}.ack.jsonl")


def _fsync_directory(path: Path) -> None:
    """Make a prior rename durable in its containing directory."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _append_durable_telemetry(
    path: Path,
    payload: Mapping[str, Any],
    *,
    on_stage: Callable[[str, Mapping[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    """Persist a subchunk record then a separately fsynced acknowledgement.

    The acknowledgement is written only after the telemetry record's successful
    ``write -> flush -> os.fsync`` sequence.  If either fsync fails, no caller
    receives a checkpoint-eligible acknowledgement.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(payload)
    if not record.get("run_id") or not record.get("record_id"):
        raise ValueError("durable telemetry requires non-empty run_id and record_id")
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    encoded = json.dumps(record, sort_keys=True) + "\n"
    try:
        if on_stage is not None:
            on_stage("progress_flush_fsync_start", None)
        progress_started = time.monotonic()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if on_stage is not None:
            on_stage(
                "progress_flush_fsync_complete",
                {"duration_seconds": time.monotonic() - progress_started},
            )
    except OSError as exc:
        raise _TelemetryDurabilityError(f"telemetry fsync failed for {path.resolve()}: {exc}") from exc

    ack_path = _ack_path_for(path)
    acknowledgement = {
        "acknowledgement_path": str(ack_path.resolve()),
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "fsync_success": True,
        "record_id": record["record_id"],
        "record_sha256": record["record_sha256"],
        "run_id": record["run_id"],
        "telemetry_path": str(path.resolve()),
    }
    ack_encoded = json.dumps(acknowledgement, sort_keys=True) + "\n"
    existing_acknowledgements = ack_path.read_text(encoding="utf-8") if ack_path.exists() else ""
    pending_ack_path = ack_path.with_suffix(f"{ack_path.suffix}.{record['record_id']}.pending")
    try:
        if on_stage is not None:
            on_stage("ack_flush_fsync_start", None)
        ack_started = time.monotonic()
        with pending_ack_path.open("w", encoding="utf-8") as handle:
            handle.write(existing_acknowledgements + ack_encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending_ack_path, ack_path)
        _fsync_directory(ack_path.parent)
        if on_stage is not None:
            on_stage(
                "ack_flush_fsync_complete",
                {"duration_seconds": time.monotonic() - ack_started},
            )
    except OSError as exc:
        # Before replace, a pending file is cleaned up.  After replace, an ack
        # can be visible but is intentionally unaccepted if the directory fsync
        # fails; recovery must re-run selected-live verification and emit a new
        # acknowledgement rather than treating that visible file as durable.
        pending_ack_path.unlink(missing_ok=True)
        raise _TelemetryDurabilityError(f"telemetry acknowledgement fsync failed for {ack_path.resolve()}: {exc}") from exc
    return acknowledgement


def _sync_relation_pass(*, kg_root: str | Path, window: RelationWindow, write: bool, resume_chunk: int, max_chunks: int | None, batch_size: int, verify_selected_live: bool, telemetry_path: Path | None, run_id: str, task_id: str | None = None, lamin_instance: str = _EXPECTED_INSTANCE, sync_pass_index: int = 0, _token: object | None = None) -> LiveEdgeSyncSummary:
    if resume_chunk < 0:
        raise ValueError("resume_chunk must be >= 0")
    if write and (not verify_selected_live or not _has_active_writer_capability(_token)):
        raise RuntimeError("fail closed: writes require selected-live verification and an active writer capability")

    effective_task_id = task_id or run_id.split("-", 1)[0]
    stage_telemetry = None
    if write and telemetry_path is not None:
        stage_telemetry = _ChunkStageTelemetry(
            telemetry_path=telemetry_path,
            kg_root=kg_root,
            window=window,
            lamin_instance=lamin_instance,
            task_id=effective_task_id,
            run_id=run_id,
        )
    _, edge_total = _parquet_metadata(kg_root, "edges", window.relation)
    _, evidence_total = _parquet_metadata(kg_root, "evidence", window.relation)
    summary = LiveEdgeSyncSummary(relation=window.relation, edge_offset=window.edge_offset, edge_limit=window.edge_limit, evidence_offset=window.evidence_offset, evidence_limit=window.evidence_limit, chunk_size=window.chunk_size, resume_chunk=resume_chunk, max_chunks=max_chunks, edge_rows_available=edge_total, evidence_rows_available=evidence_total, edge_rows_selected=_selected_count(edge_total, window.edge_offset, window.edge_limit), evidence_rows_selected=_selected_count(evidence_total, window.evidence_offset, window.evidence_limit))
    if not write:
        return summary

    edge_resume_rows = min(resume_chunk * window.chunk_size, summary.edge_rows_selected)
    evidence_resume_rows = min(resume_chunk * window.chunk_size, summary.evidence_rows_selected)
    edge_start = window.edge_offset + edge_resume_rows
    evidence_start = window.evidence_offset + evidence_resume_rows
    edge_remaining_limit = 0 if window.edge_limit == 0 else max(0, window.edge_limit - edge_resume_rows)
    evidence_remaining_limit = 0 if window.evidence_limit == 0 else max(0, window.evidence_limit - evidence_resume_rows)
    # A resumed pass starts from an already acknowledged durable boundary.  Set
    # it on the summary before any source, write, verification, or telemetry
    # operation can fail so failure reports never erase the no-replay baseline.
    if resume_chunk:
        summary.durable_edge_current_offset = edge_start
        summary.durable_evidence_current_offset = evidence_start
    active_chunk_index = resume_chunk
    if stage_telemetry is not None:
        stage_telemetry.emit(
            "iterator_window_initialization",
            chunk_index=resume_chunk,
            edge_offset=edge_start,
            evidence_offset=evidence_start,
            details={
                "edge_limit": edge_remaining_limit,
                "evidence_limit": evidence_remaining_limit,
                "chunk_size": window.chunk_size,
                "resume_chunk": resume_chunk,
            },
        )

    def source_stage(stage: str, details: Mapping[str, Any]) -> None:
        if stage_telemetry is not None:
            rows = int(details.get("rows", 0))
            stage_telemetry.emit(
                stage,
                chunk_index=active_chunk_index,
                edge_offset=edge_start,
                evidence_offset=evidence_start,
                edge_rows=rows if stage.startswith("edge_") else 0,
                evidence_rows=rows if stage.startswith("evidence_") else 0,
                details=details,
            )

    edge_iter = iter(()) if window.edge_limit > 0 and edge_remaining_limit == 0 else _iter_selected_batches(kg_root, "edges", window.relation, offset=edge_start, limit=edge_remaining_limit, chunk_size=window.chunk_size, transform=lambda b, _: _transform_edge(b), on_first_source_stage=source_stage)
    evidence_iter = iter(()) if window.evidence_limit > 0 and evidence_remaining_limit == 0 else _iter_selected_batches(kg_root, "evidence", window.relation, offset=evidence_start, limit=evidence_remaining_limit, chunk_size=window.chunk_size, transform=_transform_evidence, on_first_source_stage=source_stage)
    KGEdge, KGEdgeEvidence = _registry_models()
    durable_edge, durable_evidence = edge_start, evidence_start
    edge_target = window.edge_offset + summary.edge_rows_selected
    evidence_target = window.evidence_offset + summary.evidence_rows_selected
    processed = 0
    started_at = time.monotonic()

    def emit(stage: str, *, index: int, edge_offset: int, evidence_offset: int, edge_rows: int = 0, evidence_rows: int = 0, details: Mapping[str, Any] | None = None) -> None:
        if stage_telemetry is not None:
            stage_telemetry.emit(stage, chunk_index=index, edge_offset=edge_offset, evidence_offset=evidence_offset, edge_rows=edge_rows, evidence_rows=evidence_rows, details=details)

    while max_chunks is None or processed < max_chunks:
        if durable_edge >= edge_target and durable_evidence >= evidence_target:
            break
        index = resume_chunk + processed
        active_chunk_index = index

        emit("edge_iterator_next_start", index=index, edge_offset=durable_edge, evidence_offset=durable_evidence)
        operation_started = time.monotonic()
        edge_item = next(edge_iter, None)
        edge_absolute, edge_frame = edge_item if edge_item is not None else (durable_edge, _empty_edge_frame())
        emit("edge_iterator_next_complete", index=index, edge_offset=edge_absolute, evidence_offset=durable_evidence, edge_rows=len(edge_frame), details={"duration_seconds": time.monotonic() - operation_started})

        emit("evidence_iterator_next_start", index=index, edge_offset=edge_absolute, evidence_offset=durable_evidence, edge_rows=len(edge_frame))
        operation_started = time.monotonic()
        evidence_item = next(evidence_iter, None)
        evidence_absolute, evidence_frame = evidence_item if evidence_item is not None else (durable_evidence, _empty_evidence_frame())
        emit("evidence_iterator_next_complete", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=len(edge_frame), evidence_rows=len(evidence_frame), details={"duration_seconds": time.monotonic() - operation_started})
        if edge_frame.empty and evidence_frame.empty:
            break
        emit("chunk_materialized", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=len(edge_frame), evidence_rows=len(evidence_frame))

        try:
            emit("transaction_start", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=len(edge_frame), evidence_rows=len(evidence_frame))
            transaction_started = time.monotonic()
            with _transaction_atomic():
                emit("edge_upsert_start", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=len(edge_frame))
                operation_started = time.monotonic()
                edge_upserts = _bulk_upsert_rows(KGEdge, "edge_key", edge_frame, _edge_defaults, update_fields=EDGE_UPDATE_FIELDS, batch_size=batch_size)
                emit("edge_upsert_complete", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=edge_upserts, details={"duration_seconds": time.monotonic() - operation_started})

                emit("evidence_upsert_start", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, evidence_rows=len(evidence_frame))
                operation_started = time.monotonic()
                evidence_upserts = _bulk_upsert_rows(KGEdgeEvidence, "evidence_key", evidence_frame, _evidence_defaults, update_fields=EVIDENCE_UPDATE_FIELDS, batch_size=batch_size)
                emit("evidence_upsert_complete", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, evidence_rows=evidence_upserts, details={"duration_seconds": time.monotonic() - operation_started})

                emit("selected_live_verification_start", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=len(edge_frame), evidence_rows=len(evidence_frame))
                operation_started = time.monotonic()
                found_edges, edge_mismatches = _verify_selected(KGEdge, "edge_key", edge_frame, ["x_id", "x_type", "y_id", "y_type", "relation", "source", "credibility"], batch_size=batch_size)
                found_evidence, evidence_mismatches = _verify_selected(KGEdgeEvidence, "evidence_key", evidence_frame, ["edge_key", "x_id", "x_type", "y_id", "y_type", "relation", "source", "source_dataset", "source_record_id", "evidence_score", "predicate", "direction"], batch_size=batch_size)
                emit("selected_live_verification_complete", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=found_edges, evidence_rows=found_evidence, details={"duration_seconds": time.monotonic() - operation_started, "edge_mismatches": edge_mismatches, "evidence_mismatches": evidence_mismatches})
                if edge_mismatches or evidence_mismatches:
                    raise _VerificationError(f"selected-live mismatch edges={edge_mismatches} evidence={evidence_mismatches}")
                emit("transaction_commit_start", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=edge_upserts, evidence_rows=evidence_upserts)
                commit_started = time.monotonic()
            emit("transaction_commit_complete", index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=edge_upserts, evidence_rows=evidence_upserts, details={"duration_seconds": time.monotonic() - commit_started, "transaction_duration_seconds": time.monotonic() - transaction_started})
        except Exception as exc:
            summary.status = "verification_failed"
            summary.status_detail = str(exc)
            summary.source_live_mismatch_count = None if not isinstance(exc, _VerificationError) else 1
            return summary

        next_durable_edge = edge_absolute + len(edge_frame) if not edge_frame.empty else durable_edge
        next_durable_evidence = evidence_absolute + len(evidence_frame) if not evidence_frame.empty else durable_evidence
        elapsed_seconds = time.monotonic() - started_at
        chunk = LiveEdgeSyncChunk(run_id=run_id, record_id=f"{run_id}:{window.relation}:pass-{sync_pass_index}:{index}:{edge_absolute}:{evidence_absolute}", relation=window.relation, source_edge_offset=window.edge_offset, source_edge_limit=window.edge_limit, source_evidence_offset=window.evidence_offset, source_evidence_limit=window.evidence_limit, sync_pass_index=sync_pass_index, chunk_index=index, edge_offset=edge_absolute, edge_limit=len(edge_frame), evidence_offset=evidence_absolute, evidence_limit=len(evidence_frame), edge_rows_available=edge_total, edge_rows_selected=len(edge_frame), evidence_rows_available=evidence_total, evidence_rows_selected=len(evidence_frame), edge_upserts=edge_upserts, evidence_upserts=evidence_upserts, durable_edge_current_offset=next_durable_edge, durable_evidence_current_offset=next_durable_evidence, last_progress_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=elapsed_seconds, edge_rows_per_second=len(edge_frame) / elapsed_seconds if elapsed_seconds else None, evidence_rows_per_second=len(evidence_frame) / elapsed_seconds if elapsed_seconds else None, **_telemetry_metrics(), status="selected-live-verified")
        if telemetry_path is not None:
            try:
                stage_callback = None
                if stage_telemetry is not None:
                    stage_callback = lambda stage, details=None: emit(stage, index=index, edge_offset=edge_absolute, evidence_offset=evidence_absolute, edge_rows=len(edge_frame), evidence_rows=len(evidence_frame), details=details)
                _append_durable_telemetry(telemetry_path, asdict(chunk), on_stage=stage_callback)
            except (_TelemetryDurabilityError, OSError, ValueError) as exc:
                summary.status = "telemetry_failed"
                summary.status_detail = str(exc)
                return summary

        durable_edge, durable_evidence = next_durable_edge, next_durable_evidence
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
    return _sync_relation_pass(_token=token, lamin_instance=lamin_instance, **kwargs)


def sync_relation_to_lamindb(*, kg_root: str | Path, relation: str, edge_limit: int = DEFAULT_EDGE_LIMIT, evidence_limit: int = DEFAULT_EVIDENCE_LIMIT, edge_offset: int = 0, evidence_offset: int = 0, chunk_size: int = DEFAULT_CHUNK_SIZE, resume_chunk: int = 0, max_chunks: int | None = None, batch_size: int = DEFAULT_BATCH_SIZE, lamin_instance: str = _EXPECTED_INSTANCE, write: bool = False, idempotence_passes: int = 1, verify_selected_live: bool = False, telemetry_path: str | Path | None = None, run_id: str | None = None, task_id: str | None = None) -> LiveEdgeSyncSummary:
    if idempotence_passes < 1:
        raise ValueError("idempotence_passes must be >= 1")
    window = RelationWindow(relation, edge_offset, edge_limit, evidence_offset, evidence_limit, chunk_size)
    effective_run_id = run_id or uuid.uuid4().hex
    if not effective_run_id.strip():
        raise ValueError("run_id must be non-empty")
    common: dict[str, Any] = dict(kg_root=kg_root, window=window, write=write, resume_chunk=resume_chunk, max_chunks=max_chunks, batch_size=batch_size, verify_selected_live=verify_selected_live, telemetry_path=Path(telemetry_path) if telemetry_path else None, run_id=effective_run_id, task_id=task_id, sync_pass_index=0)
    if not write:
        return _sync_relation_pass(**common)
    if not verify_selected_live:
        raise RuntimeError("fail closed: write requires verify_selected_live=True")
    if telemetry_path is None:
        raise RuntimeError("fail closed: write requires a durable telemetry_path")
    _connect_lamin(lamin_instance)
    _configure_sqlite_timeout()
    with _single_writer_guard(lamin_instance) as token:
        summary = _sync_relation_with_token(lamin_instance=lamin_instance, token=token, **common)
        summary.idempotence_passes = idempotence_passes
        for sync_pass_index in range(1, idempotence_passes):
            summary = _sync_relation_with_token(lamin_instance=lamin_instance, token=token, **{**common, "sync_pass_index": sync_pass_index})
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
    parser.add_argument("--run-id", help="stable operator-supplied identity persisted on every telemetry record")
    parser.add_argument("--task-id", help="operator task identity persisted in per-chunk stage telemetry")
    parser.add_argument("--lamin-instance", default=_EXPECTED_INSTANCE)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summaries = sync_parquet_edges_to_lamindb(args.kg_root, relations=args.relations or list(DEFAULT_RELATIONS), edge_offset=args.edge_offset, edge_limit=args.edge_limit, evidence_offset=args.evidence_offset, evidence_limit=args.evidence_limit, chunk_size=args.chunk_size, resume_chunk=args.resume_chunk, max_chunks=args.max_chunks, batch_size=args.batch_size, verify_selected_live=args.verify_selected_live, telemetry_path=args.progress_jsonl, run_id=args.run_id, task_id=args.task_id, lamin_instance=args.lamin_instance, write=args.write)
    print(summaries_to_json(summaries) if args.json else pd.DataFrame([asdict(item) for item in summaries]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
