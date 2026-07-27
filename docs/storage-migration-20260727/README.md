# Jouvence bucket migration — 2026-07-27

Status at 2026-07-27 15:56 CEST: **copy/readback complete; legacy deletion pending independent review**.

## Decision

The stable data bucket is reduced to this contract:

```text
gs://jouvencekb/
├── README.md
├── raw/<source>.<native-format>
└── main/
    ├── nodes/<name>.parquet
    ├── edges/<name>.parquet
    ├── edges_inferred/<name>.parquet
    ├── evidence/<name>.parquet
    ├── evidence_inferred/<name>.parquet
    ├── features/<name>.parquet
    └── embeddings/<entity>-<modality>-<model>.parquet
```

GCS has no real directories. `edges_inferred/` and `evidence_inferred/` remain
absent while they contain no accepted Parquet tables.

Temporary candidates now belong under `gs://jouvencekb/staging`, covered by a
prefix-scoped 14-day deletion lifecycle. LaminDB internals
live under `gs://jouvencekb/.lamin`; they share the stable bucket's seven-day soft-delete guard
but are explicitly excluded from the public data contract.

## Frozen pre-migration evidence

- `pre-migration-objects.jsonl.gz`: every live object name, size, generation,
  CRC32C/MD5 where available, update time, class, and metadata before migration.
- `pre-migration-aggregate.json`: counts and bytes aggregated by prefixes.
- `object-map.json`: 121 generation-preconditioned object copies plus two
  reviewed compactions, with destination generation/checksum/readback evidence.

Pre-migration `kg/` contained **15,468 objects / 146,429,257,416 bytes**.
The old stable bucket additionally contained `.lamindb/` (four objects),
`lamin/` (65 objects), and `_clawd_probe.txt`.

## Canonical result

Live `main/` contains **110 flat Parquet objects / 18,318,815,894 bytes**:

| Layer | Objects |
|---|---:|
| `nodes/` | 15 |
| `edges/` | 43 |
| `edges_inferred/` | 0 |
| `evidence/` | 22 |
| `evidence_inferred/` | 0 |
| `features/` | 17 |
| `embeddings/` | 13 |

`raw/` contains 13 curated native source snapshots / 1,712,709,673 bytes.

All 121 direct copies were created with a destination-generation precondition
and passed source/destination size and CRC32C equality. Two nested releases were
compacted on the in-region worker and validated by row count, schema, SHA-256,
and destination readback:

- 24 ReMap chromosome shards →
  `main/features/remap_crm_tf_enhancer_support.parquet`, 48,768,788 rows,
  SHA-256 `3b9cbc952139fe6f37fff0321f1e42373674de1fee148848d6e141a7d8b520e2`;
- two ESM2 protein shards →
  `main/embeddings/protein_sequence_esm2_t33_650m_ur50d.parquet`, 112,051
  rows, SHA-256
  `52a7d5682f86cea80aea5f952ccee6e57b90151389d81152cd910589848dc5ed`.

The live footer-derived catalog documents **110/110** datasets with no
undocumented object.

## Resolution of ambiguous old layers

### `metadata/`

This was not one coherent layer:

- `clinical_trials_gov_trial_index.parquet` moved to
  `main/features/clinical_trials_gov_trial_index.parquet`;
- molecule-treatment trial links moved to
  `main/features/molecule_treats_disease_clinical_trial_links.parquet`;
- mutation/ReMap support rows moved to
  `main/features/mutation_overlaps_enhancer_support.parquet`;
- promotion receipts, reports, manifests, summaries, and provenance belong in
  versioned repository documentation, not a data prefix.

### `proof/`

`mutation_in_gene_containment_proof.parquet` is not retained as a separate
canonical layer. Worker-side DuckDB readback proved:

- proof rows: 2,599,525;
- evidence rows: 2,599,525;
- distinct `(relation, x_id, y_id, edge_key)` on both sides: 2,599,525;
- proof keys absent from evidence: 0;
- evidence keys absent from proof: 0.

The canonical evidence also embeds the detailed coordinate containment proof in
`text_span`; the separate proof table duplicates the accepted edge-support
population.

### `edges_inferred/` and `evidence_inferred/`

The old prefixes contain no Parquet. They only contain manifests for release
`post-operand-12fe3286f509-zero-rows`. The versioned report
`docs/formal_relation_inference_t_e8aebc97.md` already records that every rule
emitted zero rows. No placeholders were created in the new layout.

### `ml/`

The 82 objects are two June PyG pilot exports. They are reproducible build
artifacts, not KG tables. They are excluded from the stable bucket rather than
inventing a canonical `ml/` layer.

### staging, scratch, backups, and archives

`kg/staging`, `kg/v2/staging`, `kg/v2/staged`, `_promotion_staging`,
`kg/scratch`, `kg/local-archive`, `_backups`, `_removed_relations_*`, and
`archive` are historical candidates, transient builders, rollback copies, or
superseded snapshots. No active Jouvence process references them; no worker was
running during cutover. Accepted outputs are represented in `raw/` or `main/`,
and detailed promotion evidence remains in Git. They are deletion candidates,
not material to copy into the new short-lived staging bucket.

## LaminDB separation

The auxiliary `jouvencekb-lamin` bucket was repatriated under
`gs://jouvencekb/.lamin` before that bucket was deleted. All 72 source objects
(22,159,113,681 bytes) first passed size and CRC32C/MD5 equality. The usable
3.01 GB catalog was then repaired transactionally: storage roots now resolve to
`gs://jouvencekb/.lamin/lamin` and `gs://jouvencekb/main`, all 79 catalog keys
were rewritten from `kg/v2/...` to flat `main/...` paths, and SQLite
`quick_check` returned `ok`. It catalogs 60 Lamin-managed UID objects and 19
direct canonical artifacts. Local instance configuration points to
`gs://jouvencekb/.lamin`.

After promoting the repaired catalog to `.lamin/.lamindb/lamin.db`, its
redundant 3.01 GB source copy under `.lamin/lamin/.lamindb/lamin.db` was deleted
with a generation precondition. The retained `.lamin/` surface is 71 objects
(14,328,966,609 bytes): one active catalog plus Lamin-managed UID objects and
their storage/exclusion metadata.

The temporary staging bucket contained zero objects, so there was nothing to
move. It was deleted. `gs://jouvencekb/staging/` is the only future staging
namespace, with deletion after 14 days scoped by `matchesPrefix: ["staging/"]`.
The bucket's seven-day soft-delete guard remains active, and the lifecycle does
not match `raw/`, `main/`, or `.lamin/`.

## Repository cutover and validation

Active code, tests, notebook generator, operator docs, and `AGENTS.md` use:

- canonical: `gs://jouvencekb/main`;
- staging: `gs://jouvencekb/staging`;
- Lamin runtime: `gs://jouvencekb/.lamin`.

Historical dated reports retain old paths as historical evidence. A new
`scripts/check_storage_layout_contract.py` guard rejects legacy roots in active
surfaces and, after cleanup, can enforce the live root allowlist.

Executed validation on the migration worktree:

- `scripts/parquet_catalog.py check --live`: 110/110 documented;
- focused storage/notebook/Lamin/viewer suite: 46 passed;
- PyG/GNN suite with `--group gnn`: 13 passed;
- notebook 07 static checker: PASS, 28 cells, no failures;
- `git diff --check`: PASS;
- active-source legacy-path scan: only the guard's own forbidden-string list.

## Destructive cleanup gate

Before deleting old prefixes:

1. review the immutable repository revision containing this report, catalog,
   code cutover, and object map;
2. independently compare live `main/`/`raw/` objects against `object-map.json`;
3. confirm no writer/process references old paths;
4. delete `kg/`, `.lamindb/`, `lamin/`, and `_clawd_probe.txt`;
5. run `scripts/check_storage_layout_contract.py --live` and the live catalog
   check again;
6. stop `txgnn-worker` after final remote validation.

Because the stable bucket has seven-day soft delete, the deletion remains
recoverable during the immediate post-cutover window.
