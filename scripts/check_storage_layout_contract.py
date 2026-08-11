#!/usr/bin/env python3
"""Validate the stable Jouvence bucket layout and active repository references."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = (
    ROOT / "manage_db",
    ROOT / "scripts",
    ROOT / "envs",
    ROOT / "todo.d",
    ROOT / "docs" / "guides",
)
SINGLE_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "TODO.md",
    ROOT / "docs" / "storage.md",
    ROOT / "docs" / "getting-started-data.md",
    ROOT / "docs" / "txgnn_access_runbook.md",
)
TEXT_SUFFIXES = {".py", ".sh", ".md", ".toml", ".yaml", ".yml", ".json"}
FORBIDDEN = (
    "gs://jouvencekb/kg/",
    "gs://jouvencekb/staged",
    "gs://jouvencekb/metadata",
    "gs://jouvencekb/proof",
    "gs://jouvencekb/main/staged",
    "gs://jouvencekb/main/staging",
    "gs://jouvencekb/main/metadata",
    "gs://jouvencekb/main/proof",
    "/jouvencekb/main/staged",
    "/jouvencekb/main/staging",
    "/jouvencekb-kg/v2",
)
ALLOWED_TOP_LEVEL_OBJECTS = {"README.md"}
REQUIRED_TOP_LEVEL_PREFIXES = {".lamin/", "raw/", "main/"}
OPTIONAL_TOP_LEVEL_PREFIXES = {"pyg/", "staging/"}
ALLOWED_TOP_LEVEL_PREFIXES = REQUIRED_TOP_LEVEL_PREFIXES | OPTIONAL_TOP_LEVEL_PREFIXES
EXPECTED_LIFECYCLE_RULES: list[dict[str, object]] = []
EXPECTED_SOFT_DELETE_SECONDS = 604800


def active_files() -> list[Path]:
    paths = list(SINGLE_FILES)
    for root in ACTIVE_ROOTS:
        paths.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and path.name != "check_storage_layout_contract.py"
        )
    return sorted(set(paths))


def check_static() -> list[str]:
    errors: list[str] = []
    for path in active_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for forbidden in FORBIDDEN:
            if forbidden in text:
                errors.append(f"{path.relative_to(ROOT)} contains forbidden storage root {forbidden!r}")
    return errors


def check_live() -> list[str]:
    import importlib

    client = importlib.import_module("google.cloud.storage").Client()
    bucket = client.bucket("jouvencekb")
    bucket.reload()
    iterator = client.list_blobs(bucket, delimiter="/", max_results=1000)
    root_objects = {blob.name for blob in iterator}
    prefixes = set(iterator.prefixes)
    errors = []
    unexpected_objects = sorted(root_objects - ALLOWED_TOP_LEVEL_OBJECTS)
    unexpected_prefixes = sorted(prefixes - ALLOWED_TOP_LEVEL_PREFIXES)
    missing_objects = sorted(ALLOWED_TOP_LEVEL_OBJECTS - root_objects)
    # GCS has no real empty directories. Derived `pyg/` and temporary `staging/`
    # therefore appear only while they contain live objects.
    missing_prefixes = sorted(REQUIRED_TOP_LEVEL_PREFIXES - prefixes)
    if unexpected_objects:
        errors.append(f"unexpected root objects: {unexpected_objects}")
    if unexpected_prefixes:
        errors.append(f"unexpected root prefixes: {unexpected_prefixes}")
    if missing_objects:
        errors.append(f"missing root objects: {missing_objects}")
    if missing_prefixes:
        errors.append(f"missing root prefixes: {missing_prefixes}")
    lifecycle_rules = list(bucket.lifecycle_rules)
    if lifecycle_rules != EXPECTED_LIFECYCLE_RULES:
        errors.append(
            f"lifecycle policy mismatch: expected {EXPECTED_LIFECYCLE_RULES!r}, got {lifecycle_rules!r}"
        )
    soft_delete_seconds = int(bucket.soft_delete_policy.get("retentionDurationSeconds", 0))
    if soft_delete_seconds != EXPECTED_SOFT_DELETE_SECONDS:
        errors.append(
            "soft-delete policy mismatch: "
            f"expected {EXPECTED_SOFT_DELETE_SECONDS}s, got {soft_delete_seconds}s"
        )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="also query the live GCS bucket root")
    args = parser.parse_args()
    errors = check_static()
    if args.live:
        errors.extend(check_live())
    if errors:
        raise SystemExit("storage layout contract failed:\n- " + "\n- ".join(errors))
    print(f"storage layout contract: PASS (static_files={len(active_files())}, live={args.live})")


if __name__ == "__main__":
    main()
