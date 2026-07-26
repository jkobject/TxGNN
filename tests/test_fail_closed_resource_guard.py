from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from manage_db.fail_closed_resource_guard import (
    PERSISTENCE_FAILURE_EXIT_CODE,
    RESOURCE_LIMIT_EXIT_CODE,
    ResourceGuardIdentity,
    ResourceSnapshot,
    ResourceThresholds,
    atomic_json,
    enforce_resource_guard,
    evaluate_resource_guard,
)


class ExitSignal(BaseException):
    def __init__(self, code: int) -> None:
        self.code = code


def _identity() -> ResourceGuardIdentity:
    return ResourceGuardIdentity(
        task_id="t_b257f671",
        gcp_project_id="jkobject-1549353370965",
        zone="europe-west1-b",
        instance="txgnn-worker",
        instance_id="4268456364292488510",
        lease_id="c214a4024f89419fb124436570d28339",
        generation=37,
    )


def _thresholds() -> ResourceThresholds:
    return ResourceThresholds(
        max_rss_bytes=100,
        min_mem_available_bytes=50,
        min_root_free_bytes=40,
        max_task_growth_bytes=30,
    )


def _snapshot(**overrides: int) -> ResourceSnapshot:
    values = {
        "rss_bytes": 80,
        "mem_available_bytes": 60,
        "root_free_bytes": 50,
        "task_growth_bytes": 20,
    }
    values.update(overrides)
    return ResourceSnapshot(
        **values,
        measurement_started_at="2026-07-26T14:02:46.000000+00:00",
        measurement_finished_at="2026-07-26T14:02:46.100000+00:00",
    )


@pytest.mark.parametrize(
    ("overrides", "predicate"),
    [
        ({"rss_bytes": 101}, "rss_bytes > max_rss_bytes"),
        ({"mem_available_bytes": 49}, "mem_available_bytes < min_mem_available_bytes"),
        ({"root_free_bytes": 39}, "root_free_bytes < min_root_free_bytes"),
        ({"task_growth_bytes": 31}, "task_growth_bytes > max_task_growth_bytes"),
    ],
)
def test_each_resource_guard_is_attributed_independently(
    overrides: dict[str, int], predicate: str
) -> None:
    decision = evaluate_resource_guard(
        snapshot=_snapshot(**overrides),
        thresholds=_thresholds(),
        identity=_identity(),
        phase="sqlite_quick_check",
        decision_at="2026-07-26T14:02:46.200000+00:00",
    )

    assert decision["triggered_predicates"] == [predicate]
    assert decision["decision"] == "terminate"
    assert decision["intended_exit_code"] == RESOURCE_LIMIT_EXIT_CODE
    assert sum(operand["triggered"] for operand in decision["operands"].values()) == 1


def test_boundary_equality_does_not_trigger_any_guard() -> None:
    decision = evaluate_resource_guard(
        snapshot=_snapshot(
            rss_bytes=100,
            mem_available_bytes=50,
            root_free_bytes=40,
            task_growth_bytes=30,
        ),
        thresholds=_thresholds(),
        identity=_identity(),
        phase="sqlite_quick_check",
        decision_at="2026-07-26T14:02:46.200000+00:00",
    )

    assert decision["triggered_predicates"] == []
    assert decision["decision"] == "continue"
    assert decision["intended_exit_code"] is None
    assert all(not operand["triggered"] for operand in decision["operands"].values())


def test_multiple_simultaneous_triggers_are_all_attributed() -> None:
    decision = evaluate_resource_guard(
        snapshot=_snapshot(rss_bytes=101, mem_available_bytes=49, task_growth_bytes=31),
        thresholds=_thresholds(),
        identity=_identity(),
        phase="sqlite_quick_check",
        decision_at="2026-07-26T14:02:46.200000+00:00",
    )

    assert decision["triggered_predicates"] == [
        "rss_bytes > max_rss_bytes",
        "mem_available_bytes < min_mem_available_bytes",
        "task_growth_bytes > max_task_growth_bytes",
    ]


def test_trigger_record_is_persisted_before_resource_exit(tmp_path: Path) -> None:
    events: list[tuple[str, Any]] = []
    decision_path = tmp_path / "resource-guard-decision.json"

    def persist(path: Path, payload: dict[str, Any]) -> None:
        events.append(("persist", payload))
        atomic_json(path, payload)

    def terminate(code: int) -> None:
        events.append(("terminate", code))
        raise ExitSignal(code)

    with pytest.raises(ExitSignal) as raised:
        enforce_resource_guard(
            snapshot=_snapshot(rss_bytes=101),
            thresholds=_thresholds(),
            identity=_identity(),
            phase="sqlite_quick_check",
            decision_path=decision_path,
            persist=persist,
            terminate=terminate,
            decision_at="2026-07-26T14:02:46.200000+00:00",
        )

    assert raised.value.code == RESOURCE_LIMIT_EXIT_CODE
    assert [event[0] for event in events] == ["persist", "terminate"]
    persisted = json.loads(decision_path.read_text())
    assert persisted == events[0][1]
    assert persisted["phase"] == "sqlite_quick_check"
    assert persisted["task_identity"] == {"task_id": "t_b257f671"}
    assert persisted["lifecycle_identity"]["generation"] == 37
    assert set(persisted["operands"]) == {
        "rss_bytes",
        "mem_available_bytes",
        "root_free_bytes",
        "task_growth_bytes",
    }


def test_persistence_failure_uses_distinct_fail_closed_exit(tmp_path: Path) -> None:
    events: list[tuple[str, Any]] = []

    def persist(_path: Path, _payload: dict[str, Any]) -> None:
        events.append(("persist_failed", None))
        raise OSError("disk unavailable")

    def terminate(code: int) -> None:
        events.append(("terminate", code))
        raise ExitSignal(code)

    with pytest.raises(ExitSignal) as raised:
        enforce_resource_guard(
            snapshot=_snapshot(root_free_bytes=39),
            thresholds=_thresholds(),
            identity=_identity(),
            phase="sqlite_quick_check",
            decision_path=tmp_path / "resource-guard-decision.json",
            persist=persist,
            terminate=terminate,
            decision_at="2026-07-26T14:02:46.200000+00:00",
        )

    assert raised.value.code == PERSISTENCE_FAILURE_EXIT_CODE
    assert PERSISTENCE_FAILURE_EXIT_CODE != RESOURCE_LIMIT_EXIT_CODE
    assert events == [
        ("persist_failed", None),
        ("terminate", PERSISTENCE_FAILURE_EXIT_CODE),
    ]


def test_safe_decision_does_not_persist_or_terminate(tmp_path: Path) -> None:
    events: list[str] = []

    decision = enforce_resource_guard(
        snapshot=_snapshot(),
        thresholds=_thresholds(),
        identity=_identity(),
        phase="sqlite_quick_check",
        decision_path=tmp_path / "resource-guard-decision.json",
        persist=lambda _path, _payload: events.append("persist"),
        terminate=lambda _code: events.append("terminate"),
        decision_at="2026-07-26T14:02:46.200000+00:00",
    )

    assert decision["decision"] == "continue"
    assert events == []
