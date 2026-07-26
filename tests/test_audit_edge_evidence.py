from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from manage_db.audit_edge_evidence import audit_edge_evidence, main
from manage_db.kg_evidence import write_evidence
from manage_db.kg_storage import open_kg_root, write_edges


def _edge_frame(relation: str = "disease_involves_pathway") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "x_id": "R-HSA-1",
                "x_type": "pathway",
                "y_id": "EFO:1",
                "y_type": "disease",
                "relation": relation,
                "display_relation": "involves pathway",
                "source": "test",
                "credibility": 3,
            }
        ]
    )


def _evidence_frame(relation: str = "disease_involves_pathway") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "relation": relation,
                "x_id": "R-HSA-1",
                "x_type": "pathway",
                "y_id": "EFO:1",
                "y_type": "disease",
                "evidence_type": "database_record",
                "source": "test",
                "source_dataset": "unit",
                "source_record_id": "unit:1",
            }
        ]
    )


def test_audit_edge_evidence_passes_when_requested_edge_and_evidence_exist(tmp_path: Path) -> None:
    root = open_kg_root(str(tmp_path / "kg"))
    write_edges(root, "disease_involves_pathway", _edge_frame())
    write_evidence(root, "disease_involves_pathway", _evidence_frame())

    audit = audit_edge_evidence(tmp_path / "kg", relations=["disease_involves_pathway"])

    assert audit.ok
    report = audit.relation_reports["disease_involves_pathway"]
    assert report.edge_object_exists
    assert report.evidence_object_exists
    assert report.edge_rows == 1
    assert report.evidence_rows == 1


def test_cli_fail_on_missing_fails_closed_for_missing_root(tmp_path: Path, capsys) -> None:
    missing_root = tmp_path / "missing-kg"

    assert (
        main(
            [
                str(missing_root),
                "--relations",
                "disease_manifests_in_tissue",
                "--json",
                "--fail-on-missing",
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["root_exists"] is False
    assert payload["relation_reports"] == {}
    assert not missing_root.exists()


def test_cli_fail_on_missing_fails_closed_for_requested_relation_without_objects(
    tmp_path: Path,
    capsys,
) -> None:
    open_kg_root(str(tmp_path / "kg"))

    assert (
        main(
            [
                str(tmp_path / "kg"),
                "--relations",
                "disease_manifests_in_tissue",
                "--json",
                "--fail-on-missing",
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    report = payload["relation_reports"]["disease_manifests_in_tissue"]
    assert payload["ok"] is False
    assert report["ok"] is False
    assert report["edge_rows"] == 0
    assert report["evidence_rows"] == 0
    assert report["edge_object_exists"] is False
    assert report["evidence_object_exists"] is False


def test_cli_fail_on_missing_fails_closed_when_only_edge_object_exists(tmp_path: Path, capsys) -> None:
    root = open_kg_root(str(tmp_path / "kg"))
    write_edges(root, "disease_involves_pathway", _edge_frame())

    assert (
        main(
            [
                str(tmp_path / "kg"),
                "--relations",
                "disease_involves_pathway",
                "--json",
                "--fail-on-missing",
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    report = payload["relation_reports"]["disease_involves_pathway"]
    assert report["ok"] is False
    assert report["edge_rows"] == 1
    assert report["evidence_rows"] == 0
    assert report["edge_object_exists"] is True
    assert report["evidence_object_exists"] is False
    assert report["edges_without_evidence"] == 1
