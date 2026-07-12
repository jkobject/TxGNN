# Self-contained restore for the bounded Lamin edge/evidence smoke

This restore source is a clean branch from `a70bb42775afbfb06544c9326dd1c8179c4a3a21` (`origin/main`), prepared only for the bounded `enhancer_regulates_gene` Lamin smoke. It supersedes the incomplete one-patch restore that failed before collection in `t_51e11028`.

## Included source and provenance

The branch contains the committed exact-model activation sources, the bounded sync implementation, and their direct test/dependency sources. No external patch artifact is required or included.

| Path | SHA-256 | Provenance |
| --- | --- | --- |
| `manage_db/kg_edge_pilot.py` | `ab08685fb095b1a8131a71728a78037a3f237aa0ef9c0ffc3114a5fa30d126fc` | committed remote source `f34ae04bf49ebda88f14cc6fdc3e5eecbce11ff2`; accepted-source cache |
| `manage_db/sync_parquet_edges_to_lamindb.py` | `23a4ca76f6d71c4000a78dc725c6d62d34d1e76f2bfb0f4315d8d1ce8967f160` | scoped per-guard writer capability: identity-checked against the active owner-thread scope and revoked before lock release |
| `tests/test_sync_parquet_edges_to_lamindb.py` | `5bd0e1269a3480564fc002951e56445f2dce235897730dbb417aaac110e38489` | focused streaming/sync tests, including stale, forged, later-scope, and cross-thread capability rejection before write machinery |
| `manage_db/kg_storage.py` | `430513f32fd3bc7421bd12011e8710b37974daa7cf43e03a4643d884399919cf` | already present and unchanged in documented base `a70bb42` |
| `manage_db/lnschema_txgnn/__init__.py` | `450d45ce48e4271f5e72445321df568e8bbdbf4b2c3c88297bd165608b8bef3d` | committed exact-model application configuration |
| `manage_db/lnschema_txgnn/models.py` | `b4d31674456182667d2043814f9b103822d370db63438c82dae3ae6aa791158e` | committed `KGEdge` and `KGEdgeEvidence` model activation source |
| `manage_db/lnschema_txgnn/migrations/0007_generic_kg_edge_evidence.py` | `e901e435d57c8dca36645fca7423f3abdf31f8a9680083c7d6d4f1be06156f17` | committed exact-model migration; schema-only and does not sync KG rows or write GCS |
| `tests/test_lnschema_txgnn_exact_kg_models.py` | `827091de01ed835604c43cd76e1b4aedd5174511b3fde37abb161f7baca4e984` | exact-model activation regression coverage |

The eight source-path hashes above must be checked after applying this branch. This documents `kg_storage` as a pinned base dependency rather than duplicating an unchanged base file. The prior cached sync file and a later remote source/test pair did not preserve the active-scope writer-capability contract, so neither is used here.

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
