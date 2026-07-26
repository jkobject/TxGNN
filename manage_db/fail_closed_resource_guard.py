"""Durably attribute fail-closed resource-limit terminations.

Long-running payloads must not collapse several resource predicates into an
unattributed ``os._exit``.  This module evaluates one explicit snapshot,
persists every operand and threshold atomically, and only then invokes the
injected termination function.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

RESOURCE_LIMIT_EXIT_CODE = 74
PERSISTENCE_FAILURE_EXIT_CODE = 75


@dataclass(frozen=True)
class ResourceGuardIdentity:
    """Task and lifecycle identity attached to a guard decision."""

    task_id: str
    gcp_project_id: str
    zone: str
    instance: str
    instance_id: str
    lease_id: str
    generation: int


@dataclass(frozen=True)
class ResourceThresholds:
    """Byte thresholds preserving the generation-37 strict comparisons."""

    max_rss_bytes: int
    min_mem_available_bytes: int
    min_root_free_bytes: int
    max_task_growth_bytes: int


@dataclass(frozen=True)
class ResourceSnapshot:
    """One bounded measurement window used for a single guard decision."""

    rss_bytes: int
    mem_available_bytes: int
    root_free_bytes: int
    task_growth_bytes: int
    measurement_started_at: str
    measurement_finished_at: str


Persist = Callable[[Path, dict[str, Any]], None]
Terminate = Callable[[int], NoReturn]


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON through fsync + atomic rename, then fsync its directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with pending.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        pending.unlink(missing_ok=True)


def evaluate_resource_guard(
    *,
    snapshot: ResourceSnapshot,
    thresholds: ResourceThresholds,
    identity: ResourceGuardIdentity,
    phase: str,
    decision_at: str | None = None,
) -> dict[str, Any]:
    """Return a complete, deterministic decision for one resource snapshot."""

    operand_specs = (
        (
            "rss_bytes",
            snapshot.rss_bytes,
            ">",
            "max_rss_bytes",
            thresholds.max_rss_bytes,
            snapshot.rss_bytes > thresholds.max_rss_bytes,
        ),
        (
            "mem_available_bytes",
            snapshot.mem_available_bytes,
            "<",
            "min_mem_available_bytes",
            thresholds.min_mem_available_bytes,
            snapshot.mem_available_bytes < thresholds.min_mem_available_bytes,
        ),
        (
            "root_free_bytes",
            snapshot.root_free_bytes,
            "<",
            "min_root_free_bytes",
            thresholds.min_root_free_bytes,
            snapshot.root_free_bytes < thresholds.min_root_free_bytes,
        ),
        (
            "task_growth_bytes",
            snapshot.task_growth_bytes,
            ">",
            "max_task_growth_bytes",
            thresholds.max_task_growth_bytes,
            snapshot.task_growth_bytes > thresholds.max_task_growth_bytes,
        ),
    )
    operands = {
        name: {
            "observed_bytes": observed,
            "operator": operator,
            "threshold_name": threshold_name,
            "threshold_bytes": threshold,
            "triggered": triggered,
        }
        for name, observed, operator, threshold_name, threshold, triggered in operand_specs
    }
    triggered_predicates = [
        f"{name} {operator} {threshold_name}"
        for name, _observed, operator, threshold_name, _threshold, triggered in operand_specs
        if triggered
    ]
    triggered = bool(triggered_predicates)
    return {
        "schema_version": 1,
        "kind": "resource_guard_decision",
        "decision_at": decision_at or utcnow(),
        "phase": phase,
        "task_identity": {"task_id": identity.task_id},
        "lifecycle_identity": {
            "gcp_project_id": identity.gcp_project_id,
            "zone": identity.zone,
            "instance": identity.instance,
            "instance_id": identity.instance_id,
            "lease_id": identity.lease_id,
            "generation": identity.generation,
        },
        "measurement_window": {
            "started_at": snapshot.measurement_started_at,
            "finished_at": snapshot.measurement_finished_at,
        },
        "operands": operands,
        "triggered_predicates": triggered_predicates,
        "decision": "terminate" if triggered else "continue",
        "intended_exit_code": RESOURCE_LIMIT_EXIT_CODE if triggered else None,
    }


def enforce_resource_guard(
    *,
    snapshot: ResourceSnapshot,
    thresholds: ResourceThresholds,
    identity: ResourceGuardIdentity,
    phase: str,
    decision_path: Path,
    persist: Persist = atomic_json,
    terminate: Terminate = os._exit,
    decision_at: str | None = None,
) -> dict[str, Any]:
    """Persist an attributed trigger before exiting; fail distinctly on I/O loss."""

    decision = evaluate_resource_guard(
        snapshot=snapshot,
        thresholds=thresholds,
        identity=identity,
        phase=phase,
        decision_at=decision_at,
    )
    if decision["decision"] == "continue":
        return decision

    # Resource attribution must fail closed even during interpreter-level
    # interruptions such as SystemExit or KeyboardInterrupt.
    try:
        persist(decision_path, decision)
    except BaseException:  # noqa: BLE001
        terminate(PERSISTENCE_FAILURE_EXIT_CODE)
        raise RuntimeError(
            "resource guard persistence failed and termination returned unexpectedly"
        )

    terminate(RESOURCE_LIMIT_EXIT_CODE)
    raise RuntimeError("resource guard termination returned unexpectedly")
