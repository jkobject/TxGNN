#!/usr/bin/env python3
"""Bulk-import bionty reference ontologies and transfer pertdb.Compound records.

Targets: jkobject/txgnn_fresh2 (local SQLite instance).
Compounds sourced from: laminlabs/pertdata (cloud instance, 24 882 records).
"""

from __future__ import annotations

import sys
import time


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


log("=" * 65)
log("bionty import + pertdb.Compound transfer — starting")
log("=" * 65)

import lamindb as ln  # noqa: E402
import bionty as bt   # noqa: E402
import pertdb as pt   # noqa: E402

# ── 1. Connect to local instance ──────────────────────────────────────────────
ln.connect("jkobject/txgnn_fresh2")
log(f"Connected to: {ln.setup.settings.instance.slug}")

# ── 2. Import bionty ontology sources ─────────────────────────────────────────
# (entity_name, registry_class, organism_filter)
REGISTRIES: list[tuple[str, object, str | None]] = [
    ("bionty.CellType",           bt.CellType,           None),
    ("bionty.Disease",            bt.Disease,            None),
    ("bionty.Tissue",             bt.Tissue,             None),
    ("bionty.Phenotype",          bt.Phenotype,          "human"),
    ("bionty.Pathway",            bt.Pathway,            None),
    ("bionty.Gene",               bt.Gene,               "human"),
    ("bionty.ExperimentalFactor", bt.ExperimentalFactor, None),
    ("bionty.CellLine",           bt.CellLine,           None),
]

for entity_name, registry, organism in REGISTRIES:
    before = registry.objects.count()
    log(f"\n{'─'*55}")
    log(f"Importing {entity_name}  (before: {before:,})")

    source = bt.Source.objects.filter(
        entity=entity_name, currently_used=True
    ).first()
    if source is None:
        # Fallback: any source for this entity
        source = bt.Source.objects.filter(entity=entity_name).first()
    if source is None:
        log(f"  No source found — skipping")
        continue

    log(f"  Source: {source.name} {source.version or ''}")
    try:
        kwargs: dict = {"ignore_conflicts": True}
        if organism:
            kwargs["organism"] = organism
        # Try preferred API: import_source(source=...) — bionty ≥0.42
        try:
            registry.import_source(source=source, **kwargs)
        except TypeError:
            # Older API: source.import_source() or no source kwarg
            try:
                registry.import_source(**kwargs)
            except TypeError:
                registry.import_source()
        after = registry.objects.count()
        log(f"  Done: {before:,} → {after:,}  (+{after - before:,})")
    except Exception as exc:
        log(f"  ERROR: {exc}")
        import traceback
        traceback.print_exc()

# ── 3. Fetch pertdb.Compound from laminlabs/pertdata ─────────────────────────
log("\n" + "=" * 65)
log("Step 3 — fetching pertdb.Compound from laminlabs/pertdata")
log("=" * 65)

COMPOUND_FIELDS = (
    "uid", "name", "ontology_id", "abbr", "synonyms",
    "description", "type", "chembl_id", "smiles",
    "canonical_smiles", "inchikey", "molweight", "molformula", "moa",
)

log("Connecting to laminlabs/pertdata …")
ln.connect("laminlabs/pertdata")
log(f"Connected to: {ln.setup.settings.instance.slug}")

total_remote = pt.Compound.objects.count()
log(f"Remote compound count: {total_remote:,}")

FETCH_CHUNK = 2000
all_compound_dicts: list[dict] = []

for start in range(0, total_remote, FETCH_CHUNK):
    batch = list(
        pt.Compound.objects.all()[start : start + FETCH_CHUNK].values(
            *COMPOUND_FIELDS
        )
    )
    all_compound_dicts.extend(batch)
    pct = len(all_compound_dicts) * 100 // total_remote
    if start % 10_000 == 0 or len(all_compound_dicts) == total_remote:
        log(f"  Fetched {len(all_compound_dicts):,}/{total_remote:,}  ({pct}%)")

log(f"Fetched {len(all_compound_dicts):,} compound records from laminlabs/pertdata")

# ── 4. Save compounds to local instance ───────────────────────────────────────
log("\n" + "=" * 65)
log("Step 4 — saving compounds to jkobject/txgnn_fresh2")
log("=" * 65)

log("Reconnecting to jkobject/txgnn_fresh2 …")
ln.connect("jkobject/txgnn_fresh2")
log(f"Connected to: {ln.setup.settings.instance.slug}")

local_before = pt.Compound.objects.count()
log(f"Local compounds before: {local_before:,}")

existing_uids: set[str] = set(
    pt.Compound.objects.values_list("uid", flat=True)
)
log(f"Existing UIDs: {len(existing_uids):,}")

SAVE_CHUNK = 500
buffer: list[pt.Compound] = []
created_total = 0
skipped_total = 0

for d in all_compound_dicts:
    uid = d.get("uid")
    if uid in existing_uids:
        skipped_total += 1
        continue

    # Build kwargs — skip None values to respect model field defaults
    kwargs = {k: d[k] for k in COMPOUND_FIELDS if d.get(k) is not None}
    buffer.append(pt.Compound(**kwargs))

    if len(buffer) >= SAVE_CHUNK:
        pt.Compound.objects.bulk_create(buffer, ignore_conflicts=True)
        created_total += len(buffer)
        buffer = []
        if created_total % 5_000 == 0:
            log(f"  bulk_create: {created_total:,} so far …")

if buffer:
    pt.Compound.objects.bulk_create(buffer, ignore_conflicts=True)
    created_total += len(buffer)

local_after = pt.Compound.objects.count()
log(f"\nCompounds: {local_before:,} → {local_after:,}  (+{local_after - local_before:,})")
log(f"New records created: {created_total:,}  |  Skipped (existing): {skipped_total:,}")

# ── 5. Final summary ──────────────────────────────────────────────────────────
log("\n" + "=" * 65)
log("FINAL RECORD COUNTS — jkobject/txgnn_fresh2")
log("=" * 65)

summary_registries = [
    ("bt.Organism",           bt.Organism),
    ("bt.CellType",           bt.CellType),
    ("bt.Disease",            bt.Disease),
    ("bt.Tissue",             bt.Tissue),
    ("bt.Phenotype",          bt.Phenotype),
    ("bt.Pathway",            bt.Pathway),
    ("bt.Gene",               bt.Gene),
    ("bt.ExperimentalFactor", bt.ExperimentalFactor),
    ("bt.CellLine",           bt.CellLine),
    ("pt.Compound",           pt.Compound),
]

for name, reg in summary_registries:
    try:
        count = reg.objects.count()
        log(f"  {name:<30}  {count:>10,}")
    except Exception as exc:
        log(f"  {name:<30}  ERROR — {exc}")

log("\nAll done!")
