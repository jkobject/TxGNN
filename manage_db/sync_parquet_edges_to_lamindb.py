"""Bounded live sync of canonical KG edge/evidence Parquets into LaminDB.

Production-safety defaults:
- dry-run unless ``--write`` is passed;
- reads canonical KG Parquets and never writes KG Parquet outputs;
- supports explicit per-relation windows, chunking, resume, and idempotence
  passes for bounded live syncs;
- uses deterministic exact-ID keys from :mod:`manage_db.kg_edge_pilot`;
- writes through the live ``lnschema_txgnn.KGEdge`` and
  ``lnschema_txgnn.KGEdgeEvidence`` ORM models with schema-safe Django bulk
  upserts, never through local pilot SQLite.

This module is intentionally separate from ``kg_edge_pilot`` so reviewers can
see whether a run touched the live LaminDB instance or only the local review
fixture.
"""

from __future__ import annotations

import argparse
import contextlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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

EDGE_UPDATE_FIELDS = [
    "x_id",
    "x_type",
    "y_id",
    "y_type",
    "relation",
    "display_relation",
    "source",
    "credibility",
    "metadata",
]
EVIDENCE_UPDATE_FIELDS = [
    "edge_key",
    "relation",
    "x_id",
    "x_type",
    "y_id",
    "y_type",
    "evidence_type",
    "source",
    "source_dataset",
    "source_record_id",
    "paper_id",
    "dataset_id",
    "study_id",
    "evidence_score",
    "predicate",
    "direction",
    "metadata",
]


@dataclass(frozen=True)
class RelationWindow:
    """Source window selected for one relation."""

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
    edge_existing_before: int | None = None
    evidence_existing_before: int | None = None
    edge_count_after: int | None = None
    evidence_count_after: int | None = None
    edge_upserts: int = 0
    evidence_upserts: int = 0
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
    edge_existing_before: int | None = None
    evidence_existing_before: int | None = None
    edge_count_after: int | None = None
    evidence_count_after: int | None = None
    edge_upserts: int = 0
    evidence_upserts: int = 0
    selected_live_edges_found: int | None = None
    selected_live_evidence_found: int | None = None
    source_live_mismatch_count: int | None = None
    chunks: list[LiveEdgeSyncChunk] = field(default_factory=list)
    status: str = "dry_run"
    status_detail: str | None = None


def _registry_models() -> tuple[Any, Any]:
    import lnschema_txgnn as txs

    return txs.KGEdge, txs.KGEdgeEvidence


def _transaction_atomic():
    try:
        from django.db import transaction
    except Exception:  # pragma: no cover - only used without Django installed
        return contextlib.nullcontext()
    return transaction.atomic()


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
        value.pop("edge_key", None)
        value.pop("evidence_key", None)
        return value or None
    text = str(value)
    if not text:
        return None
    payload = json.loads(text)
    if isinstance(payload, dict):
        payload.pop("edge_key", None)
        payload.pop("evidence_key", None)
        return payload or None
    return {"value": payload}


def _row_dict(row: Mapping[str, Any], *, base_columns: Iterable[str], metadata_column: str = "metadata_json") -> dict[str, Any]:
    base = list(base_columns)
    out = {column: _clean_value(row.get(column)) for column in base}
    out["metadata"] = _metadata_dict(row.get(metadata_column))
    return out


def _edge_defaults(row: Mapping[str, Any]) -> dict[str, Any]:
    return _row_dict(row, base_columns=kg_edge_pilot.EDGE_BASE_COLUMNS)


def _evidence_defaults(row: Mapping[str, Any]) -> dict[str, Any]:
    return _row_dict(row, base_columns=kg_edge_pilot.EVIDENCE_BASE_COLUMNS)


def _empty_frame_for_parquet(parquet_file: pq.ParquetFile) -> pd.DataFrame:
    try:
        return pd.DataFrame(columns=list(parquet_file.schema_arrow.names))
    except Exception:  # pragma: no cover - defensive for non-standard ParquetFile doubles
        return pd.DataFrame()


def _read_limited_parquet(
    kg_root: str | Path,
    subdir: str,
    name: str,
    limit: int,
    offset: int = 0,
    *,
    batch_size: int = DEFAULT_SOURCE_BATCH_SIZE,
) -> tuple[pd.DataFrame, int]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit < 0:
        raise ValueError("limit must be >= 0; use 0 for all rows from offset")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    root = kg_storage.open_kg_root(str(kg_root))
    path = root._join(subdir, f"{name}.parquet")
    if not root.fs.exists(path):
        return pd.DataFrame(), 0
    with root.fs.open(path, "rb") as handle:
        parquet_file = pq.ParquetFile(handle)
        total_rows = int(parquet_file.metadata.num_rows)
        if offset >= total_rows:
            return _empty_frame_for_parquet(parquet_file), total_rows

        selected_batches: list[pa.RecordBatch] = []
        rows_seen = 0
        rows_selected = 0
        bounded_limit = None if int(limit) == 0 else int(limit)

        for record_batch in parquet_file.iter_batches(batch_size=batch_size):
            batch_rows = int(record_batch.num_rows)
            batch_start = rows_seen
            batch_end = batch_start + batch_rows
            rows_seen = batch_end

            if batch_end <= offset:
                continue
            if bounded_limit is not None and rows_selected >= bounded_limit:
                break

            start_in_batch = max(0, int(offset) - batch_start)
            available = batch_rows - start_in_batch
            if available <= 0:
                continue
            take = available if bounded_limit is None else min(available, bounded_limit - rows_selected)
            if take <= 0:
                break
            selected_batches.append(record_batch.slice(start_in_batch, take))
            rows_selected += take
            if bounded_limit is not None and rows_selected >= bounded_limit:
                break

        if not selected_batches:
            return _empty_frame_for_parquet(parquet_file), total_rows
        return pa.Table.from_batches(selected_batches).to_pandas(), total_rows


def build_edge_frame(kg_root: str | Path, relation: str, *, limit: int, offset: int = 0) -> tuple[pd.DataFrame, int]:
    frame, total = _read_limited_parquet(kg_root, "edges", relation, limit, offset)
    if frame.empty:
        return pd.DataFrame(columns=["edge_key", *kg_edge_pilot.EDGE_BASE_COLUMNS, "metadata_json"]), total
    missing = [col for col in ["x_id", "x_type", "y_id", "y_type", "relation"] if col not in frame.columns]
    if missing:
        raise ValueError(f"edges/{relation}.parquet missing required edge columns: {missing}")
    frame = frame.copy()
    frame["edge_key"] = [
        kg_edge_pilot.edge_key_for(
            relation=str(row["relation"]),
            x_type=str(row["x_type"]),
            x_id=str(row["x_id"]),
            y_type=str(row["y_type"]),
            y_id=str(row["y_id"]),
        )
        for _, row in frame.iterrows()
    ]
    for col in kg_edge_pilot.EDGE_BASE_COLUMNS:
        if col not in frame.columns:
            frame[col] = None
    frame["metadata_json"] = [kg_edge_pilot._metadata_json(row, [*kg_edge_pilot.EDGE_BASE_COLUMNS, "edge_key"]) for _, row in frame.iterrows()]
    return frame[["edge_key", *kg_edge_pilot.EDGE_BASE_COLUMNS, "metadata_json"]], total


def build_evidence_frame(kg_root: str | Path, relation: str, *, limit: int, offset: int = 0) -> tuple[pd.DataFrame, int]:
    frame, total = _read_limited_parquet(kg_root, "evidence", relation, limit, offset)
    if frame.empty:
        return pd.DataFrame(columns=["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"]), total
    frame = frame.copy()
    for col in kg_edge_pilot.EVIDENCE_BASE_COLUMNS:
        if col not in frame.columns:
            frame[col] = None
    frame["edge_key"] = [
        kg_edge_pilot.edge_key_for(
            relation=str(row["relation"]),
            x_type=str(row["x_type"]),
            x_id=str(row["x_id"]),
            y_type=str(row["y_type"]),
            y_id=str(row["y_id"]),
        )
        for _, row in frame.iterrows()
    ]
    # Evidence keys must be stable across resumed windows. Include the absolute
    # source-row ordinal rather than the index inside the sliced frame.
    frame["evidence_key"] = [kg_edge_pilot.evidence_key_for(row, ordinal=offset + i) for i, (_, row) in enumerate(frame.iterrows())]
    frame["metadata_json"] = [kg_edge_pilot._metadata_json(row, kg_edge_pilot.EVIDENCE_BASE_COLUMNS) for _, row in frame.iterrows()]
    return frame[["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"]], total


def _clean_records(frame: pd.DataFrame, defaults_fn, key_field: str) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    rows = frame.where(pd.notna(frame), None).to_dict(orient="records")
    records: list[dict[str, Any]] = []
    for row in rows:
        key = _clean_value(row.get(key_field))
        if key is None:
            continue
        record = defaults_fn(row)
        record[key_field] = key
        records.append(record)
    return records


def _bulk_upsert_rows(
    model: Any,
    key_field: str,
    rows: Sequence[Mapping[str, Any]],
    defaults_fn,
    *,
    update_fields: Sequence[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    records = _clean_records(pd.DataFrame(rows), defaults_fn, key_field)
    if not records:
        return 0
    objects = [model(**record) for record in records]
    _db_retry(
        f"bulk upsert {model.__module__}.{model.__name__} {len(objects)} rows",
        lambda: model.objects.bulk_create(
            objects,
            batch_size=batch_size,
            update_conflicts=True,
            update_fields=list(update_fields),
            unique_fields=[key_field],
        ),
    )
    return len(objects)


def _relation_count(model: Any, relation: str) -> int:
    value = _db_retry(
        f"count {model.__module__}.{model.__name__} {relation}",
        lambda model=model, relation=relation: model.objects.filter(relation=relation).count(),
    )
    return int(value or 0)


def _count_existing_keys(model: Any, key_field: str, keys: Sequence[str], *, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    total = 0
    for start in range(0, len(keys), batch_size):
        batch = list(keys[start : start + batch_size])
        if not batch:
            continue
        total += int(_db_retry(f"count existing {model.__name__} keys", lambda batch=batch: model.objects.filter(**{f"{key_field}__in": batch}).count()) or 0)
    return total


def _fetch_by_keys(model: Any, key_field: str, keys: Sequence[str], values: Sequence[str], *, batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(keys), batch_size):
        batch = list(keys[start : start + batch_size])
        if batch:
            rows.extend(list(_db_retry(f"fetch {model.__name__} keys", lambda batch=batch: model.objects.filter(**{f"{key_field}__in": batch}).values(*values)) or []))
    return rows


def _chunk_windows(offset: int, limit: int, chunk_size: int) -> list[tuple[int, int]]:
    if limit < 0:
        raise ValueError("limit must be >= 0; use 0 for all rows")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if limit == 0:
        return [(offset, 0)]
    chunks: list[tuple[int, int]] = []
    pos = offset
    remaining = limit
    while remaining > 0:
        size = min(chunk_size, remaining)
        chunks.append((pos, size))
        pos += size
        remaining -= size
    return chunks


def _aligned_chunk_windows(window: RelationWindow) -> list[tuple[int, int, int, int]]:
    edge_chunks = (
        _chunk_windows(window.edge_offset, window.edge_limit, window.chunk_size)
        if window.edge_limit >= 0
        else []
    )
    evidence_chunks = (
        _chunk_windows(window.evidence_offset, window.evidence_limit, window.chunk_size)
        if window.evidence_limit >= 0
        else []
    )
    if window.edge_limit == 0 and window.evidence_limit == 0:
        return [(window.edge_offset, 0, window.evidence_offset, 0)]
    max_len = max(len(edge_chunks), len(evidence_chunks), 1)
    aligned = []
    for idx in range(max_len):
        edge_offset, edge_limit = edge_chunks[idx] if idx < len(edge_chunks) else (window.edge_offset + window.edge_limit, -1)
        evidence_offset, evidence_limit = evidence_chunks[idx] if idx < len(evidence_chunks) else (window.evidence_offset + window.evidence_limit, -1)
        aligned.append((edge_offset, edge_limit, evidence_offset, evidence_limit))
    return aligned


def _source_live_mismatches(source: Mapping[str, Mapping[str, Any]], live_rows: Sequence[Mapping[str, Any]], key_field: str, fields: Sequence[str]) -> int:
    mismatches = 0
    for live in live_rows:
        src = source.get(str(live.get(key_field)))
        if src is None:
            mismatches += 1
            continue
        for field_name in fields:
            src_val = _clean_value(src.get(field_name))
            live_val = _clean_value(live.get(field_name))
            if live_val != src_val:
                mismatches += 1
    return mismatches


def compare_selected_live_to_source(kg_root: str | Path, window: RelationWindow) -> dict[str, int]:
    """Compare selected source-window rows to currently live LaminDB rows."""

    KGEdge, KGEdgeEvidence = _registry_models()
    edge_frame, edge_total = build_edge_frame(
        kg_root,
        window.relation,
        limit=window.edge_limit,
        offset=window.edge_offset,
    )
    if window.evidence_limit < 0:
        evidence_frame = pd.DataFrame(
            columns=["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"]
        )
        evidence_total = 0
    else:
        evidence_frame, evidence_total = build_evidence_frame(
            kg_root,
            window.relation,
            limit=window.evidence_limit,
            offset=window.evidence_offset,
        )
    source_edges = {str(row["edge_key"]): row for row in edge_frame.to_dict(orient="records")}
    source_evidence = {str(row["evidence_key"]): row for row in evidence_frame.to_dict(orient="records")}
    live_edges = _fetch_by_keys(
        KGEdge,
        "edge_key",
        list(source_edges),
        ["edge_key", "x_id", "x_type", "y_id", "y_type", "relation", "source", "credibility"],
    )
    live_evidence = _fetch_by_keys(
        KGEdgeEvidence,
        "evidence_key",
        list(source_evidence),
        ["evidence_key", "edge_key", "x_id", "x_type", "y_id", "y_type", "relation", "source", "source_dataset", "source_record_id", "evidence_score", "predicate", "direction"],
    )
    return {
        "source_edge_rows_total": int(edge_total),
        "source_edge_rows_selected": len(source_edges),
        "source_evidence_rows_total": int(evidence_total),
        "source_evidence_rows_selected": len(source_evidence),
        "selected_live_edges_found": len(live_edges),
        "selected_live_evidence_found": len(live_evidence),
        "missing_selected_live_edges": len(source_edges) - len(live_edges),
        "missing_selected_live_evidence": len(source_evidence) - len(live_evidence),
        "edge_mismatch_count": _source_live_mismatches(source_edges, live_edges, "edge_key", ["x_id", "x_type", "y_id", "y_type", "relation", "source", "credibility"]),
        "evidence_mismatch_count": _source_live_mismatches(source_evidence, live_evidence, "evidence_key", ["edge_key", "x_id", "x_type", "y_id", "y_type", "relation", "source", "source_dataset", "source_record_id", "evidence_score", "predicate", "direction"]),
    }


def _sync_relation_pass(
    *,
    kg_root: str | Path,
    window: RelationWindow,
    write: bool,
    resume_chunk: int,
    max_chunks: int | None,
    batch_size: int,
) -> LiveEdgeSyncSummary:
    if resume_chunk < 0:
        raise ValueError("resume_chunk must be >= 0")
    KGEdge, KGEdgeEvidence = _registry_models() if write else (None, None)
    edge_frame_all, edge_total = build_edge_frame(
        kg_root,
        window.relation,
        limit=window.edge_limit,
        offset=window.edge_offset,
    )
    if window.evidence_limit < 0:
        evidence_frame_all = pd.DataFrame(
            columns=["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"]
        )
        evidence_total = 0
    else:
        evidence_frame_all, evidence_total = build_evidence_frame(
            kg_root,
            window.relation,
            limit=window.evidence_limit,
            offset=window.evidence_offset,
        )
    summary = LiveEdgeSyncSummary(
        relation=window.relation,
        edge_offset=window.edge_offset,
        edge_limit=window.edge_limit,
        evidence_offset=window.evidence_offset,
        evidence_limit=window.evidence_limit,
        chunk_size=window.chunk_size,
        resume_chunk=resume_chunk,
        max_chunks=max_chunks,
        edge_rows_available=int(edge_total),
        edge_rows_selected=len(edge_frame_all),
        evidence_rows_available=int(evidence_total),
        evidence_rows_selected=len(evidence_frame_all),
    )
    if not write:
        return summary

    summary.edge_existing_before = _relation_count(KGEdge, window.relation)
    summary.evidence_existing_before = _relation_count(KGEdgeEvidence, window.relation)
    aligned = _aligned_chunk_windows(window)[resume_chunk:]
    if max_chunks is not None:
        aligned = aligned[:max_chunks]
    for local_index, (edge_offset, edge_limit, evidence_offset, evidence_limit) in enumerate(aligned, start=resume_chunk):
        if edge_limit < 0:
            edge_frame, edge_rows_available = pd.DataFrame(columns=["edge_key", *kg_edge_pilot.EDGE_BASE_COLUMNS, "metadata_json"]), summary.edge_rows_available
        else:
            edge_frame, edge_rows_available = build_edge_frame(kg_root, window.relation, limit=edge_limit, offset=edge_offset)
        if evidence_limit < 0:
            evidence_frame, evidence_rows_available = pd.DataFrame(columns=["evidence_key", *kg_edge_pilot.EVIDENCE_BASE_COLUMNS, "metadata_json"]), summary.evidence_rows_available
        else:
            evidence_frame, evidence_rows_available = build_evidence_frame(kg_root, window.relation, limit=evidence_limit, offset=evidence_offset)
        edge_rows = edge_frame.where(pd.notna(edge_frame), None).to_dict(orient="records")
        evidence_rows = evidence_frame.where(pd.notna(evidence_frame), None).to_dict(orient="records")
        with _transaction_atomic():
            before_edges = _relation_count(KGEdge, window.relation)
            before_evidence = _relation_count(KGEdgeEvidence, window.relation)
            edge_upserts = _bulk_upsert_rows(
                KGEdge,
                "edge_key",
                edge_rows,
                _edge_defaults,
                update_fields=EDGE_UPDATE_FIELDS,
                batch_size=batch_size,
            )
            evidence_upserts = _bulk_upsert_rows(
                KGEdgeEvidence,
                "evidence_key",
                evidence_rows,
                _evidence_defaults,
                update_fields=EVIDENCE_UPDATE_FIELDS,
                batch_size=batch_size,
            )
            after_edges = _relation_count(KGEdge, window.relation)
            after_evidence = _relation_count(KGEdgeEvidence, window.relation)
        summary.edge_upserts += edge_upserts
        summary.evidence_upserts += evidence_upserts
        summary.chunks.append(
            LiveEdgeSyncChunk(
                relation=window.relation,
                chunk_index=local_index,
                edge_offset=edge_offset,
                edge_limit=edge_limit,
                evidence_offset=evidence_offset,
                evidence_limit=evidence_limit,
                edge_rows_available=int(edge_rows_available),
                edge_rows_selected=len(edge_rows),
                evidence_rows_available=int(evidence_rows_available),
                evidence_rows_selected=len(evidence_rows),
                edge_existing_before=before_edges,
                evidence_existing_before=before_evidence,
                edge_count_after=after_edges,
                evidence_count_after=after_evidence,
                edge_upserts=edge_upserts,
                evidence_upserts=evidence_upserts,
                status="bounded live sync bulk chunk accepted",
            )
        )
    summary.edge_count_after = _relation_count(KGEdge, window.relation)
    summary.evidence_count_after = _relation_count(KGEdgeEvidence, window.relation)
    summary.status = "bounded live sync bulk accepted"
    return summary


def sync_relation_to_lamindb(
    *,
    kg_root: str | Path,
    relation: str,
    edge_limit: int = DEFAULT_EDGE_LIMIT,
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
    skip_evidence: bool = False,
    edge_offset: int = 0,
    evidence_offset: int = 0,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    resume_chunk: int = 0,
    max_chunks: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    write: bool = False,
    idempotence_passes: int = 1,
    verify_selected_live: bool = False,
) -> LiveEdgeSyncSummary:
    """Sync one relation from canonical KG Parquets to live LaminDB models.

    ``write=False`` is a dry-run that reads the source Parquets and reports the
    selected row counts. ``write=True`` performs per-chunk idempotent Django
    bulk upserts keyed by ``edge_key``/``evidence_key``.
    """

    if idempotence_passes < 1:
        raise ValueError("idempotence_passes must be >= 1")
    window = RelationWindow(
        relation=relation,
        edge_offset=edge_offset,
        edge_limit=edge_limit,
        evidence_offset=evidence_offset,
        evidence_limit=-1 if skip_evidence else evidence_limit,
        chunk_size=chunk_size,
    )
    summary = _sync_relation_pass(
        kg_root=kg_root,
        window=window,
        write=write,
        resume_chunk=resume_chunk,
        max_chunks=max_chunks,
        batch_size=batch_size,
    )
    summary.idempotence_passes = idempotence_passes
    for _ in range(1, idempotence_passes):
        summary = _sync_relation_pass(
            kg_root=kg_root,
            window=window,
            write=write,
            resume_chunk=resume_chunk,
            max_chunks=max_chunks,
            batch_size=batch_size,
        )
        summary.idempotence_passes = idempotence_passes
    if verify_selected_live:
        comparison = compare_selected_live_to_source(kg_root, window)
        summary.selected_live_edges_found = comparison["selected_live_edges_found"]
        summary.selected_live_evidence_found = comparison["selected_live_evidence_found"]
        summary.source_live_mismatch_count = comparison["edge_mismatch_count"] + comparison["evidence_mismatch_count"]
        if comparison["missing_selected_live_edges"] or comparison["missing_selected_live_evidence"] or summary.source_live_mismatch_count:
            summary.status_detail = json.dumps(comparison, sort_keys=True)
    return summary


def sync_parquet_edges_to_lamindb(
    kg_root: str | Path = DEFAULT_KG_ROOT,
    *,
    relations: Sequence[str] = DEFAULT_RELATIONS,
    edge_limit: int = DEFAULT_EDGE_LIMIT,
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
    skip_evidence: bool = False,
    edge_offset: int = 0,
    evidence_offset: int = 0,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    resume_chunk: int = 0,
    max_chunks: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    lamin_instance: str | None = "jkobject/jouvencekb",
    write: bool = False,
    idempotence_passes: int = 1,
    verify_selected_live: bool = False,
) -> list[LiveEdgeSyncSummary]:
    _connect_lamin(lamin_instance)
    _configure_sqlite_timeout()
    summaries = []
    for relation in relations:
        summaries.append(
            sync_relation_to_lamindb(
                kg_root=kg_root,
                relation=relation,
                edge_limit=edge_limit,
                evidence_limit=evidence_limit,
                skip_evidence=skip_evidence,
                edge_offset=edge_offset,
                evidence_offset=evidence_offset,
                chunk_size=chunk_size,
                resume_chunk=resume_chunk,
                max_chunks=max_chunks,
                batch_size=batch_size,
                write=write,
                idempotence_passes=idempotence_passes,
                verify_selected_live=verify_selected_live,
            )
        )
    return summaries


def summaries_to_json(summaries: Sequence[LiveEdgeSyncSummary]) -> str:
    return json.dumps([asdict(item) for item in summaries], indent=2, sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded live lnschema_txgnn KGEdge/KGEdgeEvidence sync")
    parser.add_argument("kg_root", nargs="?", default=str(DEFAULT_KG_ROOT), help="Canonical KG root; read-only")
    parser.add_argument("--relation", action="append", dest="relations", help="Relation to sync; may be repeated")
    parser.add_argument("--edge-offset", type=int, default=0, help="First edge source row to select")
    parser.add_argument("--edge-limit", type=int, default=DEFAULT_EDGE_LIMIT, help="Maximum edge rows per relation; use 0 for all rows from offset")
    parser.add_argument("--evidence-offset", type=int, default=0, help="First evidence source row to select")
    parser.add_argument("--evidence-limit", type=int, default=DEFAULT_EVIDENCE_LIMIT, help="Maximum evidence rows per relation; use 0 for all rows from offset")
    parser.add_argument(
        "--skip-evidence",
        action="store_true",
        help="Explicitly skip evidence input for an edge-only manifest lane",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Maximum source rows per transaction chunk")
    parser.add_argument("--resume-chunk", type=int, default=0, help="Skip chunks before this 0-based chunk index")
    parser.add_argument("--max-chunks", type=int, default=None, help="Optional maximum number of chunks to process after resume")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Django bulk_create batch_size")
    parser.add_argument("--idempotence-passes", type=int, default=1, help="Repeat the selected write window N times; useful to verify no duplicate keys")
    parser.add_argument("--verify-selected-live", action="store_true", help="After the run, compare selected live rows to source rows by exact keys")
    parser.add_argument("--lamin-instance", default="jkobject/jouvencekb", help="LaminDB instance slug")
    parser.add_argument("--write", action="store_true", help="Perform live ORM upserts; default is dry-run")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summaries = sync_parquet_edges_to_lamindb(
        args.kg_root,
        relations=args.relations or list(DEFAULT_RELATIONS),
        edge_limit=args.edge_limit,
        evidence_limit=args.evidence_limit,
        skip_evidence=args.skip_evidence,
        edge_offset=args.edge_offset,
        evidence_offset=args.evidence_offset,
        chunk_size=args.chunk_size,
        resume_chunk=args.resume_chunk,
        max_chunks=args.max_chunks,
        batch_size=args.batch_size,
        lamin_instance=args.lamin_instance,
        write=args.write,
        idempotence_passes=args.idempotence_passes,
        verify_selected_live=args.verify_selected_live,
    )
    if args.json:
        print(summaries_to_json(summaries))
    else:
        print(pd.DataFrame([asdict(item) for item in summaries]).to_string(index=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
