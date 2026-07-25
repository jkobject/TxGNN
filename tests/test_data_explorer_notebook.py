from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "build_data_explorer_notebook.py"
NOTEBOOK = ROOT / "notebooks" / "07_data_inventory_explorer.ipynb"


def test_data_explorer_is_deterministic_and_bounded() -> None:
    subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=True)
    first = NOTEBOOK.read_bytes()
    subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=True)
    assert NOTEBOOK.read_bytes() == first

    notebook = nbformat.read(NOTEBOOK, as_version=4)
    text = "\n".join(str(cell.source) for cell in notebook.cells)
    assert notebook.metadata["jouvence"]["bounded"] is True
    assert notebook.metadata["jouvence"]["read_only"] is True
    assert "canonical-inferred" in text
    assert "non-canonical" in text
    assert "read_bounded_parquet" in text
    assert "SELECTED_URI" in text
    assert "/Users/jkobject/mnt/gcs" not in text
    assert "jkobject-1549353370965" not in text
    assert all(not cell.get("outputs") for cell in notebook.cells if cell.cell_type == "code")
