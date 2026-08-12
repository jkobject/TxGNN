from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
import manage_db.rebuild_molecule_provenance_gaps as rebuild

from manage_db.rebuild_molecule_provenance_gaps import (
    CANONICAL_GENERATIONS,
    SOURCE_ASSERTIONS,
    acquire_source,
    build_candidates,
    compare_candidate,
    validate_launcher_receipt,
    verify_replay,
    write_replay,
)


def fixture_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "x_id": "DB00001",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "16",
                "y_type": "effect/phenotype",
                "y_source": "HPO",
                "relation": "drug_effect",
                "display_relation": "side effect",
            },
            {
                "x_id": "DB00001",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "16",
                "y_type": "effect/phenotype",
                "y_source": "HPO",
                "relation": "drug_effect",
                "display_relation": "side effect",
            },
            {
                "x_id": "DB00001",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "565",
                "y_type": "disease",
                "y_source": "MONDO",
                "relation": "contraindication",
                "display_relation": "contraindication",
            },
            {
                "x_id": "C000188",
                "x_type": "exposure",
                "x_source": "CTD",
                "y_id": "D006540",
                "y_type": "exposure",
                "y_source": "CTD",
                "relation": "exposure_exposure",
                "display_relation": "parent of",
            },
            {
                "x_id": "DB00001",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "DB00006",
                "y_type": "drug",
                "y_source": "DrugBank",
                "relation": "drug_drug",
                "display_relation": "synergizes with",
            },
            {
                "x_id": "DB00006",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "DB00001",
                "y_type": "drug",
                "y_source": "DrugBank",
                "relation": "drug_drug",
                "display_relation": "synergizes with",
            },
            {
                "x_id": "DB00002",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "536",
                "y_type": "disease",
                "y_source": "MONDO",
                "relation": "indication",
                "display_relation": "indication",
            },
            {
                "x_id": "C000188",
                "x_type": "exposure",
                "x_source": "CTD",
                "y_id": "2334",
                "y_type": "disease",
                "y_source": "MONDO",
                "relation": "exposure_disease",
                "display_relation": "linked to",
            },
            {
                "x_id": "DB00001",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "DB00002",
                "y_type": "drug",
                "y_source": "DrugBank",
                "relation": "drug_drug",
                "display_relation": "unknown predicate",
            },
        ]
    )


def test_source_contract_pins_txgnn_release_and_all_five_assertion_lanes() -> None:
    assert set(SOURCE_ASSERTIONS) == {
        "molecule_associated_phenotype",
        "molecule_contraindicates_disease",
        "molecule_parent_of_molecule",
        "molecule_synergizes_molecule",
        "molecule_treats_disease",
    }
    assert all(spec["txgnn_file_id"] == 7144484 for spec in SOURCE_ASSERTIONS.values())
    assert all(spec["txgnn_file_md5"] == "aac8191d4fbc5bf09cdf8c3c78b4e75f" for spec in SOURCE_ASSERTIONS.values())
    assert set(CANONICAL_GENERATIONS) == set(SOURCE_ASSERTIONS)


def test_fixture_replay_preserves_predicate_orientation_and_evidence_multiplicity() -> None:
    result = build_candidates(fixture_rows())

    assert result.rejections["reason"].tolist() == ["unsupported_assertion"]
    assert len(result.edges["molecule_associated_phenotype"]) == 1
    assert len(result.evidence["molecule_associated_phenotype"]) == 2
    assert result.edges["molecule_associated_phenotype"].iloc[0]["y_id"] == "HP:0000016"
    assert result.edges["molecule_contraindicates_disease"].iloc[0]["y_id"] == "MONDO:0000565"
    assert result.edges["molecule_parent_of_molecule"].iloc[0][["x_id", "y_id"]].tolist() == [
        "CTD:C000188",
        "CTD:D006540",
    ]
    assert set(map(tuple, result.edges["molecule_synergizes_molecule"][["x_id", "y_id"]].values)) == {
        ("DB00001", "DB00006"),
        ("DB00006", "DB00001"),
    }
    assert set(result.edges["molecule_treats_disease"]["display_relation"]) == {"indication", "linked to"}
    for relation, evidence in result.evidence.items():
        assert set(evidence["source_dataset"]) == {SOURCE_ASSERTIONS[relation]["constituent_source"]}
        assert set(evidence["source_predicate"]) <= set(SOURCE_ASSERTIONS[relation]["source_predicates"])


def test_parity_report_accounts_for_key_sets_endpoints_duplicates_and_later_support() -> None:
    candidate = pd.DataFrame(
        [
            {"relation": "molecule_treats_disease", "x_id": "DB1", "y_id": "D1"},
            {"relation": "molecule_treats_disease", "x_id": "DB2", "y_id": "D2"},
            {"relation": "molecule_treats_disease", "x_id": "DB2", "y_id": "D2"},
        ]
    )
    canonical = pd.DataFrame(
        [
            {"relation": "molecule_treats_disease", "x_id": "DB1", "y_id": "D1"},
            {"relation": "molecule_treats_disease", "x_id": "DB3", "y_id": "D3"},
        ]
    )
    support = pd.DataFrame(
        [
            {"relation": "molecule_treats_disease", "x_id": "DB1", "y_id": "D1"},
            {"relation": "molecule_treats_disease", "x_id": "DB9", "y_id": "D9"},
        ]
    )

    report = compare_candidate(
        "molecule_treats_disease",
        candidate,
        canonical,
        x_endpoints={"DB1", "DB2"},
        y_endpoints={"D1"},
        later_support=support,
    )

    assert report == {
        "relation": "molecule_treats_disease",
        "canonical_generation": CANONICAL_GENERATIONS["molecule_treats_disease"],
        "candidate_rows": 3,
        "candidate_distinct_keys": 2,
        "canonical_rows": 2,
        "canonical_distinct_keys": 2,
        "intersection": 1,
        "candidate_only": 1,
        "canonical_only": 1,
        "candidate_duplicate_keys": 1,
        "canonical_duplicate_keys": 0,
        "x_endpoint_anti_join": 0,
        "y_endpoint_anti_join": 1,
        "canonical_supported_by_later_evidence": 1,
        "canonical_unsupported_by_later_evidence": 1,
        "later_evidence_without_canonical_edge": 1,
    }


def test_chunked_replay_keeps_globally_unique_source_record_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "kg.csv"
    fixture_rows().iloc[:2].to_csv(source, index=False)

    allowed_root = tmp_path / "artifacts" / "staged" / "t_86299745"
    output = allowed_root / "candidate"
    write_replay(
        source,
        output,
        fixture=True,
        fixture_allowed_root=allowed_root,
        canonical_dir=None,
        chunksize=1,
    )

    evidence = pd.read_parquet(output / "evidence" / "molecule_associated_phenotype.parquet")
    assert evidence["source_record_id"].tolist() == ["TxGNN:kg.csv:0", "TxGNN:kg.csv:1"]


def test_acquisition_is_create_only_and_checksum_gated(tmp_path) -> None:
    source = tmp_path / "remote.csv"
    source.write_bytes(b"x,y\n1,2\n")
    destination = tmp_path / "raw" / "kg.csv"

    identity = acquire_source(
        source.as_uri(),
        destination,
        expected_size=8,
        expected_md5="344fd2323dd33d5c058b7cf27de029e8",
    )
    assert identity == {
        "path": str(destination),
        "size": 8,
        "md5": "344fd2323dd33d5c058b7cf27de029e8",
        "url": source.as_uri(),
    }
    assert destination.read_bytes() == source.read_bytes()

    try:
        acquire_source(source.as_uri(), destination, expected_size=8, expected_md5=identity["md5"])
    except FileExistsError:
        pass
    else:
        raise AssertionError("acquisition must not overwrite an existing raw object")


def test_endpoint_type_mismatch_is_quarantined_instead_of_relabeled() -> None:
    rows = pd.DataFrame(
        [
            {
                "x_id": "DB00001",
                "x_type": "drug",
                "x_source": "DrugBank",
                "y_id": "16",
                "y_type": "effect/phenotype",
                "y_source": "HPO",
                "relation": "contraindication",
                "display_relation": "contraindication",
            },
            {
                "x_id": "C000188",
                "x_type": "exposure",
                "x_source": "CTD",
                "y_id": "536",
                "y_type": "disease",
                "y_source": "MONDO",
                "relation": "indication",
                "display_relation": "indication",
            },
        ]
    )

    result = build_candidates(rows)
    assert all(frame.empty for frame in result.edges.values())
    assert result.rejections["reason"].tolist() == [
        "endpoint_type_mismatch:expected drug->disease, observed drug->effect/phenotype",
        "endpoint_type_mismatch:expected drug->disease, observed exposure->disease",
    ]


def test_endpoint_namespace_mismatch_is_quarantined() -> None:
    row = fixture_rows().iloc[[2]].copy()
    row.loc[:, "x_source"] = "NOT_DRUGBANK"
    result = build_candidates(row)
    assert result.edges["molecule_contraindicates_disease"].empty
    assert result.rejections["reason"].tolist() == [
        "endpoint_namespace_mismatch:expected DrugBank->MONDO|MONDO_grouped, observed NOT_DRUGBANK->MONDO"
    ]


def test_full_replay_refuses_non_worker_and_non_staging_output(tmp_path, monkeypatch) -> None:
    source = tmp_path / "kg.csv"
    fixture_rows().to_csv(source, index=False)
    canonical = tmp_path / "canonical"
    canonical.mkdir()

    monkeypatch.setattr(rebuild.socket, "gethostname", lambda: "laptop")
    with pytest.raises(RuntimeError, match="txgnn-worker"):
        write_replay(source, tmp_path / "candidate", fixture=False, canonical_dir=canonical, chunksize=2)

    monkeypatch.setattr(rebuild.socket, "gethostname", lambda: "txgnn-worker")
    with pytest.raises(ValueError, match="artifacts/staged/t_86299745"):
        write_replay(source, tmp_path / "candidate", fixture=False, canonical_dir=canonical, chunksize=2)

    monkeypatch.chdir(tmp_path)
    escape = tmp_path / "artifacts" / "staged" / "t_86299745" / ".." / "escaped"
    with pytest.raises(ValueError, match="artifacts/staged/t_86299745"):
        write_replay(source, escape, fixture=False, canonical_dir=canonical, chunksize=2)


def test_fixture_replay_requires_explicit_safe_root_and_rejects_canonical_shaped_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "kg.csv"
    fixture_rows().to_csv(source, index=False)

    with pytest.raises(ValueError, match="fixture_allowed_root"):
        write_replay(source, tmp_path / "candidate", fixture=True, canonical_dir=None, chunksize=2)
    with pytest.raises(ValueError, match="forbidden output path"):
        write_replay(
            source,
            tmp_path / "main" / "edges" / "unsafe",
            fixture=True,
            fixture_allowed_root=tmp_path,
            canonical_dir=None,
            chunksize=2,
        )

    with pytest.raises(ValueError, match="not an approved task/pytest root"):
        write_replay(
            source,
            Path("/tmp/jouvence-review-unapproved/candidate"),
            fixture=True,
            fixture_allowed_root=Path("/"),
            canonical_dir=None,
            chunksize=2,
        )


def test_full_cli_preflight_runs_before_acquisition(tmp_path, monkeypatch) -> None:
    called = False

    def forbidden_acquisition(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("acquisition must not run before admission")

    monkeypatch.setattr(rebuild, "acquire_source", forbidden_acquisition)
    monkeypatch.setattr(rebuild.socket, "gethostname", lambda: "laptop")
    with pytest.raises(RuntimeError, match="txgnn-worker"):
        rebuild.main(
            [
                "--acquire-to",
                str(tmp_path / "raw" / "kg.csv"),
                "--output-dir",
                str(tmp_path / "candidate"),
            ]
        )
    assert called is False


def test_launcher_receipt_requires_fresh_bounded_task_lease_and_exclusive_lock(tmp_path, monkeypatch) -> None:
    now = datetime.now(UTC)
    lease_until = now + timedelta(hours=2)
    absolute_deadline = now + timedelta(hours=3)
    heartbeat = tmp_path / "runtime" / "heartbeat.json"
    lock = tmp_path / "runtime" / "writer.lock"
    receipt = tmp_path / "launcher-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "task_id": "t_86299745",
                "owner": "tester",
                "project": "jouvence",
                "purpose": "molecule-provenance-gap-full-replay",
                "hostname": "txgnn-worker",
                "readback_at": now.isoformat(),
                "lease_until": lease_until.isoformat(),
                "absolute_deadline": absolute_deadline.isoformat(),
                "max_runtime_seconds": 3600,
                "payload_heartbeat_path": str(heartbeat),
                "resource_lock_path": str(lock),
                "lease_id": "lease-12345678",
                "gcp_project_id": "test-project",
                "zone": "test-zone",
                "instance": "txgnn-worker",
                "instance_id": "1234",
                "absolute_stop_policy": "stop-policy",
            }
        )
    )
    monkeypatch.setattr(rebuild, "_live_instance_readback", lambda *args: {
        "id": "1234",
        "status": "RUNNING",
        "labels": {
            "owner": "tester",
            "project": "jouvence",
            "purpose": "molecule-provenance-gap-full-replay",
            "task": "t-86299745",
            "lease-id": "lease-12345678",
            "lease-until": str(int(lease_until.timestamp())),
            "absolute-until": str(int(absolute_deadline.timestamp())),
        },
        "resourcePolicies": ["projects/test/regions/test/resourcePolicies/stop-policy"],
    })
    admission = validate_launcher_receipt(receipt)
    lock.parent.mkdir(parents=True)
    lock.write_text("existing writer\n")
    with pytest.raises(FileExistsError):
        with rebuild._exclusive_run(admission):
            pass

    receipt_payload = json.loads(receipt.read_text())
    receipt_payload["readback_at"] = (now - timedelta(minutes=10)).isoformat()
    receipt.write_text(json.dumps(receipt_payload))
    with pytest.raises(ValueError, match="not fresh"):
        validate_launcher_receipt(receipt)


def test_forged_launcher_receipt_fails_without_matching_live_gce_lease(tmp_path, monkeypatch) -> None:
    now = datetime.now(UTC)
    receipt = tmp_path / "forged.json"
    receipt.write_text(json.dumps({
        "task_id": "t_86299745", "owner": "attacker", "project": "jouvence",
        "purpose": "molecule-provenance-gap-full-replay", "hostname": "txgnn-worker",
        "readback_at": now.isoformat(), "lease_until": (now + timedelta(hours=2)).isoformat(),
        "absolute_deadline": (now + timedelta(hours=3)).isoformat(), "max_runtime_seconds": 3600,
        "payload_heartbeat_path": str(tmp_path / "heartbeat"),
        "resource_lock_path": str(tmp_path / "lock"), "lease_id": "forged-lease",
        "gcp_project_id": "test-project", "zone": "test-zone", "instance": "txgnn-worker",
        "instance_id": "1234", "absolute_stop_policy": "forged-policy",
    }))
    monkeypatch.setattr(rebuild, "_live_instance_readback", lambda *args: {
        "id": "1234", "status": "TERMINATED", "labels": {}, "resourcePolicies": []
    })
    with pytest.raises(ValueError, match="live worker identity/state"):
        validate_launcher_receipt(receipt)


def test_payload_heartbeat_fails_closed_when_live_lease_renewal_disappears(tmp_path, monkeypatch) -> None:
    now = datetime.now(UTC)
    admission = rebuild.RunAdmission(
        tmp_path / "receipt.json", tmp_path / "heartbeat.json", tmp_path / "lock",
        now + timedelta(hours=2), 3600, "tester", "lease-12345678", "test-project",
        "test-zone", "txgnn-worker", "1234", now + timedelta(hours=3), "stop-policy",
    )
    monkeypatch.setattr(rebuild, "_live_instance_readback", lambda *args: {
        "id": "1234", "status": "RUNNING",
        "labels": {
            "owner": "tester", "project": "jouvence",
            "purpose": "molecule-provenance-gap-full-replay", "task": "t-86299745",
            "lease-id": "lease-12345678", "lease-until": str(int((now + timedelta(minutes=1)).timestamp())),
            "absolute-until": str(int((now + timedelta(hours=3)).timestamp())),
        },
        "resourcePolicies": ["projects/test/regions/test/resourcePolicies/stop-policy"],
    })
    with pytest.raises(ValueError, match="not renewed"):
        rebuild._payload_heartbeat(admission, started=__import__("time").monotonic(), source_rows=1)
    assert not admission.heartbeat_path.exists()


def test_parity_requires_a_snapshot_manifest_with_frozen_edge_generations(tmp_path) -> None:
    source = tmp_path / "kg.csv"
    fixture_rows().to_csv(source, index=False)
    canonical = tmp_path / "canonical"
    canonical.mkdir()

    with pytest.raises(ValueError, match="canonical snapshot manifest"):
        write_replay(
            source,
            tmp_path / "candidate",
            fixture=True,
            fixture_allowed_root=tmp_path,
            canonical_dir=canonical,
            canonical_manifest=None,
            chunksize=2,
        )


def test_snapshot_manifest_must_bind_actual_file_bytes(tmp_path) -> None:
    source = tmp_path / "kg.csv"
    fixture_rows().to_csv(source, index=False)
    canonical = tmp_path / "canonical"
    edge_dir = canonical / "edges"
    edge_dir.mkdir(parents=True)
    for relation in CANONICAL_GENERATIONS:
        fixture_rows().iloc[:0].to_parquet(edge_dir / f"{relation}.parquet", index=False)
    manifest = tmp_path / "snapshot.json"
    manifest.write_text(
        __import__("json").dumps(
            {
                "edge_generations": CANONICAL_GENERATIONS,
                "objects": {
                    f"edges/{relation}.parquet": {"size": 1, "sha256": "0" * 64}
                    for relation in CANONICAL_GENERATIONS
                },
            }
        )
    )

    with pytest.raises(ValueError, match="snapshot object identity mismatch"):
        write_replay(
            source,
            tmp_path / "candidate",
            fixture=True,
            fixture_allowed_root=tmp_path,
            canonical_dir=canonical,
            canonical_manifest=manifest,
            chunksize=2,
        )


def test_manifest_binds_all_outputs_and_verifier_detects_tampering(tmp_path) -> None:
    source = tmp_path / "kg.csv"
    fixture_rows().to_csv(source, index=False)
    output = tmp_path / "candidate"
    write_replay(
        source,
        output,
        fixture=True,
        fixture_allowed_root=tmp_path,
        canonical_dir=None,
        chunksize=2,
    )

    manifest = verify_replay(output)
    assert len(manifest["objects"]) == 11
    assert "mapping_quarantine.parquet" in manifest["objects"]
    relation = manifest["relations"]["molecule_associated_phenotype"]
    assert relation["source_selected_rows"] == 2
    assert relation["accepted_rows"] == 2
    assert relation["source_duplicate_assertions"] == 1
    assert relation["distinct_edge_keys"] == 1
    assert relation["evidence_rows"] == 2
    assert relation["distinct_evidence_ids"] == 2
    assert relation["rejected_rows"] == 0

    target = output / "evidence" / "molecule_associated_phenotype.parquet"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="replay object identity mismatch"):
        verify_replay(output)
