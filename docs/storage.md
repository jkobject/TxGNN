# Jouvence KG storage

Stable data, durable derived PyG artifacts, LaminDB state, and temporary
candidates share `gs://jouvencekb` under disjoint prefixes. Only `raw/` and
`main/` are canonical public data. `pyg/` is a durable, reproducible derived
training layer. A prefix-scoped lifecycle applies exclusively to `staging/`,
never to canonical data, PyG snapshots, or LaminDB state.

## Namespaces

| Purpose | URI | Contract |
|---|---|---|
| Stable public data | `gs://jouvencekb/{raw,main}` | Durable, reviewed data |
| Derived PyG snapshots | `gs://jouvencekb/pyg/<graph-build-id>` | Durable, immutable, reproducible from an exact `main/` snapshot; not canonical biology |
| Temporary candidates | `gs://jouvencekb/staging` | Non-canonical; prefix-scoped lifecycle deletion after 14 days |
| LaminDB internals | `gs://jouvencekb/.lamin` | Hidden runtime/catalog state; not a public data layer |

## Stable layout

```text
gs://jouvencekb/
├── README.md
├── .lamin/
│   ├── .lamindb/lamin.db
│   └── lamin/...
├── raw/
│   └── <source>.<native-format>
├── main/
│   ├── nodes/<node-type>.parquet
│   ├── edges/<relation>.parquet
│   ├── edges_inferred/<relation>.parquet
│   ├── evidence/<relation>.parquet
│   ├── evidence_inferred/<relation>.parquet
│   ├── features/<feature>.parquet
│   └── embeddings/<entity>-<modality>-<model>.parquet
└── pyg/
    └── <graph-build-id>/
        ├── manifest.json
        ├── node_maps/
        ├── adjacency/
        ├── feature_indices/
        │   ├── nodes/
        │   ├── edges/
        │   └── splits/
        └── validation/

gs://jouvencekb/
└── staging/
    └── <task-or-build-id>/
        └── ... temporary candidate outputs ...
```

GCS has no real empty directories. The inferred prefixes are absent while there
are no accepted inferred tables; do not publish placeholders or synthetic empty
Parquets.

## Layer semantics

- `raw/`: selected upstream snapshots in native formats. If a source cannot be
  mirrored for licensing or scale reasons, document the external release and
  checksum in the catalog; do not create a fake raw object.
- `main/nodes/`: canonical entity registries.
- `main/edges/`: observed canonical graph assertions.
- `main/edges_inferred/`: independently reviewed inferred assertions only.
- `main/evidence/`: source-level support rows for observed edges.
- `main/evidence_inferred/`: provenance/evidence for accepted inferred edges.
- `main/features/`: non-topological node/edge feature sidecars.
- `main/embeddings/`: accepted learned vector tables, one flat Parquet object per
  entity/modality/model release.
- `pyg/`: immutable derived training snapshots: node index maps, disk-backed CSC
  adjacency, aligned feature arrays/masks, split metadata, and validation
  reports. It is reproducible from exact `main/` generations and never replaces
  canonical Parquet.

The old `metadata/` layer was not a coherent data layer. Clinical-trial indexes,
trial links, and mutation support rows are feature sidecars. Promotion receipts,
manifests, summaries, and provenance reports belong in versioned `docs/`. The
old `proof/mutation_in_gene_containment_proof.parquet` duplicated the 2,599,525
row-level containment proofs already encoded in
`evidence/mutation_in_gene.parquet` and is not a separate canonical layer.

## Access

`manage_db.kg_storage.open_kg_root(uri)` accepts plain paths or `gs://` URIs.
Use:

- canonical read root: `gs://jouvencekb/main`
- raw source root: `gs://jouvencekb/raw`
- candidate write root: `gs://jouvencekb/staging/<task-or-build-id>`
- durable derived PyG root: `gs://jouvencekb/pyg/<graph-build-id>`
- LaminDB storage root: `gs://jouvencekb/.lamin`

For FUSE, mount the bucket root and point code at `<mount>/main`; do not recreate
a local `kg/v2` alias.

## Publication protocol

1. Build and validate in local scratch or `gs://jouvencekb/staging`.
2. Freeze an immutable candidate generation and review its row/schema/evidence
   contract.
3. Publish one flat Parquet to the appropriate `main/` layer using a
   destination-generation precondition (`ifGenerationMatch=0` for a new name,
   or the reviewed current generation for an intentional replacement).
4. Read back CRC32C, size, Parquet footer, row count, and schema.
5. Refresh and check `docs/parquet-catalog/` against the live bucket.
6. Delete or allow lifecycle deletion of the staging candidate only after the
   canonical readback passes.

For PyG snapshots, build under `staging/<build-id>/pyg`, validate exact source
generations, adjacency, feature alignment and split leakage, then publish
marker-last to a new immutable `pyg/<graph-build-id>/`. PyG publication does not
mutate `main/` and does not make the artifact canonical biological data.

Never create `staged/`, `staging/`, `metadata/`, `proof/`, or `archive/` in the
stable bucket or inside `main/`. Candidate bundles, checkpoints, and transient
reports belong only in `gs://jouvencekb/staging`; LaminDB-owned runtime state
belongs only below `.lamin/`.

## Atomic writes

Local/FUSE writes use temporary files and atomic rename through
`manage_db.kg_storage`. Direct canonical GCS writes require generation
preconditions; a rename alone is not a concurrency guard on object storage.
Append mode rewrites a complete validated Parquet and must not be used to mutate
an unreviewed canonical generation in place.

## Catalog and provenance

The live machine-readable inventory and generated dataset pages live under
`docs/parquet-catalog/`. Source/release/license fields remain in each Parquet
where applicable. Promotion receipts and detailed migration manifests are Git
artifacts, not a bucket namespace.

Both buckets have a seven-day soft-delete policy as a short recovery guard. The
staging bucket additionally deletes all live objects after 14 days; staging must
never be treated as a durable archive.
