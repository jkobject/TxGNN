"""Map TxGNN nodes to bionty/pertdb entities and create missing records.

This module provides a single primary function:
`sync_txgnn_nodes_to_lamin_entities`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class _MappingSpec:
    """Resolved mapping target for one node."""

    registry: str
    key_field: str
    key_value: str
    create_kwargs: dict[str, Any]


def _read_nodes(nodes_path: str | Path) -> pd.DataFrame:
    """Read TxGNN node table with required columns."""
    path = Path(nodes_path)
    sep = "\t" if path.suffix == ".tab" else ","
    nodes = pd.read_csv(path, sep=sep, low_memory=False)
    required = {"node_index", "node_id", "node_type", "node_name", "node_source"}
    if not required.issubset(nodes.columns):
        missing = required - set(nodes.columns)
        raise ValueError(f"nodes file missing columns: {missing}")
    return nodes


def _prefixed_id(source: str, node_id: str, node_type: str) -> str | None:
    """Build ontology ID when a deterministic prefix exists."""
    value = str(node_id).strip()
    src = str(source).strip().upper()
    if node_type == "anatomy" and src == "UBERON" and value.isdigit():
        return f"UBERON:{value.zfill(7)}"
    if node_type == "disease" and src == "MONDO" and value.isdigit():
        return f"MONDO:{value.zfill(7)}"
    if node_type == "effect/phenotype" and src == "HPO" and value.isdigit():
        return f"HP:{value.zfill(7)}"
    if node_type in {"biological_process", "molecular_function", "cellular_component"} and src == "GO" and value.isdigit():
        return f"GO:{value.zfill(7)}"
    if node_type == "pathway" and src == "REACTOME":
        return value
    if node_type == "drug" and src == "DRUGBANK":
        return value
    return None


def _build_mapping_spec(
    node_type: str,
    node_id: str,
    node_name: str,
    node_source: str,
) -> _MappingSpec:
    """Map a TxGNN node to a concrete bionty/pertdb registry target."""
    node_type = str(node_type)
    node_id = str(node_id).replace(".0", "").strip()
    node_name = str(node_name).strip()
    node_source = str(node_source).strip()
    source_upper = node_source.upper()
    ontology_id = _prefixed_id(node_source, node_id, node_type)

    if node_type == "gene/protein":
        stable_id = f"NCBI:{node_id}"
        return _MappingSpec(
            registry="bionty.Gene",
            key_field="stable_id",
            key_value=stable_id,
            create_kwargs={
                "stable_id": stable_id,
                "symbol": node_name if node_name else None,
                "ncbi_gene_ids": node_id,
            },
        )

    if node_type == "drug":
        return _MappingSpec(
            registry="pertdb.Compound",
            key_field="ontology_id" if ontology_id else "name",
            key_value=ontology_id or node_name,
            create_kwargs={
                "name": node_name,
                "ontology_id": ontology_id,
            },
        )

    if node_type == "exposure":
        return _MappingSpec(
            registry="pertdb.EnvironmentalPerturbation",
            key_field="ontology_id" if node_id else "name",
            key_value=node_id or node_name,
            create_kwargs={
                "name": node_name,
                "ontology_id": node_id or None,
            },
        )

    if node_type == "anatomy":
        return _MappingSpec(
            registry="bionty.Tissue",
            key_field="ontology_id" if ontology_id else "name",
            key_value=ontology_id or node_name,
            create_kwargs={"name": node_name, "ontology_id": ontology_id},
        )

    if node_type == "disease":
        return _MappingSpec(
            registry="bionty.Disease",
            key_field="ontology_id" if ontology_id else "name",
            key_value=ontology_id or node_name,
            create_kwargs={"name": node_name, "ontology_id": ontology_id},
        )

    if node_type == "effect/phenotype":
        return _MappingSpec(
            registry="bionty.Phenotype",
            key_field="ontology_id" if ontology_id else "name",
            key_value=ontology_id or node_name,
            create_kwargs={"name": node_name, "ontology_id": ontology_id},
        )

    if node_type == "pathway" or (
        node_type in {"biological_process", "molecular_function", "cellular_component"} and source_upper == "GO"
    ):
        return _MappingSpec(
            registry="bionty.Pathway",
            key_field="ontology_id" if ontology_id else "name",
            key_value=ontology_id or node_name,
            create_kwargs={"name": node_name, "ontology_id": ontology_id},
        )

    # Fallback: keep unknown biological categories in Pathway by name.
    return _MappingSpec(
        registry="bionty.Pathway",
        key_field="name",
        key_value=node_name,
        create_kwargs={"name": node_name},
    )


def sync_txgnn_nodes_to_lamin_entities(
    nodes_path: str | Path = "data/txdata/nodes.tab",
    mapping_output_path: str | Path | None = "data/txdata/node_entity_mapping.csv",
    lamin_instance: str | None = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Map TxGNN nodes to bionty/pertdb entities and add missing records.

    Args:
        nodes_path: Path to TxGNN node table (`nodes.tab` or CSV).
        mapping_output_path: Output CSV path for node-to-entity mapping. Set to None to skip writing.
        lamin_instance: Optional Lamin instance slug, passed to `ln.connect(...)` if provided.
        dry_run: If True, do not write any new registry records.

    Returns:
        DataFrame with one row per node and mapping details:
        `node_index, node_id, node_type, node_name, node_source, registry,
        key_field, key_value, status, entity_uid`.
    """
    try:
        import lamindb as ln
        import bionty as bt
        import pertdb as pt
    except ImportError as exc:
        raise ImportError(
            "Missing lamindb dependencies. Install with `uv pip install lamindb bionty pertdb`."
        ) from exc

    if lamin_instance:
        ln.connect(lamin_instance)

    nodes = _read_nodes(nodes_path)

    registry_map = {
        "bionty.Gene": bt.Gene,
        "bionty.Tissue": bt.Tissue,
        "bionty.Disease": bt.Disease,
        "bionty.Phenotype": bt.Phenotype,
        "bionty.Pathway": bt.Pathway,
        "pertdb.Compound": pt.Compound,
        "pertdb.EnvironmentalPerturbation": pt.EnvironmentalPerturbation,
    }
    human_organism = bt.Organism.objects.filter(name__iexact="human").first()
    if human_organism is None:
        human_organism = bt.Organism.from_source(name="human")
        if isinstance(human_organism, list):
            human_organism = human_organism[0] if human_organism else None
        if human_organism is None:
            human_organism = bt.Organism(name="human")
        if getattr(human_organism, "_state", None) is not None and human_organism._state.adding:
            human_organism = human_organism.save()
    public_genes = bt.Gene.public(organism="human")
    if hasattr(public_genes, "to_dataframe"):
        public_genes_df = public_genes.to_dataframe()
    else:
        public_genes_df = public_genes.df()
    public_gene_ncbi_by_symbol: dict[str, set[str]] = defaultdict(set)
    for row in public_genes_df[["symbol", "ncbi_gene_id"]].itertuples(index=False):
        symbol = str(getattr(row, "symbol", "")).strip()
        ncbi_gene_id = str(getattr(row, "ncbi_gene_id", "")).strip()
        if symbol and ncbi_gene_id and ncbi_gene_id != "nan":
            public_gene_ncbi_by_symbol[symbol].add(ncbi_gene_id)

    mapping_specs: list[_MappingSpec] = []
    for row in nodes.itertuples(index=False):
        mapping_specs.append(
            _build_mapping_spec(
                node_type=getattr(row, "node_type"),
                node_id=getattr(row, "node_id"),
                node_name=getattr(row, "node_name"),
                node_source=getattr(row, "node_source"),
            )
        )

    unique_keys: dict[tuple[str, str, str], dict[str, Any]] = {}
    grouped_values: dict[tuple[str, str], set[str]] = defaultdict(set)
    for spec in mapping_specs:
        cache_key = (spec.registry, spec.key_field, spec.key_value)
        unique_keys[cache_key] = spec.create_kwargs
        grouped_values[(spec.registry, spec.key_field)].add(spec.key_value)

    cache: dict[tuple[str, str, str], tuple[str, str]] = {}
    chunk_size = 2000

    for (registry_name, key_field), values_set in grouped_values.items():
        model = registry_map[registry_name]
        values = list(values_set)
        for start in range(0, len(values), chunk_size):
            chunk = values[start : start + chunk_size]
            existing_rows = model.objects.filter(**{f"{key_field}__in": chunk}).values_list(
                key_field, "uid"
            )
            for key_value, uid in existing_rows:
                cache[(registry_name, key_field, str(key_value))] = ("existing", str(uid))

    for cache_key, create_kwargs in unique_keys.items():
        if cache_key in cache:
            continue
        registry_name, _, key_value = cache_key
        model = registry_map[registry_name]
        if dry_run:
            # For bionty records without ontology-based certainty, mark as uncertain.
            if registry_name.startswith("bionty.") and not create_kwargs.get("ontology_id") and registry_name != "bionty.Gene":
                cache[cache_key] = ("uncertain", "")
            else:
                cache[cache_key] = ("missing", "")
        else:
            if registry_name == "bionty.Gene":
                symbol = str(create_kwargs.get("symbol") or "").strip()
                ncbi_gene_id = str(create_kwargs.get("ncbi_gene_ids") or "").strip()
                if not symbol or not ncbi_gene_id:
                    cache[cache_key] = ("uncertain", "")
                    continue
                if ncbi_gene_id not in public_gene_ncbi_by_symbol.get(symbol, set()):
                    cache[cache_key] = ("uncertain", "")
                    continue
                created = model.from_source(symbol=symbol, organism=human_organism, mute=True)
                if isinstance(created, list):
                    created = created[0] if created else None
                if created is None:
                    cache[cache_key] = ("uncertain", "")
                    continue
                # Defensive check: ensure source-backed match still contains expected NCBI ID.
                ncbi_values = {x.strip() for x in str(getattr(created, "ncbi_gene_ids", "")).split("|") if x.strip()}
                if ncbi_gene_id not in ncbi_values:
                    cache[cache_key] = ("uncertain", "")
                    continue
                if getattr(created, "_state", None) is not None and created._state.adding:
                    created = created.save()
            elif registry_name.startswith("bionty.") and create_kwargs.get("ontology_id"):
                created = model.from_source(ontology_id=key_value, mute=True)
                if isinstance(created, list):
                    created = created[0] if created else None
                if created is None:
                    created = model(**create_kwargs)
                if getattr(created, "_state", None) is not None and created._state.adding:
                    created = created.save()
            elif registry_name.startswith("bionty."):
                cache[cache_key] = ("uncertain", "")
                continue
            else:
                created = model(**create_kwargs).save()
            cache[cache_key] = ("created", str(created.uid))

    mapping_rows: list[dict[str, Any]] = []
    for row, spec in zip(nodes.itertuples(index=False), mapping_specs):
        status, entity_uid = cache[(spec.registry, spec.key_field, spec.key_value)]
        mapping_rows.append(
            {
                "node_index": int(getattr(row, "node_index")),
                "node_id": str(getattr(row, "node_id")).replace(".0", ""),
                "node_type": str(getattr(row, "node_type")),
                "node_name": str(getattr(row, "node_name")),
                "node_source": str(getattr(row, "node_source")),
                "registry": spec.registry,
                "key_field": spec.key_field,
                "key_value": spec.key_value,
                "status": status,
                "entity_uid": entity_uid,
            }
        )

    mapping_df = pd.DataFrame(mapping_rows)
    if mapping_output_path is not None:
        output = Path(mapping_output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        mapping_df.to_csv(output, index=False)
    return mapping_df


if __name__ == "__main__":
    report = sync_txgnn_nodes_to_lamin_entities()
    print(report["status"].value_counts().to_string())
