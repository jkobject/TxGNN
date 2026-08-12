"""Rebuild the five legacy molecule provenance-gap lineages from TxGNN kg.csv.

The builder is deliberately task-scoped: it only writes beneath ``--output-dir`` and
never opens the canonical store for mutation. Full replay belongs on txgnn-worker;
small fixture replay is supported locally.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import socket
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

TXGNN_DATASET = {
    "doi": "10.7910/DVN/CNQV69",
    "title": "DeepPurpose",
    "version": "6.0",
    "release_time": "2023-06-07T04:55:16Z",
    "license": "CC0-1.0",
    "txgnn_code_commit": "f378c5132e287f2e02605c47d0c8df27750b413a",
    "txgnn_code_blob": "7be3ad91183e3740593734224cb951d265dae74b",
    "file_id": 7144484,
    "filename": "kg.csv",
    "size": 981_751_236,
    "md5": "aac8191d4fbc5bf09cdf8c3c78b4e75f",
    "url": "https://dataverse.harvard.edu/api/access/datafile/7144484",
}

CANONICAL_GENERATIONS = {
    "molecule_associated_phenotype": "1785155484199958",
    "molecule_contraindicates_disease": "1785155484349742",
    "molecule_parent_of_molecule": "1785155484679611",
    "molecule_synergizes_molecule": "1785155484817964",
    "molecule_treats_disease": "1785155486922602",
}

SOURCE_ASSERTIONS = {
    "molecule_associated_phenotype": {
        "legacy_relations": ["drug_effect"],
        "source_predicates": ["side effect"],
        "constituent_source": "SIDER",
        "source_release": "PrimeKG/TxGNN frozen input published 2023-06-07; upstream SIDER release not encoded",
        "orientation": "molecule_to_phenotype",
        "symmetric": False,
    },
    "molecule_contraindicates_disease": {
        "legacy_relations": ["contraindication"],
        "source_predicates": ["contraindication"],
        "constituent_source": "DrugCentral",
        "source_release": "PrimeKG/TxGNN frozen input published 2023-06-07; upstream DrugCentral release not encoded",
        "orientation": "molecule_to_disease",
        "symmetric": False,
    },
    "molecule_parent_of_molecule": {
        "legacy_relations": ["exposure_exposure"],
        "source_predicates": ["parent of"],
        "constituent_source": "Comparative Toxicogenomics Database",
        "source_release": "PrimeKG/TxGNN frozen input published 2023-06-07; upstream CTD release not encoded",
        "orientation": "parent_to_child",
        "symmetric": False,
    },
    "molecule_synergizes_molecule": {
        "legacy_relations": ["drug_drug"],
        "source_predicates": ["synergizes with"],
        "constituent_source": "DrugBank drug-interaction records",
        "source_release": "PrimeKG/TxGNN frozen input published 2023-06-07; upstream DrugBank release not redistributable",
        "orientation": "source_order_preserved",
        "symmetric": True,
        "semantic_caveat": "TxGNN labels DrugBank drug interactions as 'synergizes with'; no combination-screen score or threshold exists.",
    },
    "molecule_treats_disease": {
        "legacy_relations": ["indication", "off-label use", "exposure_disease"],
        "source_predicates": ["indication", "off-label use", "linked to"],
        "constituent_source": "DrugCentral indications plus CTD exposure-disease links",
        "source_release": "PrimeKG/TxGNN frozen input published 2023-06-07; constituent upstream releases not encoded",
        "orientation": "molecule_to_disease",
        "symmetric": False,
    },
}
for _spec in SOURCE_ASSERTIONS.values():
    _spec["txgnn_file_id"] = TXGNN_DATASET["file_id"]
    _spec["txgnn_file_md5"] = TXGNN_DATASET["md5"]

LEGACY_TO_CANONICAL = {
    legacy: relation
    for relation, spec in SOURCE_ASSERTIONS.items()
    for legacy in spec["legacy_relations"]
}

EDGE_COLUMNS = [
    "x_id",
    "x_type",
    "y_id",
    "y_type",
    "relation",
    "display_relation",
    "source",
    "credibility",
]
EVIDENCE_COLUMNS = [
    "edge_key",
    "relation",
    "x_id",
    "x_type",
    "y_id",
    "y_type",
    "evidence_type",
    "source",
    "source_dataset",
    "source_release",
    "source_record_id",
    "source_predicate",
    "original_x_id",
    "original_x_type",
    "original_y_id",
    "original_y_type",
    "mapping_method",
    "mapping_confidence",
    "pair_orientation",
    "symmetric",
    "license",
]


@dataclass
class BuildResult:
    edges: dict[str, pd.DataFrame]
    evidence: dict[str, pd.DataFrame]
    rejections: pd.DataFrame


@dataclass(frozen=True)
class RunAdmission:
    receipt_path: Path
    heartbeat_path: Path
    lock_path: Path
    lease_until: datetime
    max_runtime_seconds: int


def file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_identity(path: Path) -> dict[str, object]:
    return {"size": path.stat().st_size, "sha256": file_sha256(path)}


def _reject_dangerous_path(path: Path, *, label: str) -> Path:
    raw = str(path)
    resolved = path.resolve(strict=False)
    lowered_parts = {part.lower() for part in resolved.parts}
    if (
        raw.startswith("gs://")
        or raw.startswith("/Users/jkobject/mnt/gcs")
        or "main" in lowered_parts
        or "canonical" in lowered_parts
    ):
        raise ValueError(f"forbidden {label} path: {path}")
    return resolved


def _validate_output_path(output_dir: Path, *, fixture: bool, fixture_allowed_root: Path | None) -> None:
    resolved_output = _reject_dangerous_path(output_dir, label="output")
    if fixture:
        if fixture_allowed_root is None:
            raise ValueError("fixture_allowed_root is required for fixture replay")
        allowed_root = _reject_dangerous_path(fixture_allowed_root, label="fixture root")
        if resolved_output == allowed_root or not resolved_output.is_relative_to(allowed_root):
            raise ValueError("fixture output must be a child of fixture_allowed_root")
        return
    allowed_root = (Path.cwd() / "artifacts" / "staged" / "t_86299745").resolve(strict=False)
    if not resolved_output.is_relative_to(allowed_root) or resolved_output == allowed_root:
        raise ValueError("full replay output must be under artifacts/staged/t_86299745/")


def _parse_timestamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"launcher receipt has invalid {field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"launcher receipt {field} must be timezone-aware")
    return parsed.astimezone(UTC)


def validate_launcher_receipt(path: Path) -> RunAdmission:
    """Validate a fresh readback from the project-approved lifecycle launcher."""
    if not path.is_file():
        raise ValueError("full replay requires a launcher receipt")
    receipt = json.loads(path.read_text())
    expected = {
        "task_id": "t_86299745",
        "owner": os.environ.get("USER", "jkobject"),
        "project": "jouvence",
        "purpose": "molecule-provenance-gap-full-replay",
        "hostname": "txgnn-worker",
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ValueError(f"launcher receipt {field} must equal {value!r}")
    now = datetime.now(UTC)
    readback_at = _parse_timestamp(receipt.get("readback_at"), "readback_at")
    lease_until = _parse_timestamp(receipt.get("lease_until"), "lease_until")
    if abs((now - readback_at).total_seconds()) > 300:
        raise ValueError("launcher receipt readback is not fresh")
    max_runtime = receipt.get("max_runtime_seconds")
    if not isinstance(max_runtime, int) or not 60 <= max_runtime <= 86_400:
        raise ValueError("launcher receipt max_runtime_seconds must be an integer in [60, 86400]")
    if lease_until.timestamp() < time.time() + max_runtime + 600:
        raise ValueError("launcher lease does not cover max runtime plus cleanup margin")
    heartbeat = Path(str(receipt.get("payload_heartbeat_path", "")))
    lock = Path(str(receipt.get("resource_lock_path", "")))
    if not heartbeat.is_absolute() or not lock.is_absolute():
        raise ValueError("launcher receipt heartbeat and lock paths must be absolute")
    for candidate in (heartbeat, lock):
        _reject_dangerous_path(candidate, label="runtime")
    return RunAdmission(path, heartbeat, lock, lease_until, max_runtime)


@contextlib.contextmanager
def _exclusive_run(admission: RunAdmission | None) -> Iterator[None]:
    if admission is None:
        yield
        return
    admission.lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(admission.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        admission.lock_path.unlink(missing_ok=True)


def _payload_heartbeat(admission: RunAdmission | None, *, started: float, source_rows: int) -> None:
    if admission is None:
        return
    elapsed = time.monotonic() - started
    if elapsed > admission.max_runtime_seconds or datetime.now(UTC) >= admission.lease_until:
        raise TimeoutError("full replay exceeded its admitted runtime/lease")
    admission.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    partial = admission.heartbeat_path.with_suffix(".partial")
    partial.write_text(
        json.dumps(
            {
                "task_id": "t_86299745",
                "payload_pid": os.getpid(),
                "source_rows": source_rows,
                "elapsed_seconds": round(elapsed, 3),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            sort_keys=True,
        )
        + "\n"
    )
    os.replace(partial, admission.heartbeat_path)


def acquire_source(
    url: str,
    destination: Path,
    *,
    expected_size: int = TXGNN_DATASET["size"],
    expected_md5: str = TXGNN_DATASET["md5"],
    admission: RunAdmission | None = None,
    started: float | None = None,
) -> dict[str, object]:
    """Create-only streamed acquisition with validation before atomic adoption."""
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.partial-{os.getpid()}-{uuid.uuid4().hex}")
    digest = hashlib.md5(usedforsecurity=False)
    size = 0
    try:
        with urllib.request.urlopen(url) as response, partial.open("xb") as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                _payload_heartbeat(
                    admission,
                    started=started if started is not None else time.monotonic(),
                    source_rows=size,
                )
            handle.flush()
            os.fsync(handle.fileno())
        observed_md5 = digest.hexdigest()
        if size != expected_size or observed_md5 != expected_md5:
            raise ValueError(
                f"download identity mismatch: expected size={expected_size} md5={expected_md5}, "
                f"observed size={size} md5={observed_md5}"
            )
        # A hard-link adoption is atomic and create-only: unlike os.replace(), it
        # cannot overwrite a destination created by a concurrent process.
        os.link(partial, destination)
        partial.unlink()
        return {"path": str(destination), "size": size, "md5": observed_md5, "url": url}
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def verify_source(path: Path, *, allow_fixture: bool) -> dict[str, object]:
    size = path.stat().st_size
    md5 = file_md5(path)
    if not allow_fixture and (size != TXGNN_DATASET["size"] or md5 != TXGNN_DATASET["md5"]):
        raise ValueError(
            "TxGNN kg.csv identity mismatch: "
            f"expected size={TXGNN_DATASET['size']} md5={TXGNN_DATASET['md5']}, "
            f"observed size={size} md5={md5}"
        )
    return {"path": str(path), "size": size, "md5": md5, "fixture": allow_fixture}


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_id(raw_id: object, node_type: object, source: object) -> str:
    value = _clean(raw_id)
    kind = _clean(node_type)
    origin = _clean(source)
    if not value:
        raise ValueError("missing endpoint id")
    if kind == "drug":
        if not value.startswith("DB"):
            raise ValueError("drug endpoint is not a DrugBank ID")
        return value
    if kind == "exposure":
        return value if value.startswith("CTD:") else f"CTD:{value}"
    if kind == "effect/phenotype":
        if value.startswith("HP:"):
            return value
        return f"HP:{int(value):07d}"
    if kind == "disease":
        if value.startswith("MONDO:"):
            return value
        primary = value.split("_")[0] if origin == "MONDO_grouped" else value
        return f"MONDO:{int(primary):07d}"
    raise ValueError(f"unsupported endpoint type {kind!r}")


def _expected_types(relation: str) -> tuple[str, str]:
    if relation == "molecule_associated_phenotype":
        return "molecule", "phenotype"
    if relation in {"molecule_contraindicates_disease", "molecule_treats_disease"}:
        return "molecule", "disease"
    return "molecule", "molecule"


def _expected_legacy_types(relation: str, predicate: str) -> tuple[str, str]:
    if relation == "molecule_associated_phenotype":
        return "drug", "effect/phenotype"
    if relation == "molecule_parent_of_molecule":
        return "exposure", "exposure"
    if relation == "molecule_synergizes_molecule":
        return "drug", "drug"
    if relation == "molecule_treats_disease" and predicate == "linked to":
        return "exposure", "disease"
    return "drug", "disease"


def _expected_legacy_sources(relation: str, predicate: str) -> tuple[set[str], set[str]]:
    if relation == "molecule_associated_phenotype":
        return {"DrugBank"}, {"HPO"}
    if relation == "molecule_parent_of_molecule":
        return {"CTD"}, {"CTD"}
    if relation == "molecule_synergizes_molecule":
        return {"DrugBank"}, {"DrugBank"}
    if relation == "molecule_treats_disease" and predicate == "linked to":
        return {"CTD"}, {"MONDO", "MONDO_grouped"}
    return {"DrugBank"}, {"MONDO", "MONDO_grouped"}


def build_candidates(source_rows: pd.DataFrame, *, source_offset_start: int = 0) -> BuildResult:
    edge_rows = {relation: [] for relation in SOURCE_ASSERTIONS}
    evidence_rows = {relation: [] for relation in SOURCE_ASSERTIONS}
    rejected: list[dict[str, object]] = []

    for chunk_offset, row in source_rows.reset_index(drop=True).iterrows():
        source_offset = source_offset_start + chunk_offset
        legacy_relation = _clean(row.get("relation"))
        predicate = _clean(row.get("display_relation"))
        relation = LEGACY_TO_CANONICAL.get(legacy_relation)
        if relation is None or predicate not in SOURCE_ASSERTIONS[relation]["source_predicates"]:
            rejected.append(
                {
                    "source_offset": source_offset,
                    "target_relation": relation,
                    "legacy_relation": legacy_relation,
                    "source_predicate": predicate,
                    "reason": "unsupported_assertion",
                }
            )
            continue
        expected_x_type, expected_y_type = _expected_legacy_types(relation, predicate)
        observed_x_type = _clean(row.get("x_type"))
        observed_y_type = _clean(row.get("y_type"))
        if (observed_x_type, observed_y_type) != (expected_x_type, expected_y_type):
            rejected.append(
                {
                    "source_offset": source_offset,
                    "target_relation": relation,
                    "legacy_relation": legacy_relation,
                    "source_predicate": predicate,
                    "reason": (
                        f"endpoint_type_mismatch:expected {expected_x_type}->{expected_y_type}, "
                        f"observed {observed_x_type}->{observed_y_type}"
                    ),
                }
            )
            continue
        expected_x_sources, expected_y_sources = _expected_legacy_sources(relation, predicate)
        observed_x_source = _clean(row.get("x_source"))
        observed_y_source = _clean(row.get("y_source"))
        if observed_x_source not in expected_x_sources or observed_y_source not in expected_y_sources:
            rejected.append(
                {
                    "source_offset": source_offset,
                    "target_relation": relation,
                    "legacy_relation": legacy_relation,
                    "source_predicate": predicate,
                    "reason": (
                        f"endpoint_namespace_mismatch:expected {'|'.join(sorted(expected_x_sources))}"
                        f"->{'|'.join(sorted(expected_y_sources))}, observed "
                        f"{observed_x_source}->{observed_y_source}"
                    ),
                }
            )
            continue
        try:
            x_id = _normalize_id(row.get("x_id"), row.get("x_type"), row.get("x_source", ""))
            y_id = _normalize_id(row.get("y_id"), row.get("y_type"), row.get("y_source", ""))
        except (TypeError, ValueError) as exc:
            rejected.append(
                {
                    "source_offset": source_offset,
                    "target_relation": relation,
                    "legacy_relation": legacy_relation,
                    "source_predicate": predicate,
                    "reason": f"mapping_failure:{exc}",
                }
            )
            continue

        x_type, y_type = _expected_types(relation)
        edge = {
            "x_id": x_id,
            "x_type": x_type,
            "y_id": y_id,
            "y_type": y_type,
            "relation": relation,
            "display_relation": predicate,
            "source": "TxGNN",
            "credibility": 3,
        }
        edge_rows[relation].append(edge)
        spec = SOURCE_ASSERTIONS[relation]
        evidence_rows[relation].append(
            {
                "edge_key": f"{relation}|{x_id}|{y_id}",
                "relation": relation,
                "x_id": x_id,
                "x_type": x_type,
                "y_id": y_id,
                "y_type": y_type,
                "evidence_type": "legacy_source_assertion",
                "source": "TxGNN/PrimeKG",
                "source_dataset": spec["constituent_source"],
                "source_release": spec["source_release"],
                "source_record_id": f"TxGNN:kg.csv:{source_offset}",
                "source_predicate": predicate,
                "original_x_id": _clean(row.get("x_id")),
                "original_x_type": _clean(row.get("x_type")),
                "original_y_id": _clean(row.get("y_id")),
                "original_y_type": _clean(row.get("y_type")),
                "mapping_method": "TxGNN typed endpoint normalization",
                "mapping_confidence": "exact",
                "pair_orientation": spec["orientation"],
                "symmetric": spec["symmetric"],
                "license": TXGNN_DATASET["license"],
            }
        )

    edges = {}
    evidence = {}
    for relation in SOURCE_ASSERTIONS:
        frame = pd.DataFrame(edge_rows[relation], columns=EDGE_COLUMNS)
        edges[relation] = (
            frame.sort_values(["x_id", "y_id", "display_relation"], kind="stable")
            .drop_duplicates(["relation", "x_id", "y_id"], keep="first")
            .reset_index(drop=True)
        )
        evidence[relation] = pd.DataFrame(evidence_rows[relation], columns=EVIDENCE_COLUMNS).sort_values(
            ["x_id", "y_id", "source_record_id"], kind="stable"
        ).reset_index(drop=True)
    return BuildResult(edges=edges, evidence=evidence, rejections=pd.DataFrame(rejected))


def _keys(frame: pd.DataFrame) -> set[tuple[str, str, str]]:
    return set(map(tuple, frame[["relation", "x_id", "y_id"]].drop_duplicates().values))


def compare_candidate(
    relation: str,
    candidate: pd.DataFrame,
    canonical: pd.DataFrame,
    *,
    x_endpoints: set[str],
    y_endpoints: set[str],
    later_support: pd.DataFrame | None = None,
) -> dict[str, object]:
    candidate_keys = _keys(candidate)
    canonical_keys = _keys(canonical)
    report: dict[str, object] = {
        "relation": relation,
        "canonical_generation": CANONICAL_GENERATIONS[relation],
        "candidate_rows": len(candidate),
        "candidate_distinct_keys": len(candidate_keys),
        "canonical_rows": len(canonical),
        "canonical_distinct_keys": len(canonical_keys),
        "intersection": len(candidate_keys & canonical_keys),
        "candidate_only": len(candidate_keys - canonical_keys),
        "canonical_only": len(canonical_keys - candidate_keys),
        "candidate_duplicate_keys": int(candidate.duplicated(["relation", "x_id", "y_id"]).sum()),
        "canonical_duplicate_keys": int(canonical.duplicated(["relation", "x_id", "y_id"]).sum()),
        "x_endpoint_anti_join": len({x for _, x, _ in candidate_keys if x not in x_endpoints}),
        "y_endpoint_anti_join": len({y for _, _, y in candidate_keys if y not in y_endpoints}),
    }
    if later_support is not None:
        support_keys = _keys(later_support)
        report.update(
            {
                "canonical_supported_by_later_evidence": len(canonical_keys & support_keys),
                "canonical_unsupported_by_later_evidence": len(canonical_keys - support_keys),
                "later_evidence_without_canonical_edge": len(support_keys - canonical_keys),
            }
        )
    return report


def iter_csv(path: Path, chunksize: int) -> Iterator[pd.DataFrame]:
    yield from pd.read_csv(path, dtype=str, chunksize=chunksize, low_memory=False)


def write_replay(
    source: Path,
    output_dir: Path,
    *,
    fixture: bool,
    fixture_allowed_root: Path | None = None,
    canonical_dir: Path | None,
    canonical_manifest: Path | None = None,
    chunksize: int,
    admission: RunAdmission | None = None,
    started: float | None = None,
) -> None:
    if not fixture and socket.gethostname() != "txgnn-worker":
        raise RuntimeError("full replay must run on txgnn-worker")
    _validate_output_path(output_dir, fixture=fixture, fixture_allowed_root=fixture_allowed_root)
    if not fixture and admission is None:
        raise ValueError("full replay requires a validated launcher receipt")
    snapshot_manifest = None
    if canonical_dir is not None:
        if canonical_manifest is None or not canonical_manifest.is_file():
            raise ValueError("canonical snapshot manifest is required for parity")
        snapshot_manifest = json.loads(canonical_manifest.read_text())
        observed_generations = snapshot_manifest.get("edge_generations", {})
        if observed_generations != CANONICAL_GENERATIONS:
            raise ValueError("canonical snapshot manifest edge generations do not match frozen contract")
        objects = snapshot_manifest.get("objects", {})
        required_paths = [f"edges/{relation}.parquet" for relation in CANONICAL_GENERATIONS]
        required_paths += [f"nodes/{node_type}.parquet" for node_type in ("molecule", "disease", "phenotype")]
        evidence_path = canonical_dir / "evidence" / "molecule_treats_disease.parquet"
        if evidence_path.exists():
            required_paths.append("evidence/molecule_treats_disease.parquet")
        for relative_path in required_paths:
            path = canonical_dir / relative_path
            identity = objects.get(relative_path, {})
            if (
                not path.is_file()
                or identity.get("size") != path.stat().st_size
                or identity.get("sha256") != file_sha256(path)
            ):
                raise ValueError(f"snapshot object identity mismatch: {relative_path}")
    output_dir.mkdir(parents=True, exist_ok=False)
    source_identity = verify_source(source, allow_fixture=fixture)
    chunks = []
    source_offset = 0
    started = started if started is not None else time.monotonic()
    for chunk in iter_csv(source, chunksize):
        chunks.append(build_candidates(chunk, source_offset_start=source_offset))
        source_offset += len(chunk)
        _payload_heartbeat(admission, started=started, source_rows=source_offset)
    if not chunks:
        raise ValueError("source kg.csv contains no rows")
    combined = BuildResult(
        edges={
            relation: pd.concat([chunk.edges[relation] for chunk in chunks], ignore_index=True)
            .sort_values(["x_id", "y_id", "display_relation"], kind="stable")
            .drop_duplicates(["relation", "x_id", "y_id"])
            .reset_index(drop=True)
            for relation in SOURCE_ASSERTIONS
        },
        evidence={
            relation: pd.concat([chunk.evidence[relation] for chunk in chunks], ignore_index=True)
            .sort_values(["x_id", "y_id", "source_record_id"], kind="stable")
            .reset_index(drop=True)
            for relation in SOURCE_ASSERTIONS
        },
        rejections=pd.concat([chunk.rejections for chunk in chunks], ignore_index=True),
    )

    (output_dir / "edges").mkdir()
    (output_dir / "evidence").mkdir()
    for relation in SOURCE_ASSERTIONS:
        combined.edges[relation].to_parquet(output_dir / "edges" / f"{relation}.parquet", index=False)
        combined.evidence[relation].to_parquet(output_dir / "evidence" / f"{relation}.parquet", index=False)
    combined.rejections.to_parquet(output_dir / "mapping_quarantine.parquet", index=False)

    relation_stats = {}
    rejection_relations = combined.rejections.get("target_relation", pd.Series(dtype=object))
    for relation in SOURCE_ASSERTIONS:
        evidence = combined.evidence[relation]
        relation_rejections = combined.rejections[rejection_relations == relation]
        reasons = relation_rejections.get("reason", pd.Series(dtype=str)).value_counts().sort_index()
        relation_stats[relation] = {
            **SOURCE_ASSERTIONS[relation],
            "canonical_generation": CANONICAL_GENERATIONS[relation],
            "source_selected_rows": len(evidence) + len(relation_rejections),
            "accepted_rows": len(evidence),
            "source_duplicate_assertions": int(
                evidence.duplicated(["relation", "x_id", "y_id"], keep="first").sum()
            ),
            "distinct_edge_keys": len(combined.edges[relation]),
            "evidence_rows": len(evidence),
            "distinct_evidence_ids": int(evidence["source_record_id"].nunique()),
            "rejected_rows": len(relation_rejections),
            "mapping_failure_rows": int(reasons[reasons.index.str.startswith("mapping_failure:")].sum()),
            "rejections_by_reason": {str(reason): int(count) for reason, count in reasons.items()},
        }

    output_paths = [output_dir / "mapping_quarantine.parquet"]
    output_paths.extend(
        output_dir / kind / f"{relation}.parquet"
        for kind in ("edges", "evidence")
        for relation in SOURCE_ASSERTIONS
    )
    manifest: dict[str, object] = {
        "task_id": "t_86299745",
        "status": "staged-only",
        "canonical_write": False,
        "source_contract": TXGNN_DATASET,
        "source_identity": source_identity,
        "canonical_snapshot_manifest": str(canonical_manifest) if canonical_manifest else None,
        "relations": relation_stats,
        "mapping_quarantine_rows": len(combined.rejections),
        "objects": {
            str(path.relative_to(output_dir)): _object_identity(path)
            for path in sorted(output_paths)
        },
    }

    if canonical_dir is not None:
        parity = {}
        node_cache: dict[str, set[str]] = {}
        for node_type in ("molecule", "disease", "phenotype"):
            node_cache[node_type] = set(pd.read_parquet(canonical_dir / "nodes" / f"{node_type}.parquet", columns=["id"])["id"])
        later_support_path = canonical_dir / "evidence" / "molecule_treats_disease.parquet"
        later_support = pd.read_parquet(later_support_path) if later_support_path.exists() else None
        for relation in SOURCE_ASSERTIONS:
            canonical = pd.read_parquet(canonical_dir / "edges" / f"{relation}.parquet")
            x_type, y_type = _expected_types(relation)
            parity[relation] = compare_candidate(
                relation,
                combined.edges[relation],
                canonical,
                x_endpoints=node_cache[x_type],
                y_endpoints=node_cache[y_type],
                later_support=later_support if relation == "molecule_treats_disease" else None,
            )
            parity[relation].update(relation_stats[relation])
        (output_dir / "parity_report.json").write_text(json.dumps(parity, indent=2, sort_keys=True) + "\n")
        manifest["parity_report"] = "parity_report.json"
        object_manifest = manifest["objects"]
        assert isinstance(object_manifest, dict)
        object_manifest["parity_report.json"] = _object_identity(output_dir / "parity_report.json")

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def verify_replay(output_dir: Path) -> dict[str, object]:
    """Read back every manifest-bound replay object and reject extra/mutated bytes."""
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    objects = manifest.get("objects")
    if not isinstance(objects, dict) or not objects:
        raise ValueError("replay manifest has no object identities")
    for relative_path, identity in objects.items():
        path = output_dir / relative_path
        if not path.is_file() or identity != _object_identity(path):
            raise ValueError(f"replay object identity mismatch: {relative_path}")
    actual = {
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual != set(objects):
        raise ValueError("replay object inventory mismatch")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Already acquired release-pinned TxGNN kg.csv")
    parser.add_argument("--acquire-to", type=Path, help="Create-only acquisition destination for TxGNN kg.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="New absent task-scoped output directory")
    parser.add_argument("--canonical-dir", type=Path, help="Read-only flat canonical snapshot for parity")
    parser.add_argument("--canonical-manifest", type=Path, help="Snapshot identity with exact frozen edge generations")
    parser.add_argument("--fixture", action="store_true", help="Permit a bounded fixture instead of exact source bytes")
    parser.add_argument("--fixture-allowed-root", type=Path, help="Explicit safe root for test-only fixture output")
    parser.add_argument("--launcher-receipt", type=Path, help="Fresh lifecycle launcher lease readback for full replay")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args(argv)
    if (args.source is None) == (args.acquire_to is None):
        parser.error("provide exactly one of --source or --acquire-to")
    admission = None
    if args.fixture:
        if args.acquire_to is not None:
            parser.error("fixture replay requires --source; it cannot acquire the full release")
        _validate_output_path(
            args.output_dir,
            fixture=True,
            fixture_allowed_root=args.fixture_allowed_root,
        )
    else:
        if socket.gethostname() != "txgnn-worker":
            raise RuntimeError("full replay must run on txgnn-worker")
        _validate_output_path(args.output_dir, fixture=False, fixture_allowed_root=None)
        admission = validate_launcher_receipt(args.launcher_receipt or Path(""))
        if args.acquire_to is not None:
            _reject_dangerous_path(args.acquire_to, label="acquisition")
        if args.source is not None:
            _reject_dangerous_path(args.source, label="source")
    source = args.source
    with _exclusive_run(admission):
        started = time.monotonic()
        if args.acquire_to is not None:
            acquire_source(
                TXGNN_DATASET["url"],
                args.acquire_to,
                admission=admission,
                started=started,
            )
            source = args.acquire_to
        assert source is not None
        write_replay(
            source,
            args.output_dir,
            fixture=args.fixture,
            fixture_allowed_root=args.fixture_allowed_root,
            canonical_dir=args.canonical_dir,
            canonical_manifest=args.canonical_manifest,
            chunksize=args.chunksize,
            admission=admission,
            started=started,
        )
        verify_replay(args.output_dir)


if __name__ == "__main__":
    main()
