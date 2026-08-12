"""Phase 3 — TxGNN KG migration.

Reads the TxData knowledge graph (nodes.tab + edges.csv) and converts
it to the new edge Parquet schema defined in kg_schema.py.

Outputs
-------
data/kg/nodes/{node_type}.parquet   — one file per NodeType
data/kg/edges/{relation}.parquet    — one file per canonical relation name

Node ID normalisation rules
---------------------------
node_type          source ID              → new ontology ID
──────────────────────────────────────────────────────────────
gene/protein       NCBI Gene int          → human ENSG via pinned authoritative map
drug               DrugBank DB…           → keep as-is  (ChEMBL mapping deferred)
effect/phenotype   HPO int                → HP:{id:07d}
disease (MONDO)    MONDO int              → MONDO:{id:07d}
disease (grouped)  int1_int2_…            → MONDO:{first_id:07d}  (primary rep)
biological_process GO int                 → GO:{id:07d}
molecular_function GO int                 → GO:{id:07d}
cellular_component GO int                 → GO:{id:07d}
exposure           CTD C…                 → CTD:{id}
pathway            Reactome R-HSA-…       → keep as-is
anatomy            UBERON int             → UBERON:{id:07d}

Usage
-----
    uv run python -m txgnn.kg_migrate [--dry-run] [--data-dir ./data]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

try:
    from . import kg_storage
except ImportError:  # pragma: no cover - script fallback
    import kg_storage  # type: ignore

try:
    from .kg_schema import (
        TXDATA_NODE_TYPE_MAP, TXDATA_RELATION_MAP, TXDATA_RELATION_FLIP,
        NODE_TYPES, RELATION_BY_NAME, NodeType, Credibility,
    )
except ImportError:
    from kg_schema import (  # type: ignore[no-redef]
        TXDATA_NODE_TYPE_MAP, TXDATA_RELATION_MAP, TXDATA_RELATION_FLIP,
        NODE_TYPES, RELATION_BY_NAME, NodeType, Credibility,
    )

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ID normalisation helpers
# ---------------------------------------------------------------------------

def _fmt_zero(prefix: str, raw_id: str, width: int = 7) -> str:
    """Format ``prefix:{raw_id:0width}`` for integer-style ontology IDs."""
    return f"{prefix}:{int(raw_id):0{width}d}"


def normalise_node_id(
    raw_id: str,
    txdata_type: str,
    source: str,
    *,
    gene_id_map: dict[str, str] | None = None,
) -> str:
    """Return a normalised ontology ID for a single node."""
    rid = str(raw_id).strip()

    match txdata_type:
        case "gene/protein":
            if gene_id_map is None:
                raise ValueError("gene/protein normalization requires a pinned NCBI Gene→human ENSG map")
            canonical_id = gene_id_map.get(rid)
            if canonical_id is None or not canonical_id.startswith("ENSG"):
                raise ValueError(f"NCBI Gene {rid!r} has no accepted one-to-one human ENSG mapping")
            return canonical_id

        case "drug":
            # DrugBank IDs are already in DB00001 format
            return rid

        case "effect/phenotype":
            return _fmt_zero("HP", rid)

        case "disease":
            if source == "MONDO_grouped":
                # Take the first MONDO ID from the underscore-separated list
                first = rid.split("_")[0]
                return _fmt_zero("MONDO", first)
            else:
                return _fmt_zero("MONDO", rid)

        case "biological_process" | "molecular_function" | "cellular_component":
            return _fmt_zero("GO", rid)

        case "exposure":
            return f"CTD:{rid}"

        case "pathway":
            # Reactome IDs are already in R-HSA-… format
            return rid

        case "anatomy":
            return _fmt_zero("UBERON", rid)

        case _:
            log.warning("Unknown TxData node type %r — keeping raw id %r", txdata_type, rid)
            return rid


# ---------------------------------------------------------------------------
# Node migration
# ---------------------------------------------------------------------------

def migrate_nodes(
    nodes_df: pd.DataFrame,
    *,
    gene_id_map: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[int, str]]:
    """Normalise node IDs and return (new_nodes_df, index_to_new_id mapping).

    Returns
    -------
    new_nodes_df
        Columns include node_type, id, all schema-required xref columns, and
        lightweight legacy provenance columns.
    index_to_id
        Dict mapping original ``node_index`` (int) → new ontology ``node_id``
    """
    rows = []
    index_to_id: dict[int, str] = {}

    for _, row in nodes_df.iterrows():
        raw_id = str(row["node_id"]).strip()
        txdata_type = str(row["node_type"]).strip()
        source = str(row["node_source"]).strip()
        name = str(row["node_name"]).strip()
        idx = int(row["node_index"])

        new_id = normalise_node_id(
            raw_id,
            txdata_type,
            source,
            gene_id_map=gene_id_map,
        )
        new_type = TXDATA_NODE_TYPE_MAP.get(txdata_type)
        if new_type is None:
            log.warning("Unmapped legacy type %r (node_index=%d) — skipping", txdata_type, idx)
            continue

        index_to_id[idx] = new_id
        record = {
            "id": new_id,
            "node_type": new_type.value,
            "txdata_type": txdata_type,
            "txdata_id": raw_id,
            "txdata_index": idx,
            "source": source,
        }
        for col in NODE_TYPES[new_type].xref_columns:
            record[col] = None

        if new_type == NodeType.GENE:
            record["ncbi_gene_id"] = raw_id
            record["gene_name"] = name
        elif new_type == NodeType.MOLECULE and txdata_type == "drug":
            record["drugbank_id"] = raw_id
        elif new_type == NodeType.DISEASE:
            record["mondo_id"] = new_id if new_id.startswith("MONDO:") else None
        elif new_type == NodeType.PHENOTYPE:
            record["hp_id"] = new_id if new_id.startswith("HP:") else None
        elif new_type == NodeType.PATHWAY:
            record["go_id"] = new_id if new_id.startswith("GO:") else None

        rows.append(record)

    new_nodes_df = pd.DataFrame(rows)
    return new_nodes_df, index_to_id


# ---------------------------------------------------------------------------
# Edge migration
# ---------------------------------------------------------------------------

def migrate_edges(
    edges_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    index_to_id: dict[int, str],
) -> tuple[pd.DataFrame, list[str]]:
    """Convert TxData edges to new Parquet schema.

    Returns
    -------
    new_edges_df
        Columns: x_id, x_type, y_id, y_type, relation, display_relation, source, credibility
    unmapped_relations
        List of TxData relation names that had no mapping in TXDATA_RELATION_MAP
    """
    node_types = nodes_df["node_type"].astype(str).str.strip().map(TXDATA_NODE_TYPE_MAP)
    index_to_type = pd.Series(
        [nt.value if isinstance(nt, NodeType) else nt for nt in node_types],
        index=pd.to_numeric(nodes_df["node_index"], errors="coerce"),
    ).dropna()

    legacy_rel = edges_df["relation"].astype(str).str.strip()
    new_rel = legacy_rel.map(TXDATA_RELATION_MAP)
    display_relation = edges_df.get("display_relation", pd.Series("", index=edges_df.index)).astype(str).str.strip()
    exposure_parent = legacy_rel.eq("exposure_exposure") & display_relation.eq("parent of")
    new_rel = new_rel.mask(exposure_parent, "molecule_parent_of_molecule")
    unmapped = sorted(set(legacy_rel[new_rel.isna()]))

    x_idx = pd.to_numeric(edges_df["x_index"], errors="coerce")
    y_idx = pd.to_numeric(edges_df["y_index"], errors="coerce")

    out = pd.DataFrame(
        {
            "x_id": x_idx.map(index_to_id),
            "x_type": x_idx.map(index_to_type),
            "y_id": y_idx.map(index_to_id),
            "y_type": y_idx.map(index_to_type),
            "relation": new_rel,
            "display_relation": display_relation,
            "source": "TxGNN",
            "credibility": Credibility.ESTABLISHED_FACT.value,
            "_txdata_relation": legacy_rel,
        }
    )
    out = out.dropna(subset=["x_id", "x_type", "y_id", "y_type", "relation"]).reset_index(drop=True)

    flip = out["_txdata_relation"].isin(TXDATA_RELATION_FLIP)
    if bool(flip.any()):
        out.loc[flip, ["x_id", "y_id"]] = out.loc[flip, ["y_id", "x_id"]].to_numpy()
        out.loc[flip, ["x_type", "y_type"]] = out.loc[flip, ["y_type", "x_type"]].to_numpy()

    def legacy_node_type(node_type: NodeType) -> str:
        # TxData conflates protein with gene/protein nodes stored as gene.
        if node_type == NodeType.PROTEIN:
            return NodeType.GENE.value
        return node_type.value

    desired_source = out["relation"].map(lambda rel: legacy_node_type(RELATION_BY_NAME[rel].source))
    desired_target = out["relation"].map(lambda rel: legacy_node_type(RELATION_BY_NAME[rel].target))
    reverse = (out["x_type"] == desired_target) & (out["y_type"] == desired_source)
    if bool(reverse.any()):
        out.loc[reverse, ["x_id", "y_id"]] = out.loc[reverse, ["y_id", "x_id"]].to_numpy()
        out.loc[reverse, ["x_type", "y_type"]] = out.loc[reverse, ["y_type", "x_type"]].to_numpy()

    out = out.drop(columns=["_txdata_relation"])
    return out, unmapped


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def save_nodes(nodes_df: pd.DataFrame, root: kg_storage.KGRoot, dry_run: bool) -> None:
    for nt_val, group in nodes_df.groupby("node_type"):
        log.info("  nodes/%s.parquet  →  %d rows", nt_val, len(group))
        if dry_run:
            continue
        kg_storage.write_nodes(
            root,
            nt_val,
            group.reset_index(drop=True).drop(columns=["node_type"], errors="ignore"),
            mode="overwrite",
        )


def save_edges(edges_df: pd.DataFrame, root: kg_storage.KGRoot, dry_run: bool) -> None:
    for rel, group in edges_df.groupby("relation"):
        log.info("  edges/%s.parquet  →  %d rows", rel, len(group))
        if dry_run:
            continue
        kg_storage.write_edges(
            root,
            rel,
            group.reset_index(drop=True),
            mode="overwrite",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_gene_id_map(path: Path) -> dict[str, str]:
    """Load accepted one-to-one NCBI→ENSG rows from a pinned migration manifest."""
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    required = {"ncbi_gene_id", "canonical_ensembl_gene_id", "mapping_status"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"gene ID map missing columns: {missing}")
    accepted_statuses = {"accepted_1to1", "retired_replaced_1to1"}
    is_accepted = frame["mapping_status"].isin(accepted_statuses)
    inconsistent_rejected = ~is_accepted & frame["canonical_ensembl_gene_id"].notna()
    if bool(inconsistent_rejected.any()):
        statuses = sorted(frame.loc[inconsistent_rejected, "mapping_status"].astype(str).unique())
        raise ValueError(
            f"gene ID map has non-accepted statuses with canonical ENSG IDs: {statuses}"
        )
    accepted = frame.loc[is_accepted].copy()
    strict_ensg = (
        accepted["canonical_ensembl_gene_id"]
        .astype("string")
        .str.fullmatch(r"ENSG[0-9]+")
        .fillna(False)
    )
    if not bool(strict_ensg.all()):
        raise ValueError("accepted gene ID map rows must contain strict ENSG identifiers")
    if accepted["ncbi_gene_id"].astype(str).duplicated().any():
        raise ValueError("gene ID map contains duplicate accepted NCBI IDs")
    return dict(
        zip(
            accepted["ncbi_gene_id"].astype(str),
            accepted["canonical_ensembl_gene_id"].astype(str),
            strict=True,
        )
    )


def run(data_dir: Path, *, gene_id_map_path: Path, dry_run: bool = False) -> None:
    nodes_path = data_dir / "txdata" / "nodes.tab"
    edges_path = data_dir / "txdata" / "edges.csv"
    out_dir    = data_dir / "kg"
    root = kg_storage.open_kg_root(str(out_dir))

    log.info("Loading nodes from %s", nodes_path)
    nodes_raw = pd.read_csv(nodes_path, sep="\t", dtype=str)
    log.info("  %d nodes loaded", len(nodes_raw))

    log.info("Loading edges from %s", edges_path)
    edges_raw = pd.read_csv(edges_path, dtype=str)
    log.info("  %d edges loaded", len(edges_raw))

    # ── Node migration ───────────────────────────────────────────────────────
    log.info("Migrating nodes…")
    gene_id_map = load_gene_id_map(gene_id_map_path)
    new_nodes, index_to_id = migrate_nodes(nodes_raw, gene_id_map=gene_id_map)
    log.info("  %d nodes mapped", len(new_nodes))

    # Stats per type
    for nt_val, grp in new_nodes.groupby("node_type"):
        log.info("    %-25s  %6d nodes", nt_val, len(grp))

    # ── Edge migration ───────────────────────────────────────────────────────
    log.info("Migrating edges…")
    new_edges, unmapped_rels = migrate_edges(edges_raw, nodes_raw, index_to_id)
    log.info("  %d edges mapped", len(new_edges))

    if unmapped_rels:
        log.warning("Unmapped relations (dropped): %s", unmapped_rels)

    # Stats per relation
    for rel, grp in new_edges.groupby("relation"):
        log.info("    %-45s  %7d edges", rel, len(grp))

    # ── Save ─────────────────────────────────────────────────────────────────
    if dry_run:
        log.info("DRY RUN — no files written")
    else:
        log.info("Writing node parquets to %s/nodes/", root.uri)
        save_nodes(new_nodes, root, dry_run=False)
        log.info("Writing edge parquets to %s/edges/", root.uri)
        save_edges(new_edges, root, dry_run=False)
        log.info("Done.")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n=== Migration summary ===")
    print(f"  Input nodes : {len(nodes_raw):,}")
    print(f"  Output nodes: {len(new_nodes):,}")
    print(f"  Input edges : {len(edges_raw):,}")
    print(f"  Output edges: {len(new_edges):,}")
    if unmapped_rels:
        print(f"  Unmapped relations ({len(unmapped_rels)}): {unmapped_rels}")
    print(f"  Output dir  : {root.uri}")
    if dry_run:
        print("  (dry run — nothing written)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Migrate TxGNN KG to new Parquet schema")
    parser.add_argument("--data-dir", default="./data", help="Root data directory (default: ./data)")
    parser.add_argument(
        "--gene-id-map",
        type=Path,
        required=True,
        help="Pinned Parquet/CSV crosswalk with accepted NCBI Gene→human ENSG mappings",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing files")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
        stream=sys.stderr,
    )

    run(Path(args.data_dir), gene_id_map_path=args.gene_id_map, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
