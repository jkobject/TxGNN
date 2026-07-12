# Lamin edge-sync durable telemetry contract

This contract applies only to future bounded `manage_db.sync_parquet_edges_to_lamindb` runs. It does not provide, reconstruct, or imply historical `fsync` proof for older artifacts.

## Per-subchunk records and acknowledgements

A writer supplies a stable `--run-id`; each verified subchunk derives a stable `record_id` from that run, relation, chunk index, and independent edge/evidence source offsets. The primary JSONL record contains the relation/window fields, independent selected/upserted/durable edge and evidence counts/offsets, `last_progress_at`, elapsed seconds, edge/evidence throughput, process RSS, disk free, iowait value/status, and `record_sha256` (the SHA-256 of the canonical payload before the hash field).

The writer writes, flushes, and calls `os.fsync` for that primary record. Only after that succeeds does it publish the acknowledgement in `progress.jsonl.ack.jsonl`; every acknowledgement binds `run_id`, `record_id`, `record_sha256`, the resolved primary telemetry path, acknowledgement timestamp, and `fsync_success=true`. The acknowledgement sequence is primary `write -> flush -> fsync`, then pending acknowledgement `write -> flush -> fsync -> atomic replace -> containing-directory fsync`. A primary, pending-acknowledgement, or directory fsync failure returns `telemetry_failed` and does not advance the in-memory durable edge/evidence checkpoint or append the chunk to the accepted summary.

If the directory fsync fails after `replace`, the acknowledgement filename can be visible but is an **unaccepted recovery artifact**, not durable evidence and not a checkpoint. Recovery must re-run selected-live verification and emit a fresh fully durable acknowledgement; it must never accept or advance from that visible record.

`iowait_status=unavailable` is intentional on non-Linux or unreadable `/proc/stat`. Any production gate that requires iowait must reject that record rather than treating the missing value as healthy.

## Checked worker uv runner

The source-controlled launcher `scripts/run_txgnn_uv_checked.sh` is non-installing. It does not mutate VM/package configuration. Invoke it from the reviewed TxGNN checkout with an explicit absolute uv path resolving under `$HOME/.local/` and exact checkout SHA. Canonicalization rejects system binaries, path traversal, and symlinks escaping that user-local root:

```bash
TXGNN_UV=/home/ubuntu/.local/bin/uv \
TXGNN_EXPECTED_COMMIT=<reviewed-sha> \
./scripts/run_txgnn_uv_checked.sh -m pytest tests/test_sync_parquet_edges_to_lamindb.py -q
```

Before it runs `uv`, the launcher prints `TXGNN_UV_PATH`, SHA-256, the verified checkout HEAD, and `uv --version`; it exits nonzero if the binary is missing/not executable or checkout identity differs. It never downloads or installs `uv`. An operations card must retain that output in its ordered transcript and separately perform its required live instance/root/offset/writer gates before any writer command.
