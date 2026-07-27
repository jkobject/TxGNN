import importlib.util
import sys
from pathlib import Path

WATCHDOG_PATH = Path("/Users/jkobject/.hermes/scripts/txgnn_remote_remap_watchdog.py")
_spec = importlib.util.spec_from_file_location("txgnn_remote_remap_watchdog", WATCHDOG_PATH)
assert _spec and _spec.loader
watchdog = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = watchdog
_spec.loader.exec_module(watchdog)

VALIDATED_EVIDENCE = {
    "task_id": "t_98f49c27",
    "rc": 0,
    "stderr_bytes": 0,
    "canonical_writes": False,
    "no_canonical_writes_validation": True,
    "staged_only": True,
    "latest_run_dir": "/home/jkobject/txgnn-run/repo/artifacts/reports/remote_supervisor/remap/20260706T051617Z_tiles6648_rows3318139_max100",
    "progress": {
        "completed_crm_rows": 3327980,
        "planned_crm_rows": 3327980,
        "remaining_crm_rows": 0,
        "completion_fraction": 1.0,
    },
}


def test_acknowledged_completion_reason_accepts_validated_row_tuple() -> None:
    assert watchdog.acknowledged_completion_reason(
        "✅ remote ReMap complete 3327980/3327980 rows", VALIDATED_EVIDENCE
    ) == "already validated by t_98f49c27 for 3327980/3327980 rows"


def test_acknowledged_completion_reason_rejects_count_regression() -> None:
    assert watchdog.acknowledged_completion_reason(
        "✅ remote ReMap complete 3327979/3327980 rows", VALIDATED_EVIDENCE
    ) is None


def test_acknowledged_completion_reason_rejects_changed_run_identity() -> None:
    assert watchdog.acknowledged_completion_reason(
        "✅ remote ReMap complete 3327980/3327980 rows run_dir=/different/run", VALIDATED_EVIDENCE
    ) is None
    assert watchdog.acknowledged_completion_reason(
        "✅ remote ReMap complete 3327980/3327980 rows latest_run_dir: /different/run", VALIDATED_EVIDENCE
    ) is None
    assert watchdog.acknowledged_completion_reason(
        "✅ remote ReMap complete 3327980/3327980 rows /artifacts/reports/remote_supervisor/remap/different",
        VALIDATED_EVIDENCE,
    ) is None


def test_acknowledged_completion_reason_allows_matching_run_identity() -> None:
    text = (
        "✅ remote ReMap complete 3327980/3327980 rows "
        f"latest_run_dir={VALIDATED_EVIDENCE['latest_run_dir']}"
    )

    assert watchdog.acknowledged_completion_reason(text, VALIDATED_EVIDENCE) == (
        "already validated by t_98f49c27 for 3327980/3327980 rows"
    )


def test_acknowledged_completion_reason_rejects_mixed_matching_and_different_run_identities() -> None:
    identity_fragments = [
        f"latest_run_dir={VALIDATED_EVIDENCE['latest_run_dir']} run_dir=/different/run",
        f"run_dir=/different/run latest_run_dir={VALIDATED_EVIDENCE['latest_run_dir']}",
        f"latest_run_dir={VALIDATED_EVIDENCE['latest_run_dir']} /artifacts/reports/remote_supervisor/remap/different",
    ]

    for identity_fragment in identity_fragments:
        assert watchdog.acknowledged_completion_reason(
            f"✅ remote ReMap complete 3327980/3327980 rows {identity_fragment}",
            VALIDATED_EVIDENCE,
        ) is None


def test_acknowledged_completion_reason_rejects_validation_inconsistency() -> None:
    inconsistent = dict(VALIDATED_EVIDENCE)
    inconsistent["no_canonical_writes_validation"] = False

    assert watchdog.acknowledged_completion_reason(
        "✅ remote ReMap complete 3327980/3327980 rows", inconsistent
    ) is None


def test_main_is_retired_silent_and_does_not_touch_remote(monkeypatch, capsys) -> None:
    calls = []
    monkeypatch.setattr(watchdog, "vm_status", lambda: calls.append("vm_status"))
    monkeypatch.setattr(watchdog, "dns_probe", lambda: calls.append("dns_probe"))
    monkeypatch.setattr(watchdog, "run_once", lambda: calls.append("run_once"))

    assert watchdog.main() == 0
    assert capsys.readouterr().out == ""
    assert calls == []
