from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

from manage_db import data_explorer

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "build_data_explorer_notebook.py"
NOTEBOOK = ROOT / "notebooks" / "07_data_inventory_explorer.ipynb"


def test_data_explorer_is_deterministic_and_bounded(tmp_path: Path) -> None:
    first = tmp_path / "first.ipynb"
    second = tmp_path / "second.ipynb"
    subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(first)], cwd=ROOT, check=True
    )
    subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(second)], cwd=ROOT, check=True
    )
    assert first.read_bytes() == second.read_bytes()
    assert NOTEBOOK.read_bytes() == first.read_bytes()

    notebook = nbformat.read(NOTEBOOK, as_version=4)
    text = "\n".join(str(cell.source) for cell in notebook.cells)
    assert notebook.metadata["jouvence"]["bounded"] is True
    assert notebook.metadata["jouvence"]["read_only"] is True
    assert "canonical-inferred" in text
    assert "non-canonical" in text
    assert "read_bounded_parquet" in text
    assert "list_parquet_uris" in text
    assert "fs.glob(" not in text
    assert "SELECTED_URI" in text
    assert "/Users/jkobject/mnt/gcs" not in text
    assert "jkobject-1549353370965" not in text
    assert all(not cell.get("outputs") for cell in notebook.cells if cell.cell_type == "code")


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("JOUVENCE_DATA_MODE", "invalid", "JOUVENCE_DATA_MODE must be fixture or live"),
        ("JOUVENCE_EXPLORER_SAMPLE_ROWS", "101", "must be between 1 and 100"),
        ("JOUVENCE_EXPLORER_MAX_FILES", "2001", "must be between 1 and 2000"),
    ],
)
def test_optimized_python_cannot_remove_safety_bounds(
    variable: str, value: str, message: str
) -> None:
    environment = os.environ.copy()
    environment.update({"PYTHONOPTIMIZE": "1", variable: value})
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_data_explorer_notebook.py"), "--execute"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert message in result.stdout + result.stderr


def test_every_live_gcs_root_requires_billing_project(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "JOUVENCE_DATA_MODE": "live",
            "JOUVENCE_CANONICAL_ROOT": str(tmp_path),
            "JOUVENCE_STAGING_ROOT": "gs://example-bucket/staging",
        }
    )
    environment.pop("JOUVENCE_BILLING_PROJECT", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_data_explorer_notebook.py"), "--execute"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "Every configured GCS root requires JOUVENCE_BILLING_PROJECT" in (
        result.stdout + result.stderr
    )


def test_local_listing_is_early_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(5):
        path = tmp_path / f"part-{index}.parquet"
        path.write_bytes(b"fixture")

    listing = data_explorer.list_parquet_uris(tmp_path, limit=2)

    assert len(listing.uris) == 2
    assert listing.truncated is True
    assert listing.uris[0].endswith("part-0.parquet")

    def failing_walk(_root, *, onerror):
        onerror(PermissionError("local denied"))
        return iter(())

    with monkeypatch.context() as scoped:
        scoped.setattr(data_explorer.os, "walk", failing_walk)
        with pytest.raises(PermissionError, match="local denied"):
            data_explorer.list_parquet_uris(tmp_path, limit=2)


def test_gcs_listing_uses_server_side_cap_and_propagates_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class Blob:
        def __init__(self, name: str):
            self.name = name

    class FakeClient:
        def bucket(self, name: str, *, user_project: str):
            calls["bucket"] = (name, user_project)
            return object()

        def list_blobs(self, _bucket, **kwargs):
            calls["list"] = kwargs
            return [Blob("kg/v2/edges/a.parquet"), Blob("kg/v2/edges/b.parquet"), Blob("kg/v2/edges/c.parquet")]

    monkeypatch.setattr(data_explorer, "Client", FakeClient)
    listing = data_explorer.list_parquet_uris(
        "gs://jouvencekb/kg/v2/edges", limit=2, billing_project="caller-project"
    )

    assert listing.uris == (
        "gs://jouvencekb/kg/v2/edges/a.parquet",
        "gs://jouvencekb/kg/v2/edges/b.parquet",
    )
    assert listing.truncated is True
    assert calls["bucket"] == ("jouvencekb", "caller-project")
    assert calls["list"] == {
        "prefix": "kg/v2/edges/",
        "match_glob": "kg/v2/edges/**/*.parquet",
        "max_results": 3,
        "page_size": 3,
    }

    class FailingClient(FakeClient):
        def list_blobs(self, _bucket, **kwargs):
            raise PermissionError("denied")

    monkeypatch.setattr(data_explorer, "Client", FailingClient)
    with pytest.raises(PermissionError, match="denied"):
        data_explorer.list_parquet_uris(
            "gs://jouvencekb/kg/v2/edges", limit=2, billing_project="caller-project"
        )
