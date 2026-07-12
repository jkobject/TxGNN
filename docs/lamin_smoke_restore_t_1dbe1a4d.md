# Self-contained restore for the bounded Lamin edge/evidence smoke

This restore source is a clean branch from `a70bb42775afbfb06544c9326dd1c8179c4a3a21` (`origin/main`), prepared only for the bounded `enhancer_regulates_gene` Lamin smoke. It supersedes the incomplete one-patch restore that failed before collection in `t_51e11028`.

## Included source and provenance

The branch contains the previously accepted exact-model activation patch plus the sync implementation and its direct source dependency:

| Path | SHA-256 | Provenance |
| --- | --- | --- |
| `manage_db/kg_edge_pilot.py` | `ab08685fb095b1a8131a71728a78037a3f237aa0ef9c0ffc3114a5fa30d126fc` | committed remote source `f34ae04bf49ebda88f14cc6fdc3e5eecbce11ff2`; accepted-source cache |
| `manage_db/sync_parquet_edges_to_lamindb.py` | `30c485923912cc86a303d698c0ae1617e34ae1363a38cf96fccf6f311c61e738` | staged `t_a9bd79f6` review source, derived from the accepted isolated source; implements bounded single-pass streaming, fsynced telemetry, selected-key verification, and the accepted writer-capability guard |
| `tests/test_sync_parquet_edges_to_lamindb.py` | `68f10c53bce5a5fb381160ec8e58226e78f667080fa84007677d4a1985ac62df` | matching staged `t_a9bd79f6` focused test source |
| `manage_db/kg_storage.py` | `430513f32fd3bc7421bd12011e8710b37974daa7cf43e03a4643d884399919cf` | already present and unchanged in documented base `a70bb42` |
| `artifacts/staged/t_c432d85d/lamin_exact_kg_models.patch` | `da8bcd0b30f343f2b8f00b518003cf370da037ecc9bdeb2399d660dca00e5d20` | accepted `KGEdge`/`KGEdgeEvidence` activation and writer-capability safety patch |

The four source-path hashes above must be checked after applying this branch/patch. This documents `kg_storage` as a pinned base dependency rather than duplicating an unchanged base file in the patch. The prior cached sync file and a later remote source/test pair did not preserve the accepted writer-capability contract, so neither is used here.

## Restore and pre-write gate

On `txgnn-worker` only, start from a clean clone at the branch commit. Before any write:

1. Confirm `hostname` is `txgnn-worker`, input root is exactly `gs://jouvencekb/kg/v2`, and no related writer/supervisor is running.
2. Use only ephemeral requester-pays environment variables; do not record credentials.
3. Prove the connected LaminDB instance is exactly `jkobject/jouvencekb` and run the opt-in read-only exact-model probe.
4. Run the focused collection gate:

   ```sh
   uv run --group dev pytest -q tests/test_sync_parquet_edges_to_lamindb.py tests/test_lnschema_txgnn_exact_kg_models.py
   ```

5. Do not write unless collection and tests pass. The write runner must retain non-empty fsynced monotonic subchunk telemetry and selected-live edge/evidence equality with mismatch `0` before moving from the 10,000-row window at offset `10,315,000` to the 50,000-row window.

This source does not authorize a broad run, a macOS FUSE read, or a canonical Parquet write.
