from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from manage_db.lamin_wave_runner import (
    ACCEPTED_MANIFEST_SHA256,
    DurableWaveLedger,
    ExecutionResult,
    ResourceBounds,
    StopCriteria,
    WavePlan,
    WriterCapability,
    issue_writer_capability,
    load_accepted_manifest,
    main,
    plan_waves,
    run_wave,
    validate_wave_spec,
)


FIXTURE = Path(__file__).parent / "fixtures" / "full_kg_lamin_delta.json"


def _plan(tmp_path: Path) -> WavePlan:
    rows = load_accepted_manifest(FIXTURE)
    return plan_waves(rows, artifact_root=tmp_path / "run")


def test_loads_exact_accepted_72_lane_contract_without_payload_scan() -> None:
    rows = load_accepted_manifest(FIXTURE)

    assert len(rows) == 72
    assert [row["family"] for row in rows].count("node") == 13
    assert [row["family"] for row in rows].count("edge") == 39
    assert [row["family"] for row in rows].count("evidence") == 20
    assert sum(row["source_rows"] for row in rows if row["family"] == "node") == 52_565_491
    assert sum(row["current_lamin_rows"] for row in rows if row["family"] == "node") == 3_771_054
    assert sum(row["remaining_delta"] for row in rows if row["family"] == "node") == 48_794_437
    assert sum(row["source_rows"] for row in rows if row["family"] == "edge") == 101_743_458
    assert sum(row["current_lamin_rows"] for row in rows if row["family"] == "edge") == 1_431_264
    assert sum(row["remaining_delta"] for row in rows if row["family"] == "edge") == 100_312_194
    assert sum(row["source_rows"] for row in rows if row["family"] == "evidence") == 76_565_213
    assert sum(row["current_lamin_rows"] for row in rows if row["family"] == "evidence") == 1_389_167
    assert sum(row["remaining_delta"] for row in rows if row["family"] == "evidence") == 75_176_046
    assert sum(row["current_lamin_rows"] == 0 for row in rows) == 53
    assert {
        row["lane_key"]: row["remaining_delta"]
        for row in rows
        if row["remaining_delta"] < 0
    } == {"node:cell_line": -165_943, "node:phenotype": -6_270}
    assert ACCEPTED_MANIFEST_SHA256 == "3f587a2947e1d4e1a2685a886eb8b65e6b2fa3bbeb01431ac846ff617b1ffb64"


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unknown", "ambiguous"])
def test_manifest_rejects_lane_contract_tampering(tmp_path: Path, mutation: str) -> None:
    rows = json.loads(FIXTURE.read_text())
    if mutation == "duplicate":
        rows[-1] = dict(rows[0])
    elif mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[0]["lane_key"] = "edge:not_canonical"
        rows[0]["canonical_name"] = "not_canonical"
    else:
        rows[0]["mapping_identifiable"] = False
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(rows))

    with pytest.raises(ValueError):
        load_accepted_manifest(path)


def test_planner_rejects_unattested_rows_even_when_values_match(tmp_path: Path) -> None:
    accepted = load_accepted_manifest(FIXTURE)
    unattested_copy = [dict(row) for row in accepted]

    with pytest.raises(ValueError, match="attested"):
        plan_waves(unattested_copy, artifact_root=tmp_path / "run")


def test_planner_groups_independent_edge_and_evidence_lanes_deterministically(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    assert len(plan.waves) == 41
    assert sum(len(wave.lane_keys) for wave in plan.waves) == 59
    assert [wave.wave_id for wave in plan.waves] == sorted(wave.wave_id for wave in plan.waves)
    paired = next(wave for wave in plan.waves if wave.wave_id == "relation:enhancer_regulates_gene")
    assert paired.lane_keys == (
        "edge:enhancer_regulates_gene",
        "evidence:enhancer_regulates_gene",
    )
    assert paired.source_rows == (48_808_144, 48_810_390)
    assert paired.current_rows == (1_345_000, 1_345_000)
    assert paired.remaining_deltas == (47_463_144, 47_465_390)
    assert paired.checkpoints.accepted == 10_315_000
    assert paired.checkpoints.sealed_candidate == 11_345_000
    assert paired.checkpoints.live_count == 1_345_000


def test_cli_dry_run_emits_deterministic_plan_covering_all_manifest_lanes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    artifact_root = tmp_path / "run"

    assert main([str(FIXTURE), "--artifact-root", str(artifact_root), "--output", str(first)]) == 0
    assert main([str(FIXTURE), "--artifact-root", str(artifact_root), "--output", str(second)]) == 0

    first_payload = json.loads(first.read_text())
    second_payload = json.loads(second.read_text())
    assert first_payload == second_payload
    assert first_payload["manifest_lane_count"] == 72
    assert first_payload["planned_lane_count"] == 59
    assert first_payload["zero_no_work_count"] == 11
    assert first_payload["negative_no_work_count"] == 2


def test_node_waves_resume_from_independent_manifest_current_counts(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    gene = next(item for item in plan.waves if item.wave_id == "node:gene")
    mutation = next(item for item in plan.waves if item.wave_id == "node:mutation")

    assert gene.start_checkpoints == (109_325,)
    assert gene.end_checkpoints == (114_325,)
    assert gene.argv[gene.argv.index("--row-offset") + 1] == "109325"
    assert mutation.start_checkpoints == (2_589_508,)
    assert mutation.end_checkpoints == (2_589_509,)
    assert mutation.argv[mutation.argv.index("--row-offset") + 1] == "2589508"


def test_planner_preserves_negative_lanes_as_no_work_anomalies(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    assert plan.negative_no_work == {
        "node:cell_line": -165_943,
        "node:phenotype": -6_270,
    }
    assert all(delta > 0 for wave in plan.waves for delta in wave.remaining_deltas)
    assert not any("cell_line" in wave.lane_keys or "phenotype" in wave.lane_keys for wave in plan.waves)


def test_planner_preserves_zero_delta_lanes_as_explicit_no_work(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    assert len(plan.zero_no_work) == 11
    assert plan.zero_no_work["edge:molecule_targets_gene"] == 0
    assert plan.zero_no_work["evidence:molecule_targets_gene"] == 0
    assert plan.zero_no_work["node:transcript"] == 0
    assert set(plan.zero_no_work).isdisjoint(
        lane_key for wave in plan.waves for lane_key in wave.lane_keys
    )


def test_every_wave_is_exactly_allowlisted_bounded_and_verifiable(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    for wave in plan.waves:
        validate_wave_spec(wave)
        assert wave.argv and isinstance(wave.argv, tuple)
        assert wave.verification_argvs and all(command for command in wave.verification_argvs)
        assert 0 < wave.bounds.max_rows <= 5_000
        assert 0 < wave.bounds.max_chunks <= 1
        assert 0 < wave.bounds.max_runtime_seconds <= 900
        assert wave.bounds.resources == ResourceBounds(cpu_cores=2, memory_bytes=4 * 1024**3)
        assert wave.progress_path.is_absolute()
        assert wave.ack_path.is_absolute()
        assert wave.ledger_path.is_absolute()
        assert wave.stop_criteria == StopCriteria(
            mismatch_count=0,
            require_selected_live=True,
            require_write_flush_fsync_ack=True,
        )
        assert wave.max_retries == 2

    edge_only = next(
        wave for wave in plan.waves if wave.wave_id == "relation:cell_line_derived_from_tissue"
    )
    assert edge_only.lane_keys == ("edge:cell_line_derived_from_tissue",)
    assert "--skip-evidence" in edge_only.argv


def test_wave_validation_rejects_unbounded_limit_zero_all_lane_and_shell_text(tmp_path: Path) -> None:
    wave = _plan(tmp_path).waves[0]

    bad_argvs = [
        wave.argv + ("--max-rows", "0"),
        tuple(arg for arg in wave.argv if arg not in wave.allowlist),
        ("sh", "-c", "python -m manage_db.sync_parquet_nodes_to_lamindb --write"),
    ]
    for argv in bad_argvs:
        with pytest.raises(ValueError):
            validate_wave_spec(replace(wave, argv=argv))


def test_wave_validation_binds_argv_module_offsets_and_limits_to_spec(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    node = next(item for item in plan.waves if item.wave_id == "node:gene")
    relation = next(item for item in plan.waves if item.wave_id == "relation:enhancer_regulates_gene")

    bad_module = list(node.argv)
    bad_module[bad_module.index("manage_db.sync_parquet_nodes_to_lamindb")] = "manage_db.unsafe"
    bad_node_offset = list(node.argv)
    bad_node_offset[bad_node_offset.index("--row-offset") + 1] = "0"
    bad_relation_limit = list(relation.argv)
    bad_relation_limit[bad_relation_limit.index("--edge-limit") + 1] = "5001"
    bad_duplicate_max_chunks = relation.argv + ("--max-chunks", "9999")

    for wave, argv in (
        (node, bad_module),
        (node, bad_node_offset),
        (relation, bad_relation_limit),
        (relation, bad_duplicate_max_chunks),
    ):
        with pytest.raises(ValueError):
            validate_wave_spec(replace(wave, argv=tuple(argv)))

    bad_verification = tuple(arg for arg in bad_node_offset if arg != "--write")
    with pytest.raises(ValueError):
        validate_wave_spec(replace(node, verification_argvs=(bad_verification,)))


@pytest.mark.parametrize(
    "change",
    [
        {"instance": "jkobject/repo"},
        {"kg_root": "/Users/jkobject/mnt/gcs/jouvencekb-kg/v2"},
        {"execution_host": "mac-mini"},
        {"verification_argvs": ()},
        {"max_retries": 3},
    ],
)
def test_wave_validation_fails_closed_on_unsafe_execution_contract(tmp_path: Path, change: dict) -> None:
    wave = _plan(tmp_path).waves[0]

    with pytest.raises(ValueError):
        validate_wave_spec(replace(wave, **change))


def test_wave_validation_rejects_zero_resource_bounds(tmp_path: Path) -> None:
    wave = _plan(tmp_path).waves[0]
    bounds = replace(
        wave.bounds,
        resources=replace(wave.bounds.resources, memory_bytes=0),
    )

    with pytest.raises(ValueError):
        validate_wave_spec(replace(wave, bounds=bounds))


def test_run_rejects_forged_stale_or_wrong_plan_capability(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = plan.waves[0]
    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], *, timeout: int) -> ExecutionResult:
        calls.append(argv)
        return ExecutionResult(returncode=0, summary={"status": "complete"})

    forged = WriterCapability("forged", plan.digest, expires_at=999)
    with pytest.raises(RuntimeError):
        run_wave(wave, plan=plan, capability=forged, executor=executor, now=1)

    with issue_writer_capability(plan, ttl_seconds=5, now=10) as capability:
        with pytest.raises(RuntimeError):
            run_wave(wave, plan=replace(plan, digest="other"), capability=capability, executor=executor, now=11)
        with pytest.raises(RuntimeError):
            run_wave(wave, plan=plan, capability=capability, executor=executor, now=16)

    with pytest.raises(RuntimeError):
        run_wave(wave, plan=plan, capability=capability, executor=executor, now=12)
    assert calls == []


def test_writer_capability_allows_only_one_logical_writer(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    with issue_writer_capability(plan, ttl_seconds=5, now=10):
        with pytest.raises(RuntimeError, match="one logical writer"):
            with issue_writer_capability(plan, ttl_seconds=5, now=10):
                pass


def test_run_executes_argv_without_shell_only_with_fresh_capability(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = plan.waves[0]
    calls: list[tuple[tuple[str, ...], int]] = []

    def executor(argv: tuple[str, ...], *, timeout: int) -> ExecutionResult:
        calls.append((argv, timeout))
        if argv == wave.argv:
            return ExecutionResult(returncode=0, summary={"status": "write_complete"})
        selected = wave.end_checkpoints[0] - wave.start_checkpoints[0]
        return ExecutionResult(
            returncode=0,
            summary={
                "mismatch_count": 0,
                "lanes": {
                    wave.lane_keys[0]: {
                        "cursor": wave.end_checkpoints[0],
                        "attempted": selected,
                        "selected_live": selected,
                    }
                },
            },
        )

    with issue_writer_capability(plan, ttl_seconds=5, now=10) as capability:
        result = run_wave(
            wave,
            plan=plan,
            capability=capability,
            executor=executor,
            now=11,
            hostname="txgnn-worker",
        )

    assert result.returncode == 0
    assert calls == [
        (wave.argv, wave.bounds.max_runtime_seconds),
        (wave.verification_argvs[0], wave.bounds.max_runtime_seconds),
    ]
    assert wave.ledger_path.exists()


def test_run_refuses_missing_selected_live_verification_without_checkpoint(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = plan.waves[0]

    def executor(argv: tuple[str, ...], *, timeout: int) -> ExecutionResult:
        if argv == wave.argv:
            return ExecutionResult(returncode=0, summary={"status": "write_complete"})
        return ExecutionResult(returncode=0, summary={"status": "no_verification"})

    with issue_writer_capability(plan, ttl_seconds=5, now=10) as capability:
        with pytest.raises(RuntimeError, match="verification"):
            run_wave(
                wave,
                plan=plan,
                capability=capability,
                executor=executor,
                now=11,
                hostname="txgnn-worker",
            )

    assert not wave.ledger_path.exists()


def test_run_stops_after_at_most_two_retries(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = plan.waves[0]
    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], *, timeout: int) -> ExecutionResult:
        calls.append(argv)
        return ExecutionResult(returncode=75, summary={"status": "transient_failure"})

    with issue_writer_capability(plan, ttl_seconds=5, now=10) as capability:
        result = run_wave(
            wave,
            plan=plan,
            capability=capability,
            executor=executor,
            now=11,
            hostname="txgnn-worker",
        )

    assert result.returncode == 75
    assert calls == [wave.argv, wave.argv, wave.argv]


def test_run_refuses_actual_host_mismatch_before_execution(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = plan.waves[0]
    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], *, timeout: int) -> ExecutionResult:
        calls.append(argv)
        return ExecutionResult(returncode=0, summary={})

    with issue_writer_capability(plan, ttl_seconds=5, now=10) as capability:
        with pytest.raises(RuntimeError, match="txgnn-worker"):
            run_wave(
                wave,
                plan=plan,
                capability=capability,
                executor=executor,
                now=11,
                hostname="mac-mini",
            )

    assert calls == []


def test_ledger_preserves_independent_asymmetric_cursors(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = next(item for item in plan.waves if item.wave_id == "relation:enhancer_regulates_gene")
    ledger = DurableWaveLedger(wave)

    checkpoint = ledger.commit_verified(
        edge_cursor=10_320_000,
        evidence_cursor=10_317_000,
        edge_attempted=5_000,
        evidence_attempted=2_000,
        selected_live_edges=5_000,
        selected_live_evidence=2_000,
        mismatch_count=0,
    )

    assert checkpoint["durable_edge_current_offset"] == 10_320_000
    assert checkpoint["durable_evidence_current_offset"] == 10_317_000
    assert checkpoint["current_offset"] == 10_317_000


def test_ledger_supports_node_and_repeated_edge_only_commits(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    node = next(item for item in plan.waves if item.wave_id == "node:mutation")
    node_checkpoint = DurableWaveLedger(node).commit_verified_lanes(
        lane_results={
            "node:mutation": {
                "cursor": 2_589_509,
                "attempted": 1,
                "selected_live": 1,
            }
        },
        mismatch_count=0,
    )
    assert node_checkpoint["current_offset"] == 2_589_509

    edge_only = next(
        item for item in plan.waves if item.wave_id == "relation:cell_line_derived_from_tissue"
    )
    start = edge_only.start_checkpoints[0]
    first = DurableWaveLedger(edge_only).commit_verified(
        edge_cursor=start + 2,
        evidence_cursor=0,
        edge_attempted=2,
        evidence_attempted=0,
        selected_live_edges=2,
        selected_live_evidence=0,
        mismatch_count=0,
    )
    second = DurableWaveLedger(edge_only).commit_verified(
        edge_cursor=start + 4,
        evidence_cursor=0,
        edge_attempted=2,
        evidence_attempted=0,
        selected_live_edges=2,
        selected_live_evidence=0,
        mismatch_count=0,
    )
    assert first["current_offset"] == start + 2
    assert second["current_offset"] == start + 4


def test_ledger_refuses_unverified_cursor_advance(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    wave = next(item for item in plan.waves if item.wave_id == "relation:enhancer_regulates_gene")
    ledger = DurableWaveLedger(wave)

    with pytest.raises(RuntimeError, match="verification"):
        ledger.commit_verified(
            edge_cursor=10_320_000,
            evidence_cursor=10_320_000,
            edge_attempted=5_000,
            evidence_attempted=5_000,
            selected_live_edges=4_999,
            selected_live_evidence=5_000,
            mismatch_count=1,
        )

    with pytest.raises(RuntimeError):
        ledger.commit_verified(
            edge_cursor=10_320_001,
            evidence_cursor=10_320_000,
            edge_attempted=5_001,
            evidence_attempted=5_000,
            selected_live_edges=5_001,
            selected_live_evidence=5_000,
            mismatch_count=0,
        )
    assert not wave.ledger_path.exists()


def test_ledger_orders_progress_fsync_ack_before_checkpoint(tmp_path: Path, monkeypatch) -> None:
    plan = _plan(tmp_path)
    wave = next(item for item in plan.waves if item.wave_id == "relation:enhancer_regulates_gene")
    ledger = DurableWaveLedger(wave)
    events: list[str] = []

    monkeypatch.setattr(ledger, "_fsync", lambda handle, label: events.append(f"fsync:{label}"))
    checkpoint = ledger.commit_verified(
        edge_cursor=10_320_000,
        evidence_cursor=10_320_000,
        edge_attempted=5_000,
        evidence_attempted=5_000,
        selected_live_edges=5_000,
        selected_live_evidence=5_000,
        mismatch_count=0,
    )

    assert events == ["fsync:progress", "fsync:ack", "fsync:ledger", "fsync:ledger_dir"]
    ack = json.loads(wave.ack_path.read_text().splitlines()[-1])
    progress_line = wave.progress_path.read_bytes().splitlines(keepends=True)[-1]
    assert ack["record_sha256"] == __import__("hashlib").sha256(progress_line).hexdigest()
    assert ack["progress_path"] == str(wave.progress_path)
    assert checkpoint["current_offset"] == 10_320_000
    assert json.loads(wave.ledger_path.read_text())["current_offset"] == 10_320_000


def test_ledger_does_not_advance_when_ack_fsync_fails(tmp_path: Path, monkeypatch) -> None:
    plan = _plan(tmp_path)
    wave = next(item for item in plan.waves if item.wave_id == "relation:enhancer_regulates_gene")
    ledger = DurableWaveLedger(wave)

    def fail_ack(_handle, label: str) -> None:
        if label == "ack":
            raise OSError("fsync failed")

    monkeypatch.setattr(ledger, "_fsync", fail_ack)
    with pytest.raises(OSError, match="fsync failed"):
        ledger.commit_verified(
            edge_cursor=10_320_000,
            evidence_cursor=10_320_000,
            edge_attempted=5_000,
            evidence_attempted=5_000,
            selected_live_edges=5_000,
            selected_live_evidence=5_000,
            mismatch_count=0,
        )

    assert not wave.ledger_path.exists()


def test_ledger_removes_uncommitted_checkpoint_when_directory_fsync_fails(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    wave = next(item for item in plan.waves if item.wave_id == "relation:enhancer_regulates_gene")
    ledger = DurableWaveLedger(wave)
    original_fsync = ledger._fsync

    def fail_directory(handle, label: str) -> None:
        if label == "ledger_dir":
            raise OSError("directory fsync failed")
        original_fsync(handle, label)

    monkeypatch.setattr(ledger, "_fsync", fail_directory)
    with pytest.raises(OSError, match="directory fsync failed"):
        ledger.commit_verified(
            edge_cursor=10_320_000,
            evidence_cursor=10_320_000,
            edge_attempted=5_000,
            evidence_attempted=5_000,
            selected_live_edges=5_000,
            selected_live_evidence=5_000,
            mismatch_count=0,
        )

    assert not wave.ledger_path.exists()
