"""Phase 3 — TxGNN KG migration.

Reads the legacy TxGNN knowledge graph (nodes.tab + edges.csv) and converts
it to the new edge Parquet schema defined in kg_schema.py.

Outputs
-------
data/kg/nodes/{node_type}.parquet   — one file per NodeType
data/kg/edges/{relation}.parquet    — one file per canonical relation name

Node ID normalisation rules
---------------------------
node_type          source ID              → new ontology ID
──────────────────────────────────────────────────────────────
gene/protein       NCBI Gene int          → NCBI:{id}   (Ensembl mapping deferred)
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
    from .kg_schema import (
        LEGACY_NODE_TYPE_MAP, LEGACY_RELATION_MAP, LEGACY_RELATION_FLIP,
        NodeType, Credibility,
    )
except ImportError:
    from kg_schema import (  # type: ignore[no-redef]
        LEGACY_NODE_TYPE_MAP, LEGACY_RELATION_MAP, LEGACY_RELATION_FLIP,
        NodeType, Credibility,
    )

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ID normalisation helpers
# ---------------------------------------------------------------------------

def _fmt_zero(prefix: str, raw_id: str, width: int = 7) -> str:
    """Format ``prefix:{raw_id:0width}`` for integer-style ontology IDs."""
    return f"{prefix}:{int(raw_id):0{width}d}"


def normalise_node_id(raw_id: str, legacy_type: str, source: str) -> str:
    """Return a normalised ontology ID for a single node."""
    rid = str(raw_id).strip()

    match legacy_type:
        case "gene/protein":
            return f"NCBI:{rid}"

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
            log.warning("Unknown legacy node type %r — keeping raw id %r", legacy_type, rid)
            return rid


# ---------------------------------------------------------------------------
# Node migration
# ---------------------------------------------------------------------------

def migrate_nodes(nodes_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, str]]:
    """Normalise node IDs and return (new_nodes_df, index_to_new_id mapping).

    Returns
    -------
    new_nodes_df
        Columns: node_id, node_type, name, legacy_type, legacy_id, legacy_index, source
    index_to_id
        Dict mapping original ``node_index`` (int) → new ontology ``node_id``
    """
    rows = []
    index_to_id: dict[int, str] = {}

    for _, row in nodes_df.iterrows():
        raw_id = str(row["node_id"]).strip()
        legacy_type = str(row["node_type"]).strip()
        source = str(row["node_source"]).strip()
        name = str(row["node_name"]).strip()
        idx = int(row["node_index"])

        new_id = normalise_node_id(raw_id, legacy_type, source)
        new_type = LEGACY_NODE_TYPE_MAP.get(legacy_type)
        if new_type is None:
            log.warning("Unmapped legacy type %r (node_index=%d) — skipping", legacy_type, idx)
            continue

        index_to_id[idx] = new_id
        rows.append({
            "node_id":       new_id,
            "node_type":     new_type.value,
            "name":          name,
            "legacy_type":   legacy_type,
            "legacy_id":     raw_id,
            "legacy_index":  idx,
            "source":        source,
        })

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
    """Convert legacy edges to new Parquet schema.

    Returns
    -------
    new_edges_df
        Columns: x_id, x_type, y_id, y_type, relation, display_relation, source, credibility
    unmapped_relations
        List of legacy relation names that had no mapping in LEGACY_RELATION_MAP
    """
    # Build index → node_type lookup for x_type / y_type
    index_to_type: dict[int, str] = {}
    for _, row in nodes_df.iterrows():
        lt = str(row["node_type"]).strip()
        nt = LEGACY_NODE_TYPE_MAP.get(lt)
        if nt is not None:
            index_to_type[int(row["node_index"])] = nt.value

    unmapped: set[str] = set()
    rows = []

    for _, row in edges_df.iterrows():
        legacy_rel = str(row["relation"]).strip()
        x_idx = int(row["x_index"])
        y_idx = int(row["y_index"])

        new_rel = LEGACY_RELATION_MAP.get(legacy_rel)
        if new_rel is None:
            unmapped.add(legacy_rel)
            continue

        x_id = index_to_id.get(x_idx)
        y_id = index_to_id.get(y_idx)
        if x_id is None or y_id is None:
            continue  # dangling edge

        x_type = index_to_type.get(x_idx, "")
        y_type = index_to_type.get(y_idx, "")

        # Swap x/y for relations where legacy direction is reversed vs canonical
        if legacy_rel in LEGACY_RELATION_FLIP:
            x_id, y_id = y_id, x_id
            x_type, y_type = y_type, x_type

        rows.append({
            "x_id":              x_id,
            "x_type":            x_type,
            "y_id":              y_id,
            "y_type":            y_type,
            "relation":          new_rel,
            "display_relation":  str(row.get("display_relation", "")).strip(),
            "source":            "TxGNN",
            "credibility":       Credibility.ESTABLISHED_FACT.value,
        })

    new_edges_df = pd.DataFrame(rows)
    return new_edges_df, sorted(unmapped)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def save_nodes(nodes_df: pd.DataFrame, out_dir: Path, dry_run: bool) -> None:
    node_dir = out_dir / "nodes"
    if not dry_run:
        node_dir.mkdir(parents=True, exist_ok=True)

    for nt_val, group in nodes_df.groupby("node_type"):
        path = node_dir / f"{nt_val}.parquet"
        log.info("  nodes/%s.parquet  →  %d rows", nt_val, len(group))
        if not dry_run:
            group.reset_index(drop=True).to_parquet(path, index=False)


def save_edges(edges_df: pd.DataFrame, out_dir: Path, dry_run: bool) -> None:
    edge_dir = out_dir / "edges"
    if not dry_run:
        edge_dir.mkdir(parents=True, exist_ok=True)

    for rel, group in edges_df.groupby("relation"):
        path = edge_dir / f"{rel}.parquet"
        log.info("  edges/%s.parquet  →  %d rows", rel, len(group))
        if not dry_run:
            group.reset_index(drop=True).to_parquet(path, index=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(data_dir: Path, dry_run: bool = False) -> None:
    nodes_path = data_dir / "txdata" / "nodes.tab"
    edges_path = data_dir / "txdata" / "edges.csv"
    out_dir    = data_dir / "kg"

    log.info("Loading nodes from %s", nodes_path)
    nodes_raw = pd.read_csv(nodes_path, sep="\t", dtype=str)
    log.info("  %d nodes loaded", len(nodes_raw))

    log.info("Loading edges from %s", edges_path)
    edges_raw = pd.read_csv(edges_path, dtype=str)
    log.info("  %d edges loaded", len(edges_raw))

    # ── Node migration ───────────────────────────────────────────────────────
    log.info("Migrating nodes…")
    new_nodes, index_to_id = migrate_nodes(nodes_raw)
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
        log.info("Writing node parquets to %s/nodes/", out_dir)
        save_nodes(new_nodes, out_dir, dry_run=False)
        log.info("Writing edge parquets to %s/edges/", out_dir)
        save_edges(new_edges, out_dir, dry_run=False)
        log.info("Done.")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n=== Migration summary ===")
    print(f"  Input nodes : {len(nodes_raw):,}")
    print(f"  Output nodes: {len(new_nodes):,}")
    print(f"  Input edges : {len(edges_raw):,}")
    print(f"  Output edges: {len(new_edges):,}")
    if unmapped_rels:
        print(f"  Unmapped relations ({len(unmapped_rels)}): {unmapped_rels}")
    print(f"  Output dir  : {out_dir}")
    if dry_run:
        print("  (dry run — nothing written)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Migrate TxGNN KG to new Parquet schema")
    parser.add_argument("--data-dir", default="./data", help="Root data directory (default: ./data)")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing files")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
        stream=sys.stderr,
    )

    run(Path(args.data_dir), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
