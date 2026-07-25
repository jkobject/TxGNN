"""Batch sync KG node Parquets into LaminDB registries.

Production-safety defaults:
- dry-run unless ``--write`` is passed;
- reads only required Parquet columns;
- processes rows in bounded batches;
- checks registry existence with filtered ``field__in`` lookups instead of
  materializing whole LaminDB tables.
"""

from __future__ import annotations

import argparse
import json
import sys
import re
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from . import kg_storage
from .kg_ids import normalize_disease_id
from .kg_schema import NODE_TYPES, NodeType

try:
    from django.core.exceptions import ObjectDoesNotExist
    from django.db.utils import OperationalError
except Exception:  # pragma: no cover - django is available in LaminDB runtime
    ObjectDoesNotExist = Exception  # type: ignore[assignment]
    OperationalError = Exception  # type: ignore[assignment]

SUPPORTED_NODE_TYPES = {
    "enhancer",
    "mutation",
    "paper",
    "transcript",
    "protein",
    "disease",
    "gene",
    "molecule",
    "pathway",
    "tissue",
    "cell_type",
}

# Public bionty/pertdb write paths can resolve by names/symbols and mutate
# existing source-backed records instead of representing the exact KG primary
# ID. Keep them auditable in dry-run/parity mode, but block writes until a
# project-approved exact-ID insertion policy exists.
UNSAFE_PUBLIC_WRITE_REGISTRIES = {
    "bionty.Gene",
    "bionty.Pathway",
    "bionty.Tissue",
    "bionty.CellType",
    "pertdb.Compound",
}
DEFAULT_BATCH_SIZE = 50_000
LOOKUP_CHUNK_SIZE = 5_000
DEFAULT_BULK_CREATE_BATCH_SIZE = 1_000


@dataclass(frozen=True)
class RecordSpec:
    """A registry record candidate derived from one KG node row."""

    node_type: str
    node_id: str
    registry_name: str
    key_field: str
    key_value: str
    create_kwargs: dict[str, Any]


@dataclass
class SyncSummary:
    node_type: str
    registry: str | None
    key_field: str | None
    seen: int = 0
    existing: int = 0
    would_create: int = 0
    created: int = 0
    skipped: int = 0
    unsupported: int = 0
    status: str = "ok"
    status_detail: str | None = None

    @property
    def missing_or_created(self) -> int:
        return self.created or self.would_create


def _clean(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "<na>"}:
        return None
    return text


def _clean_int(value: object) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _clean_bool(value: object) -> bool:
    text = _clean(value)
    if text is None:
        return False
    return text.lower() in {"1", "true", "t", "yes", "y"}


def _first_clean(row: Mapping[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        if name in row:
            value = _clean(row[name])
            if value:
                return value
    return None


def _pmid_from_id(node_id: str) -> str:
    return node_id.removeprefix("PMID:")


_GNOMAD_LIKE_ID_RE = re.compile(r"^(?:chr)?[0-9XYMT]+[_:-]\d+[_:-][ACGTN]+[_:-][ACGTN]+$", re.IGNORECASE)


def _looks_like_gnomad_id(value: str) -> bool:
    return bool(_GNOMAD_LIKE_ID_RE.match(value))


def _row_to_record_spec(node_type: str, row: Mapping[str, Any]) -> RecordSpec | None:
    """Map one node parquet row to a LaminDB registry write candidate.

    This helper is intentionally LaminDB-free so it can be unit-tested without
    a configured instance.
    """

    node_id = _first_clean(row, ["id"])
    if node_id is None:
        return None

    if node_type == "mutation":
        rsid = node_id if node_id.startswith("rs") else _first_clean(row, ["rsid", "name"])
        if rsid and not rsid.startswith("rs"):
            rsid = None
        explicit_gnomad_id = _first_clean(row, ["gnomad_id"])
        gnomad_id = explicit_gnomad_id or (node_id if not node_id.startswith("rs") and _looks_like_gnomad_id(node_id) else None)
        create_kwargs = {
            "rsid": rsid,
            "hgvs": _first_clean(row, ["hgvs"]),
            "clinvar_id": _first_clean(row, ["clinvar_id"]),
            "gnomad_id": gnomad_id,
            "chromosome": _first_clean(row, ["chromosome", "chr"]),
            "position": _clean_int(row.get("position")),
            "ref_allele": _first_clean(row, ["ref_allele", "ref"]),
            "alt_allele": _first_clean(row, ["alt_allele", "alt"]),
            "consequence": _first_clean(row, ["consequence"]),
        }
        # Mutation.rsid is nullable, and OpenTargets can identify variants by
        # chr_pos_ref_alt IDs while carrying the dbSNP ID in ``name``. Use the
        # KG node ID itself as the existence key when it is gnomAD-like so
        # parity proves the Parquet node ID is represented, not merely a label.
        key_field = "rsid" if node_id.startswith("rs") else "gnomad_id"
        key_value = create_kwargs.get(key_field)
        if not key_value:
            return None
        return RecordSpec(
            node_type,
            node_id,
            "lnschema_txgnn.Mutation",
            key_field,
            str(key_value),
            create_kwargs,
        )

    if node_type == "paper":
        pmid = _pmid_from_id(node_id)
        create_kwargs = {
            "pmid": pmid,
            "doi": _first_clean(row, ["doi"]),
            "pmc_id": _first_clean(row, ["pmc_id", "pmcid"]),
            "arxiv_id": _first_clean(row, ["arxiv_id"]),
            "title": _first_clean(row, ["title", "name"]),
            "year": _clean_int(row.get("year")),
            "journal": _first_clean(row, ["journal"]),
            "abstract": _first_clean(row, ["abstract"]),
        }
        return RecordSpec(node_type, node_id, "lnschema_txgnn.Paper", "pmid", pmid, create_kwargs)

    if node_type == "transcript":
        if not node_id.startswith("ENST"):
            return None
        create_kwargs = {
            "ensembl_transcript_id": node_id,
            "ensembl_gene_id": _first_clean(row, ["ensembl_gene_id", "gene_id"]),
            "refseq_mrna": _first_clean(row, ["refseq_mrna"]),
            "ccds_id": _first_clean(row, ["ccds_id"]),
            "biotype": _first_clean(row, ["biotype", "transcript_biotype"]),
            "is_canonical": _clean_bool(row.get("is_canonical")),
        }
        return RecordSpec(
            node_type,
            node_id,
            "lnschema_txgnn.Transcript",
            "ensembl_transcript_id",
            node_id,
            create_kwargs,
        )

    if node_type == "protein":
        if not node_id.startswith("ENSP"):
            return None
        # TxGNN protein nodes are ENSP translation products. Use the custom
        # registry keyed by ensembl_protein_id; UniProt remains an xref.
        create_kwargs = {
            "ensembl_protein_id": node_id,
            "ensembl_gene_id": _first_clean(row, ["ensembl_gene_id", "gene_id"]),
            "uniprot_id": _first_clean(row, ["uniprot_id"]),
            "refseq_protein": _first_clean(row, ["refseq_protein"]),
            "pdb_ids": _first_clean(row, ["pdb_ids"]),
        }
        return RecordSpec(
            node_type,
            node_id,
            "lnschema_txgnn.Protein",
            "ensembl_protein_id",
            node_id,
            create_kwargs,
        )

    if node_type == "enhancer":
        encode_id = node_id if node_id.startswith("EH") else _first_clean(row, ["encode_id"])
        ensembl_regulatory_id = (
            node_id if node_id.startswith("ENSR") else _first_clean(row, ["ensembl_regulatory_id"])
        )
        if encode_id:
            key_field, key_value = "encode_id", encode_id
        elif ensembl_regulatory_id:
            key_field, key_value = "ensembl_regulatory_id", ensembl_regulatory_id
        else:
            return None
        create_kwargs = {
            "encode_id": encode_id,
            "ensembl_regulatory_id": ensembl_regulatory_id,
            "encode_experiment_id": _first_clean(row, ["encode_experiment_id"]),
            "chromosome": _first_clean(row, ["chromosome", "chr"]),
            "start_pos": _clean_int(row.get("start_pos", row.get("start"))),
            "end_pos": _clean_int(row.get("end_pos", row.get("end"))),
        }
        return RecordSpec(
            node_type,
            node_id,
            "lnschema_txgnn.Enhancer",
            key_field,
            str(key_value),
            create_kwargs,
        )

    if node_type == "disease":
        normalized_id = normalize_disease_id(node_id)
        if not normalized_id:
            return None
        name = _first_clean(row, ["name", "label", "disease_name"])
        if name == node_id:
            name = normalized_id
        source_ontology = normalized_id.split(":", 1)[0] if ":" in normalized_id else None
        create_kwargs = {
            "ontology_id": normalized_id,
            "source_ontology": source_ontology,
            "name": name,
        }
        for key in ["mondo_id", "hp_id"]:
            normalized_xref = normalize_disease_id(row.get(key))
            if normalized_xref:
                create_kwargs[key] = normalized_xref
        for key in ["omim_id", "doid_id", "icd10_code", "mesh_id"]:
            value = _first_clean(row, [key])
            if value:
                create_kwargs[key] = value
        return RecordSpec(
            node_type,
            normalized_id,
            "lnschema_txgnn.Disease",
            "ontology_id",
            normalized_id,
            create_kwargs,
        )

    if node_type == "gene":
        symbol = _first_clean(row, ["gene_name", "symbol", "name", "label"])
        create_kwargs = {"ensembl_gene_id": node_id, "symbol": symbol, "name": _first_clean(row, ["name", "label"])}
        if _first_clean(row, ["ncbi_gene_id"]):
            create_kwargs["ncbi_gene_id"] = _first_clean(row, ["ncbi_gene_id"])
        if _first_clean(row, ["hgnc_id"]):
            create_kwargs["hgnc_id"] = _first_clean(row, ["hgnc_id"])
        if _first_clean(row, ["uniprot_id"]):
            create_kwargs["uniprot_id"] = _first_clean(row, ["uniprot_id"])
        return RecordSpec(
            node_type, node_id, "lnschema_txgnn.Gene", "ensembl_gene_id", node_id, create_kwargs
        )

    if node_type == "molecule":
        name = _first_clean(row, ["name", "label", "molecule_name"])
        create_kwargs = {
            "chembl_id": node_id,
            "ontology_id": node_id,
            "name": name or node_id,
            # Avoid pertdb's optional RDKit SMILES processing during parity
            # backfills; canonical KG keeps SMILES in Parquet, while registry
            # parity only requires the ChEMBL primary ID representation.
            "inchikey": _first_clean(row, ["inchikey"]),
        }
        return RecordSpec(node_type, node_id, "lnschema_txgnn.Molecule", "chembl_id", node_id, create_kwargs)

    if node_type in {"pathway", "tissue", "cell_type"}:
        registry_by_node_type = {
            "pathway": "lnschema_txgnn.Pathway",
            "tissue": "lnschema_txgnn.Tissue",
            "cell_type": "lnschema_txgnn.CellType",
        }
        name = _first_clean(row, ["name", "label"]) or node_id
        create_kwargs = {"ontology_id": node_id, "name": name}
        return RecordSpec(
            node_type,
            node_id,
            registry_by_node_type[node_type],
            "ontology_id",
            node_id,
            create_kwargs,
        )

    return None


def _columns_for_node_type(node_type: str) -> list[str]:
    cols = {"id"}
    try:
        cols.update(NODE_TYPES[NodeType(node_type)].xref_columns)
    except ValueError:
        pass
    # Optional metadata columns used when present.
    cols.update(
        {
            "name",
            "label",
            "gene_name",
            "symbol",
            "disease_name",
            "molecule_name",
            "title",
            "year",
            "journal",
            "abstract",
            "biotype",
            "transcript_biotype",
            "is_canonical",
            "chromosome",
            "chr",
            "position",
            "ref_allele",
            "alt_allele",
            "ref",
            "alt",
            "consequence",
            "encode_id",
            "ensembl_regulatory_id",
            "encode_experiment_id",
            "start",
            "end",
            "start_pos",
            "end_pos",
        }
    )
    return sorted(cols)


def _available_columns(path: str, fs) -> set[str]:
    with fs.open(path, "rb") as fh:
        parquet_file = pq.ParquetFile(fh)
        return set(parquet_file.schema_arrow.names)


def _iter_node_batches(
    root: kg_storage.KGRoot,
    node_type: str,
    batch_size: int,
    row_offset: int = 0,
) -> Iterator[pd.DataFrame]:
    if row_offset < 0:
        raise ValueError("row_offset must be >= 0")
    path = root._node_internal(node_type)
    wanted = [col for col in _columns_for_node_type(node_type) if col in _available_columns(path, root.fs)]
    if "id" not in wanted:
        raise ValueError(f"nodes/{node_type}.parquet missing required column: id")
    with root.fs.open(path, "rb") as fh:
        parquet_file = pq.ParquetFile(fh)
        remaining_offset = row_offset
        for record_batch in parquet_file.iter_batches(batch_size=batch_size, columns=wanted):
            if remaining_offset >= record_batch.num_rows:
                remaining_offset -= record_batch.num_rows
                continue
            if remaining_offset:
                record_batch = record_batch.slice(remaining_offset)
                remaining_offset = 0
            yield record_batch.to_pandas()


def _registry_models() -> dict[str, Any]:
    import bionty as bt
    import pertdb as pt
    import lnschema_txgnn as txs

    return {
        "bionty.Gene": bt.Gene,
        "bionty.Pathway": bt.Pathway,
        "bionty.Tissue": bt.Tissue,
        "bionty.CellType": bt.CellType,
        "pertdb.Compound": pt.Compound,
        "lnschema_txgnn.Gene": txs.Gene,
        "lnschema_txgnn.Molecule": txs.Molecule,
        "lnschema_txgnn.Pathway": txs.Pathway,
        "lnschema_txgnn.Tissue": txs.Tissue,
        "lnschema_txgnn.CellType": txs.CellType,
        "lnschema_txgnn.Disease": txs.Disease,
        "lnschema_txgnn.Mutation": txs.Mutation,
        "lnschema_txgnn.Paper": txs.Paper,
        "lnschema_txgnn.Transcript": txs.Transcript,
        "lnschema_txgnn.Protein": txs.Protein,
        "lnschema_txgnn.Enhancer": txs.Enhancer,
    }




def _human_organism():
    import bionty as bt

    return (
        bt.Organism.objects.filter(name__iexact="human").first()
        or bt.Organism.objects.filter(ontology_id="NCBITaxon:9606").first()
    )

def _current_lamin_slug() -> str | None:
    try:
        import lamindb as ln

        instance = getattr(ln.setup.settings, "instance", None)
        return getattr(instance, "slug", None)
    except Exception:
        return None


def _connect_lamin(lamin_instance: str | None) -> None:
    import lamindb as ln

    if lamin_instance and _current_lamin_slug() != lamin_instance:
        ln.connect(lamin_instance)
    _configure_sqlite_timeout()


def _configure_sqlite_timeout(timeout_ms: int = 600_000) -> None:
    try:
        from django.db import connection

        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA busy_timeout = {int(timeout_ms)}")
    except Exception:
        pass


def _is_locked(exc: BaseException) -> bool:
    return "database is locked" in str(exc).lower()


def _db_retry(label: str, func, retries: int = 10, delay: float = 2.0, max_delay: float = 60.0):
    wait = delay
    for attempt in range(1, retries + 1):
        try:
            return func()
        except Exception as exc:
            if _is_locked(exc) and attempt < retries:
                print(f"{label}: database locked, retrying in {wait:.1f}s ({attempt}/{retries})")
                time.sleep(wait)
                wait = min(wait * 2, max_delay)
                continue
            raise



def _registry_table_name(model: Any) -> str | None:
    meta = getattr(model, "_meta", None)
    return getattr(meta, "db_table", None)


def _is_missing_registry_table_error(model: Any, exc: BaseException) -> bool:
    """Return True only for DB errors caused by an absent registry table."""

    text = str(exc).lower()
    if not any(marker in text for marker in ("no such table", "does not exist")):
        return False

    table = _registry_table_name(model)
    if table:
        return table.lower() in text

    return "no such table" in text


def _schema_pending_message(model: Any) -> str:
    table = _registry_table_name(model)
    model_name = f"{model.__module__}.{model.__name__}"
    if table:
        return f"missing registry table {table} for {model_name}; apply the LaminDB schema migration before --write"
    return f"missing registry table for {model_name}; apply the LaminDB schema migration before --write"

def _model_has_field(model: Any, field_name: str) -> bool:
    return any(getattr(field, "name", None) == field_name for field in model._meta.fields)


def _choose_existing_lookup_field(model: Any, spec: RecordSpec) -> str | None:
    for candidate in [spec.key_field, "stable_id", "ontology_id", "name"]:
        if candidate and _model_has_field(model, candidate):
            return candidate
    return None


def _existing_keys(model: Any, field_name: str, values: Iterable[str]) -> set[str]:
    values_list = [value for value in values if value]
    found: set[str] = set()
    for start in range(0, len(values_list), LOOKUP_CHUNK_SIZE):
        chunk = values_list[start : start + LOOKUP_CHUNK_SIZE]
        rows = _db_retry(
            f"lookup {model.__module__}.{model.__name__}.{field_name}",
            lambda model=model, field_name=field_name, chunk=chunk: list(
                model.objects.filter(**{f"{field_name}__in": chunk}).values_list(field_name, flat=True)
            ),
        )
        found.update(str(value) for value in rows if value is not None)
    return found


def _drop_unknown_fields(model: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    valid = {field.name for field in model._meta.fields}
    return {key: value for key, value in kwargs.items() if key in valid and value is not None}


def _create_record(model: Any, spec: RecordSpec, kwargs: dict[str, Any]):
    # For KG parity we must represent the exact canonical Parquet node ID.
    # bionty.from_source can legally resolve by aliases/symbols and mutate an
    # existing source-backed row (for example an ENSG request can hit a same
    # symbol NCBI gene row).  Missing parity rows therefore use direct inserts
    # with the KG primary ID after the filtered existence lookup has proven that
    # exact ID is absent.  Disease is intentionally custom lnschema_txgnn.Disease
    # and should not reach this bionty.Disease guard.
    if spec.registry_name == "bionty.Disease":
        return None

    safe_kwargs = _drop_unknown_fields(model, kwargs)
    return _db_retry(
        f"save {spec.registry_name} {spec.key_value}",
        lambda model=model, safe_kwargs=safe_kwargs: model(**safe_kwargs).save(),
    )



def _can_bulk_create_direct(spec: RecordSpec) -> bool:
    """Return True for registries safe to insert without source resolution hooks.

    Custom lnschema_txgnn records are simple SQLRecord subclasses keyed by a
    unique identifier already present in the KG node parquet. Bionty/pertdb
    records may need ontology/source-specific constructors, so keep those on
    the existing per-record path.
    """

    return spec.registry_name.startswith("lnschema_txgnn.")


def _bulk_create_records(
    model: Any,
    specs: list[RecordSpec],
    *,
    bulk_create_batch_size: int,
) -> int:
    if not specs:
        return 0
    records = [model(**_drop_unknown_fields(model, spec.create_kwargs)) for spec in specs]
    _db_retry(
        f"bulk_create {model.__module__}.{model.__name__} {len(records)} records",
        lambda model=model, records=records, bulk_create_batch_size=bulk_create_batch_size: model.objects.bulk_create(
            records,
            batch_size=bulk_create_batch_size,
        ),
    )
    return len(records)


def _reconcile_mutation_xref_collisions(model: Any, missing: dict[str, RecordSpec]) -> set[str]:
    """Attach missing gnomAD-like KG IDs to existing rsID mutation rows.

    OpenTargets pharmacogenomics can use a chr_pos_ref_alt node ID and carry
    the dbSNP rsID as metadata. If the rsID row already exists, creating a new
    custom Mutation with the same unique ``rsid`` would fail; updating the xref
    preserves one biological variant record while making the KG node ID auditable
    through ``gnomad_id``.
    """

    rsid_to_spec = {
        str(spec.create_kwargs["rsid"]): spec
        for spec in missing.values()
        if spec.registry_name == "lnschema_txgnn.Mutation"
        and spec.key_field == "gnomad_id"
        and spec.create_kwargs.get("rsid")
    }
    if not rsid_to_spec:
        return set()

    reconciled: set[str] = set()
    rsids = list(rsid_to_spec)
    for start in range(0, len(rsids), LOOKUP_CHUNK_SIZE):
        chunk = rsids[start : start + LOOKUP_CHUNK_SIZE]
        records = _db_retry(
            f"lookup {model.__module__}.{model.__name__}.rsid",
            lambda model=model, chunk=chunk: list(model.objects.filter(rsid__in=chunk)),
        )
        for record in records:
            rsid = str(getattr(record, "rsid", ""))
            spec = rsid_to_spec.get(rsid)
            if spec is None:
                continue
            current_gnomad_id = _clean(getattr(record, "gnomad_id", None))
            if current_gnomad_id and current_gnomad_id != spec.key_value:
                continue
            if current_gnomad_id != spec.key_value:
                setattr(record, "gnomad_id", spec.key_value)
                _db_retry(
                    f"update {model.__module__}.{model.__name__}.gnomad_id {spec.key_value}",
                    lambda record=record: record.save(update_fields=["gnomad_id"]),
                )
            reconciled.add(spec.key_value)
    return reconciled


def _drop_conflicting_mutation_rsids(model: Any, specs: list[RecordSpec]) -> None:
    """Mutate create kwargs so bulk-create respects Mutation.rsid uniqueness."""

    rsids = [
        str(spec.create_kwargs["rsid"])
        for spec in specs
        if spec.registry_name == "lnschema_txgnn.Mutation"
        and spec.key_field == "gnomad_id"
        and spec.create_kwargs.get("rsid")
    ]
    if not rsids:
        return

    existing_rsids: set[str] = set()
    unique_rsids = sorted(set(rsids))
    for start in range(0, len(unique_rsids), LOOKUP_CHUNK_SIZE):
        chunk = unique_rsids[start : start + LOOKUP_CHUNK_SIZE]
        rows = _db_retry(
            f"lookup {model.__module__}.{model.__name__}.rsid",
            lambda model=model, chunk=chunk: list(
                model.objects.filter(rsid__in=chunk).values_list("rsid", flat=True)
            ),
        )
        existing_rsids.update(str(value) for value in rows if value is not None)

    kept_new_rsids: set[str] = set()
    for spec in specs:
        if not (
            spec.registry_name == "lnschema_txgnn.Mutation"
            and spec.key_field == "gnomad_id"
            and spec.create_kwargs.get("rsid")
        ):
            continue
        rsid = str(spec.create_kwargs["rsid"])
        if rsid in existing_rsids or rsid in kept_new_rsids:
            spec.create_kwargs["rsid"] = None
        else:
            kept_new_rsids.add(rsid)

def _process_specs(
    specs: list[RecordSpec],
    *,
    registry_models: dict[str, Any] | None,
    write: bool,
    summary: SyncSummary,
    bulk_create_batch_size: int = DEFAULT_BULK_CREATE_BATCH_SIZE,
) -> None:
    if not specs:
        return
    if registry_models is None:
        summary.would_create += len({(s.registry_name, s.key_field, s.key_value) for s in specs})
        return

    if write and specs[0].registry_name in UNSAFE_PUBLIC_WRITE_REGISTRIES:
        summary.skipped += len({(s.registry_name, s.key_field, s.key_value) for s in specs})
        summary.status = "blocked"
        summary.status_detail = (
            summary.status_detail
            or "public registry write path may resolve by name/symbol and mutate existing IDs; exact-ID parity policy required"
        )
        return

    model = registry_models[specs[0].registry_name]
    lookup_field = _choose_existing_lookup_field(model, specs[0])
    if lookup_field is None:
        summary.skipped += len(specs)
        return

    # Re-key by the actual lookup field because bionty.Gene may prefer stable_id
    # in some LaminDB versions while KG rows use ensembl_gene_id.
    unique_by_lookup: dict[str, RecordSpec] = {}
    for spec in specs:
        lookup_value = str(spec.create_kwargs.get(lookup_field) or spec.key_value)
        if lookup_value:
            unique_by_lookup[lookup_value] = spec

    try:
        existing = _existing_keys(model, lookup_field, unique_by_lookup.keys())
    except OperationalError as exc:
        if not _is_missing_registry_table_error(model, exc):
            raise
        message = _schema_pending_message(model)
        if write:
            raise RuntimeError(f"Refusing --write: {message}") from exc
        summary.status = "schema_pending"
        summary.status_detail = message
        summary.skipped += len(unique_by_lookup)
        return

    missing = {value: spec for value, spec in unique_by_lookup.items() if value not in existing}
    summary.existing += len(existing)

    if not write:
        summary.would_create += len(missing)
        return

    reconciled_keys = _reconcile_mutation_xref_collisions(model, missing)
    if reconciled_keys:
        summary.existing += len(reconciled_keys)
        missing = {value: spec for value, spec in missing.items() if value not in reconciled_keys}

    missing_specs = list(missing.values())
    _drop_conflicting_mutation_rsids(model, missing_specs)
    if missing_specs and all(_can_bulk_create_direct(spec) for spec in missing_specs):
        summary.created += _bulk_create_records(
            model,
            missing_specs,
            bulk_create_batch_size=bulk_create_batch_size,
        )
        return

    for spec in missing_specs:
        created = _create_record(model, spec, spec.create_kwargs)
        if created is None:
            summary.skipped += 1
            summary.status = "blocked"
            summary.status_detail = (
                summary.status_detail
                or "bionty source API could not resolve one or more missing records; direct inserts skipped"
            )
            continue
        summary.created += 1


def sync_parquet_nodes_to_lamindb(
    kg_path: str | Path,
    *,
    node_types: list[str] | None = None,
    lamin_instance: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    write: bool = False,
    max_rows: int | None = None,
    row_offset: int = 0,
    bulk_create_batch_size: int = DEFAULT_BULK_CREATE_BATCH_SIZE,
) -> list[SyncSummary]:
    """Sync selected KG node Parquets into LaminDB registries.

    ``write=False`` is a dry-run that performs registry existence lookups but
    creates nothing. Passing ``write=True`` is the only path that writes records.
    """

    root = kg_storage.open_kg_root(str(kg_path))
    available = set(root.list_nodes())
    selected = node_types or sorted(available & SUPPORTED_NODE_TYPES)

    registry_models = None
    registry_lookup_unavailable_detail: str | None = None
    if write:
        _connect_lamin(lamin_instance)
        registry_models = _registry_models()
    else:
        # Dry-run still benefits from live existence counts when LaminDB is
        # configured. If imports/config fail, fall back to conservative
        # would_create counts without writing or crashing local tests.
        try:
            _connect_lamin(lamin_instance)
            registry_models = _registry_models()
        except Exception as exc:
            registry_lookup_unavailable_detail = str(exc)
            print(
                f"dry-run: LaminDB registry lookup unavailable ({exc}); reporting all valid rows as would_create",
                file=sys.stderr,
            )
            registry_models = None

    summaries: list[SyncSummary] = []
    for node_type in selected:
        if node_type not in available:
            summaries.append(
                SyncSummary(node_type=node_type, registry=None, key_field=None, unsupported=0)
            )
            continue
        if node_type not in SUPPORTED_NODE_TYPES:
            row_count = 0
            for batch in _iter_node_batches(root, node_type, batch_size, row_offset=row_offset):
                row_count += len(batch)
                if max_rows is not None and row_count >= max_rows:
                    break
            summaries.append(
                SyncSummary(
                    node_type=node_type,
                    registry=None,
                    key_field=None,
                    seen=row_count,
                    unsupported=row_count,
                )
            )
            continue

        registry_name = None
        key_field = None
        summary = SyncSummary(node_type=node_type, registry=None, key_field=None)
        processed = 0
        for batch in _iter_node_batches(root, node_type, batch_size, row_offset=row_offset):
            if max_rows is not None:
                remaining = max_rows - processed
                if remaining <= 0:
                    break
                batch = batch.head(remaining)
            processed += len(batch)
            summary.seen += len(batch)

            specs: list[RecordSpec] = []
            for row in batch.to_dict(orient="records"):
                spec = _row_to_record_spec(node_type, row)
                if spec is None:
                    summary.skipped += 1
                    continue
                registry_name = spec.registry_name
                key_field = spec.key_field
                specs.append(spec)

            # Most node types use one registry/key field, but mutation nodes can
            # mix dbSNP rsIDs with gnomAD-like chr_pos_ref_alt IDs. Keep lookup
            # groups key-field-specific so existence checks and writes use the
            # identifier that actually represents each KG node ID.
            by_registry_and_key: dict[tuple[str, str], list[RecordSpec]] = {}
            for spec in specs:
                by_registry_and_key.setdefault((spec.registry_name, spec.key_field), []).append(spec)
            for group in by_registry_and_key.values():
                _process_specs(
                    group,
                    registry_models=registry_models,
                    write=write,
                    summary=summary,
                    bulk_create_batch_size=bulk_create_batch_size,
                )

        summary.registry = registry_name
        summary.key_field = key_field
        if registry_models is None and registry_lookup_unavailable_detail and registry_name:
            if "wasn't configured" in registry_lookup_unavailable_detail and registry_name.startswith("lnschema_txgnn."):
                summary.status = "schema_module_not_configured"
            else:
                summary.status = "registry_lookup_unavailable"
            summary.status_detail = registry_lookup_unavailable_detail
        summaries.append(summary)

    return summaries


def _print_summary(summaries: list[SyncSummary], *, kg_path: str | Path, write: bool) -> None:
    mode = "WRITE" if write else "DRY-RUN"
    print(f"LaminDB parquet-node sync ({mode}): {kg_path}")
    for item in summaries:
        would_create = "unknown" if item.status == "schema_pending" else f"{item.would_create:,}"
        print(
            f"  {item.node_type:<12} seen={item.seen:,} existing={item.existing:,} "
            f"would_create={would_create} created={item.created:,} "
            f"skipped={item.skipped:,} unsupported={item.unsupported:,} "
            f"status={item.status} registry={item.registry or '-'}"
        )
        if item.status_detail:
            print(f"    {item.status_detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kg_path", help="Local KG root containing nodes/*.parquet")
    parser.add_argument(
        "--node-types",
        nargs="+",
        default=None,
        help="Node types to sync; defaults to supported node files",
    )
    parser.add_argument("--lamin-instance", default=None, help="Optional ln.connect(...) instance slug")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-rows", type=int, default=None, help="Optional smoke-test row cap per node type")
    parser.add_argument("--row-offset", type=int, default=0, help="First source row to select per node type")
    parser.add_argument("--bulk-create-batch-size", type=int, default=DEFAULT_BULK_CREATE_BATCH_SIZE)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually create missing LaminDB records; default is dry-run",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args(argv)

    summaries = sync_parquet_nodes_to_lamindb(
        args.kg_path,
        node_types=args.node_types,
        lamin_instance=args.lamin_instance,
        batch_size=args.batch_size,
        write=args.write,
        max_rows=args.max_rows,
        row_offset=args.row_offset,
        bulk_create_batch_size=args.bulk_create_batch_size,
    )
    if args.json:
        print(json.dumps([asdict(item) for item in summaries], indent=2, sort_keys=True))
    else:
        _print_summary(summaries, kg_path=args.kg_path, write=args.write)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
