from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from manage_db import sync_parquet_edges_to_lamindb as sync


REL = "disease_associated_gene"


def _fixture(root: Path, *, edges: int = 2, evidence: int = 2) -> None:
    (root / "edges").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    edge_rows = [{"x_id": f"G:{i}", "x_type": "gene", "y_id": f"D:{i}", "y_type": "disease", "relation": REL, "source": "fixture", "credibility": 1} for i in range(edges)]
    evidence_rows = [{"x_id": f"G:{i}", "x_type": "gene", "y_id": f"D:{i}", "y_type": "disease", "relation": REL, "source": "fixture", "evidence_type": "record", "source_dataset": "fixture", "source_record_id": str(i), "evidence_score": 1.0, "predicate": REL, "direction": "forward"} for i in range(evidence)]
    pd.DataFrame(edge_rows).to_parquet(root / "edges" / f"{REL}.parquet", index=False)
    pd.DataFrame(evidence_rows).to_parquet(root / "evidence" / f"{REL}.parquet", index=False)


class Query:
    def __init__(self, rows: list[dict[str, Any]]): self.rows = rows
    def values(self, *fields: str): return [{field: row.get(field) for field in fields} for row in self.rows]


class Manager:
    def __init__(self): self.records: dict[str, dict[str, Any]] = {}
    def bulk_create(self, objects, *, batch_size, update_conflicts, update_fields, unique_fields):
        assert update_conflicts
        for obj in objects:
            self.records[vars(obj)[unique_fields[0]]] = dict(vars(obj))
        return objects
    def filter(self, **lookups):
        rows = list(self.records.values())
        for lookup, values in lookups.items():
            field = lookup.removesuffix("__in")
            rows = [row for row in rows if row.get(field) in set(values)]
        return Query(rows)


class Model:
    objects = Manager()
    def __init__(self, **kwargs): self.__dict__.update(kwargs)


class Edge(Model): pass
class Evidence(Model): pass


def _fake_lamin(monkeypatch, *, mismatch: bool = False) -> None:
    Edge.objects, Evidence.objects = Manager(), Manager()
    monkeypatch.setattr(sync, "_connect_lamin", lambda _: None)
    monkeypatch.setattr(sync, "_configure_sqlite_timeout", lambda: None)
    monkeypatch.setattr(sync, "_registry_models", lambda: (Edge, Evidence))
    monkeypatch.setattr(sync, "_transaction_atomic", lambda: contextlib.nullcontext())
    if mismatch:
        monkeypatch.setattr(sync, "_verify_selected", lambda *args, **kwargs: (0, 1))


def test_streaming_reader_never_uses_full_parquet_read(monkeypatch, tmp_path: Path) -> None:
    _fixture(tmp_path)
    original = sync.pq.ParquetFile
    class NoRead(original):
        def read(self, *args, **kwargs): raise AssertionError("full parquet materialization is forbidden")
    monkeypatch.setattr(sync.pq, "ParquetFile", NoRead)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=0, evidence_limit=0, chunk_size=1)
    assert (result.edge_rows_selected, result.evidence_rows_selected) == (2, 2)


def test_limit_zero_means_all_remaining_in_dry_run(tmp_path: Path) -> None:
    _fixture(tmp_path, edges=2, evidence=1)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_offset=1, edge_limit=0, evidence_limit=0, chunk_size=1)
    assert (result.edge_rows_selected, result.evidence_rows_selected) == (1, 1)


def test_finite_limit_exhausted_by_resume_is_not_unbounded(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, resume_chunk=1, write=True, verify_selected_live=True, telemetry_path=tmp_path / "progress.jsonl")
    assert result.status == "no_verified_subchunks"
    assert result.chunks == []
    assert Edge.objects.records == Evidence.objects.records == {}


@pytest.mark.parametrize(("edges", "evidence", "expected"), [(2, 1, (2, 1)), (1, 2, (1, 2))])
def test_asymmetric_streams_advance_only_nonempty_cursor(tmp_path: Path, monkeypatch, edges: int, evidence: int, expected: tuple[int, int]) -> None:
    _fixture(tmp_path, edges=edges, evidence=evidence)
    _fake_lamin(monkeypatch)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=0, evidence_limit=0, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=tmp_path / "progress.jsonl")
    assert (result.durable_edge_current_offset, result.durable_evidence_current_offset) == expected
    assert [(c.edge_rows_selected, c.evidence_rows_selected) for c in result.chunks][-1] in {(1, 0), (0, 1)}


def test_mismatch_emits_no_telemetry_or_durable_offset(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch, mismatch=True)
    telemetry = tmp_path / "progress.jsonl"
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry)
    assert result.status == "verification_failed"
    assert result.chunks == []
    assert result.durable_edge_current_offset is None
    assert not telemetry.exists()


def test_durable_telemetry_ack_follows_fsync_and_binds_record_identity(tmp_path: Path, monkeypatch) -> None:
    telemetry = tmp_path / "progress.jsonl"
    events: list[str] = []
    original_fsync = os.fsync

    class RecordingHandle:
        def __init__(self, handle): self.handle = handle
        def write(self, value):
            events.append("write")
            return self.handle.write(value)
        def flush(self):
            events.append("flush")
            return self.handle.flush()
        def fileno(self): return self.handle.fileno()
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.close()
        def __getattr__(self, name): return getattr(self.handle, name)

    original_open = Path.open
    def recording_open(self, *args, **kwargs): return RecordingHandle(original_open(self, *args, **kwargs))
    def recording_fsync(fd: int) -> None:
        events.append("fsync")
        original_fsync(fd)

    original_replace = os.replace
    def recording_replace(source, target) -> None:
        events.append("replace")
        original_replace(source, target)

    def recording_directory_fsync(directory: Path) -> None:
        assert directory == telemetry.parent
        events.append("directory_fsync")

    monkeypatch.setattr(Path, "open", recording_open)
    monkeypatch.setattr(sync.os, "fsync", recording_fsync)
    monkeypatch.setattr(sync.os, "replace", recording_replace)
    monkeypatch.setattr(sync, "_fsync_directory", recording_directory_fsync)
    ack = sync._append_durable_telemetry(telemetry, {"run_id": "run-1", "record_id": "record-1", "relation": REL})

    assert events == ["write", "flush", "fsync", "write", "flush", "fsync", "replace", "directory_fsync"]
    assert ack["fsync_success"] is True
    assert ack["record_id"] == "record-1"
    assert ack["telemetry_path"] == str(telemetry.resolve())
    assert ack["acknowledgement_path"] == str(telemetry.with_suffix(".jsonl.ack.jsonl").resolve())
    payload = json.loads(telemetry.read_text().strip())
    assert ack["record_sha256"] == payload["record_sha256"]
    ack_path = telemetry.with_suffix(".jsonl.ack.jsonl")
    assert json.loads(ack_path.read_text().strip()) == ack


def test_directory_fsync_failure_leaves_visible_ack_unaccepted_and_no_checkpoint(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    telemetry = tmp_path / "progress.jsonl"

    def fail_directory_fsync(_: Path) -> None:
        raise OSError("directory sync failure")

    monkeypatch.setattr(sync, "_fsync_directory", fail_directory_fsync)
    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry, run_id="run-directory-failure")

    assert result.status == "telemetry_failed"
    assert result.chunks == []
    assert result.durable_edge_current_offset is None
    assert result.durable_evidence_current_offset is None
    # A post-replace file can be visible but is not checkpoint-eligible until
    # the containing directory fsync succeeds.
    assert telemetry.with_suffix(".jsonl.ack.jsonl").exists()


def test_fsync_failure_emits_no_success_ack_and_does_not_advance_checkpoint(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    telemetry = tmp_path / "progress.jsonl"
    monkeypatch.setattr(sync.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("disk failure")))

    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry, run_id="run-fsync-failure")

    assert result.status == "telemetry_failed"
    assert result.chunks == []
    assert result.durable_edge_current_offset is None
    assert result.durable_evidence_current_offset is None
    assert not telemetry.with_suffix(".jsonl.ack.jsonl").exists()


def test_ack_fsync_failure_leaves_no_success_ack_or_checkpoint(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    telemetry = tmp_path / "progress.jsonl"
    original_fsync = os.fsync
    calls = 0
    def fail_ack_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("ack disk failure")
        original_fsync(fd)
    monkeypatch.setattr(sync.os, "fsync", fail_ack_fsync)

    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry, run_id="run-ack-failure")

    assert result.status == "telemetry_failed"
    assert result.durable_edge_current_offset is None
    assert result.durable_evidence_current_offset is None
    ack_path = telemetry.with_suffix(".jsonl.ack.jsonl")
    assert not ack_path.exists() or not ack_path.read_text()


def test_committed_telemetry_contains_independent_progress_contract(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    telemetry = tmp_path / "progress.jsonl"

    result = sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_offset=0, edge_limit=1, evidence_offset=0, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry, run_id="stable-run")

    assert result.status == "bounded live sync verified"
    payload = json.loads(telemetry.read_text().strip())
    assert payload["run_id"] == "stable-run"
    assert payload["relation"] == REL
    assert payload["edge_offset"] == payload["evidence_offset"] == 0
    assert payload["edge_rows_selected"] == payload["evidence_rows_selected"] == 1
    assert payload["durable_edge_current_offset"] == payload["durable_evidence_current_offset"] == 1
    for field in ("record_id", "record_sha256", "source_edge_offset", "source_edge_limit", "source_evidence_offset", "source_evidence_limit", "last_progress_at", "elapsed_seconds", "edge_rows_per_second", "evidence_rows_per_second", "process_rss_bytes", "disk_free_bytes", "iowait_seconds", "iowait_status"):
        assert field in payload


def test_idempotence_passes_preserve_run_identity_with_distinct_record_ids(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    telemetry = tmp_path / "progress.jsonl"

    sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, chunk_size=1, write=True, verify_selected_live=True, telemetry_path=telemetry, run_id="stable-run", idempotence_passes=2)

    records = [json.loads(line) for line in telemetry.read_text().splitlines()]
    assert [record["run_id"] for record in records] == ["stable-run", "stable-run"]
    assert [record["sync_pass_index"] for record in records] == [0, 1]
    assert len({record["record_id"] for record in records}) == 2


def test_unverified_write_is_rejected_before_upsert(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    with pytest.raises(RuntimeError, match="verify_selected_live"):
        sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, write=True)
    assert Edge.objects.records == {}


def test_verified_write_requires_durable_telemetry_before_upsert(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    with pytest.raises(RuntimeError, match="durable telemetry_path"):
        sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, write=True, verify_selected_live=True)
    assert Edge.objects.records == Evidence.objects.records == {}


def test_checked_uv_launcher_rejects_system_binary_and_symlink_escape(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    launcher = root / "scripts" / "run_txgnn_uv_checked.sh"
    expected_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    fake_uv = local_bin / "uv"
    fake_uv.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    environment = {**os.environ, "HOME": str(home), "TXGNN_EXPECTED_COMMIT": expected_commit}

    system_binary = subprocess.run([str(launcher), "--version"], cwd=root, env={**environment, "TXGNN_UV": "/usr/bin/true"}, text=True, capture_output=True)
    assert system_binary.returncode == 64
    assert "user-local" in system_binary.stderr

    escaped_uv = tmp_path / "outside-uv"
    escaped_uv.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    escaped_uv.chmod(0o755)
    fake_uv.unlink()
    fake_uv.symlink_to(escaped_uv)
    symlink_escape = subprocess.run([str(launcher), "--version"], cwd=root, env=environment, text=True, capture_output=True)
    assert symlink_escape.returncode == 64
    assert "user-local" in symlink_escape.stderr


def test_checked_uv_launcher_rejects_missing_binary_and_checkout_mismatch(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    launcher = root / "scripts" / "run_txgnn_uv_checked.sh"
    expected_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    environment = {**os.environ, "HOME": str(home), "TXGNN_EXPECTED_COMMIT": expected_commit}

    missing_binary = subprocess.run([str(launcher), "--version"], cwd=root, env=environment, text=True, capture_output=True)
    assert missing_binary.returncode == 127
    assert "unavailable" in missing_binary.stderr

    fake_uv = local_bin / "uv"
    fake_uv.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    positive = subprocess.run([str(launcher), "--version"], cwd=root, env=environment, text=True, capture_output=True)
    assert positive.returncode == 0
    assert f"TXGNN_CHECKOUT_HEAD={expected_commit}" in positive.stdout
    mismatch = subprocess.run([str(launcher), "--version"], cwd=root, env={**environment, "TXGNN_EXPECTED_COMMIT": "0" * 40}, text=True, capture_output=True)
    assert mismatch.returncode == 65
    assert "checkout mismatch" in mismatch.stderr


def test_direct_api_cannot_bypass_global_lock_with_other_telemetry_path(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path)
    _fake_lamin(monkeypatch)
    called = False
    original = sync._sync_relation_pass
    def observe(*args, **kwargs):
        nonlocal called
        called = True
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, "_sync_relation_pass", observe)
    with sync._single_writer_guard("jkobject/jouvencekb"):
        with pytest.raises(RuntimeError, match="global Lamin sync lock"):
            sync.sync_relation_to_lamindb(kg_root=tmp_path, relation=REL, edge_limit=1, evidence_limit=1, write=True, verify_selected_live=True, telemetry_path=tmp_path / "other.jsonl")
    assert called is False


def _direct_write_kwargs(tmp_path: Path) -> dict[str, Any]:
    return {
        "kg_root": tmp_path,
        "window": sync.RelationWindow(REL, edge_limit=1, evidence_limit=1, chunk_size=1),
        "write": True,
        "resume_chunk": 0,
        "max_chunks": None,
        "batch_size": 1,
        "verify_selected_live": True,
        "telemetry_path": None,
        "run_id": "direct-test-run",
    }


def _assert_capability_rejected_before_write_machinery(tmp_path: Path, monkeypatch, token: object) -> None:
    def no_write_machinery(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("stale or forged capability reached write machinery")

    monkeypatch.setattr(sync, "_parquet_metadata", no_write_machinery)
    with pytest.raises(RuntimeError, match="active writer capability"):
        sync._sync_relation_with_token(
            lamin_instance="jkobject/jouvencekb",
            token=token,
            **_direct_write_kwargs(tmp_path),
        )


def test_stale_writer_capability_is_rejected_before_write_machinery(tmp_path: Path, monkeypatch) -> None:
    with sync._single_writer_guard("jkobject/jouvencekb") as stale_token:
        pass
    _assert_capability_rejected_before_write_machinery(tmp_path, monkeypatch, stale_token)


def test_forged_writer_capability_is_rejected_before_write_machinery(tmp_path: Path, monkeypatch) -> None:
    with sync._single_writer_guard("jkobject/jouvencekb"):
        _assert_capability_rejected_before_write_machinery(tmp_path, monkeypatch, object())


def test_writer_capability_cannot_be_reused_by_a_later_guard_scope(tmp_path: Path, monkeypatch) -> None:
    with sync._single_writer_guard("jkobject/jouvencekb") as prior_token:
        pass
    with sync._single_writer_guard("jkobject/jouvencekb") as current_token:
        assert current_token is not prior_token
        _assert_capability_rejected_before_write_machinery(tmp_path, monkeypatch, prior_token)


def test_writer_capability_cannot_be_used_from_another_thread_before_write_machinery(tmp_path: Path, monkeypatch) -> None:
    failures: list[BaseException] = []

    def no_write_machinery(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("cross-thread capability reached write machinery")

    monkeypatch.setattr(sync, "_parquet_metadata", no_write_machinery)
    with sync._single_writer_guard("jkobject/jouvencekb") as token:
        def attempt_cross_thread_write() -> None:
            try:
                sync._sync_relation_with_token(
                    lamin_instance="jkobject/jouvencekb",
                    token=token,
                    **_direct_write_kwargs(tmp_path),
                )
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=attempt_cross_thread_write)
        worker.start()
        worker.join()

    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)
    assert "active writer capability" in str(failures[0])


def test_registry_models_fails_closed_without_activated_registry(monkeypatch) -> None:
    import sys
    monkeypatch.setitem(sys.modules, "django.apps", None)
    with pytest.raises(RuntimeError, match="activated lnschema_txgnn"):
        sync._registry_models()


def test_cli_parses_progress_and_all_remaining_contract() -> None:
    args = sync.build_parser().parse_args(["gs://jouvencekb/kg/v2", "--relation", REL, "--edge-limit", "0", "--evidence-limit", "0", "--progress-jsonl", "x.jsonl"])
    assert (args.edge_limit, args.evidence_limit, args.progress_jsonl) == (0, 0, "x.jsonl")
