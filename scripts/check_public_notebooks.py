#!/usr/bin/env python3
"""Static and execution smoke checks for the public Jouvence notebooks."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"
EXPECTED = [
    "01_data_model_and_use_cases.ipynb",
    "02_nodes_features_and_embeddings.ipynb",
    "03_relations_evidence_and_questions.ipynb",
    "04_lamindb_equivalent_queries.ipynb",
    "05_sampled_pyg_heterodata.ipynb",
    "06_sampled_ml_use_cases.ipynb",
    "07_data_inventory_explorer.ipynb",
]
FORBIDDEN = [
    "/Users/jkobject/mnt/gcs",
    "/mnt/gcs/jouvencekb",
    "jkobject-1549353370965",
    "00_setup_requester_pays",
    "pq.read_table(PUBLIC_KG_ROOT",
    "pd.read_parquet(PUBLIC_KG_ROOT",
]
REQUIRED_PHRASES = [
    "what this means",
    "does not mean",
    "not prove",
    "leakage",
    "partial",
    "bounded",
]


def check_notebook(path: Path) -> dict[str, object]:
    notebook = nbformat.read(path, as_version=4)
    text = "\n".join(str(cell.source) for cell in notebook.cells)
    lower = text.lower()
    failures: list[str] = []
    if notebook.metadata.get("jouvence", {}).get("bounded") is not True:
        failures.append("missing metadata.jouvence.bounded=true")
    for token in FORBIDDEN:
        if token in text:
            failures.append(f"forbidden token: {token}")
    for cell in notebook.cells:
        if cell.cell_type == "code" and (cell.get("execution_count") is not None or cell.get("outputs")):
            failures.append("committed code output/execution count")
            break
    return {
        "path": str(path.relative_to(ROOT)),
        "cells": len(notebook.cells),
        "failures": failures,
        "phrases": {phrase: phrase in lower for phrase in REQUIRED_PHRASES},
    }


def execute_notebook(path: Path, destination: Path) -> dict[str, object]:
    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    output_path = destination / path.name
    nbformat.write(notebook, output_path)
    return {"path": str(path.relative_to(ROOT)), "status": "pass", "executed_copy": str(output_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    actual = sorted(path.name for path in NOTEBOOK_DIR.glob("*.ipynb"))
    suite_failures = [] if actual == EXPECTED else [f"notebook set mismatch: {actual}"]
    checks = [check_notebook(NOTEBOOK_DIR / name) for name in EXPECTED if (NOTEBOOK_DIR / name).exists()]
    suite_text = "\n".join(
        "\n".join(str(cell.source) for cell in nbformat.read(NOTEBOOK_DIR / name, as_version=4).cells).lower()
        for name in EXPECTED
        if (NOTEBOOK_DIR / name).exists()
    )
    for phrase in REQUIRED_PHRASES:
        if phrase not in suite_text:
            suite_failures.append(f"suite missing interpretation phrase: {phrase}")
    for check in checks:
        suite_failures.extend(f"{check['path']}: {failure}" for failure in check["failures"])

    executions: list[dict[str, object]] = []
    if args.execute and not suite_failures:
        destination = Path(tempfile.mkdtemp(prefix="jouvence-public-notebooks-"))
        for name in EXPECTED:
            executions.append(execute_notebook(NOTEBOOK_DIR / name, destination))

    report = {
        "status": "pass" if not suite_failures else "fail",
        "expected_notebooks": EXPECTED,
        "static_checks": checks,
        "executions": executions,
        "failures": suite_failures,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
