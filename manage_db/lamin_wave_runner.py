"""Plan and capability-gate bounded LaminDB ingestion waves from an accepted manifest.

This module never scans canonical Parquet payloads while planning.  It accepts
only the immutable 72-lane reconciliation manifest reviewed under t_6f200217,
emits deterministic argv arrays, and keeps durable checkpoint advancement
behind selected-live verification and write/flush/fsync/ack ordering.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import resource
import secrets
import shutil
import socket
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, overload

ACCEPTED_MANIFEST_SHA256 = "3f587a2947e1d4e1a2685a886eb8b65e6b2fa3bbeb01431ac846ff617b1ffb64"
EXPECTED_INSTANCE = "jkobject/jouvencekb"
EXPECTED_KG_ROOT = "gs://jouvencekb/kg/v2"
EXPECTED_EXECUTION_HOST = "txgnn-worker"
MAX_ROWS_PER_WAVE = 5_000
MAX_CHUNKS_PER_WAVE = 1
MAX_RUNTIME_SECONDS = 900
MAX_RETRIES = 2

EXPECTED_LANE_KEYS = (
    "edge:cell_line_derived_from_tissue",
    "edge:cell_line_expresses_gene",
    "edge:cell_line_from_organism",
    "edge:cell_type_expresses_gene",
    "edge:disease_associated_gene",
    "edge:disease_has_phenotype",
    "edge:disease_involves_pathway",
    "edge:disease_manifests_in_tissue",
    "edge:disease_subtype_of_disease",
    "edge:enhancer_regulates_gene",
    "edge:gene_associated_phenotype",
    "edge:gene_has_transcript",
    "edge:gene_interacts_gene",
    "edge:gene_ortholog_gene",
    "edge:molecule_associated_phenotype",
    "edge:molecule_contraindicates_disease",
    "edge:molecule_in_pathway",
    "edge:molecule_parent_of_molecule",
    "edge:molecule_synergizes_molecule",
    "edge:molecule_targets_gene",
    "edge:molecule_treats_disease",
    "edge:mutation_affects_molecule_response",
    "edge:mutation_affects_transcript",
    "edge:mutation_associated_disease",
    "edge:mutation_associated_gene",
    "edge:mutation_associated_phenotype",
    "edge:mutation_causes_protein_change",
    "edge:mutation_in_gene",
    "edge:mutation_overlaps_enhancer",
    "edge:organism_has_gene",
    "edge:organism_has_tissue",
    "edge:pathway_child_of_pathway",
    "edge:pathway_contains_gene",
    "edge:phenotype_subtype_of_phenotype",
    "edge:protein_interacts_protein",
    "edge:tissue_expresses_gene",
    "edge:tissue_expresses_protein",
    "edge:tissue_subtype_of_tissue",
    "edge:transcript_encodes_protein",
    "evidence:cell_line_from_organism",
    "evidence:disease_associated_gene",
    "evidence:disease_involves_pathway",
    "evidence:disease_manifests_in_tissue",
    "evidence:enhancer_regulates_gene",
    "evidence:gene_interacts_gene",
    "evidence:gene_ortholog_gene",
    "evidence:molecule_targets_gene",
    "evidence:molecule_treats_disease",
    "evidence:mutation_affects_molecule_response",
    "evidence:mutation_affects_transcript",
    "evidence:mutation_associated_disease",
    "evidence:mutation_associated_gene",
    "evidence:mutation_associated_phenotype",
    "evidence:mutation_causes_protein_change",
    "evidence:mutation_in_gene",
    "evidence:mutation_overlaps_enhancer",
    "evidence:pathway_contains_gene",
    "evidence:protein_interacts_protein",
    "evidence:tissue_expresses_protein",
    "node:cell_line",
    "node:cell_type",
    "node:disease",
    "node:enhancer",
    "node:gene",
    "node:molecule",
    "node:mutation",
    "node:organism",
    "node:pathway",
    "node:phenotype",
    "node:protein",
    "node:tissue",
    "node:transcript",
)

EXPECTED_AGGREGATES = {
    "node": (13, 52_565_491, 3_771_054, 48_794_437),
    "edge": (39, 101_743_458, 1_431_264, 100_312_194),
    "evidence": (20, 76_565_213, 1_389_167, 75_176_046),
}


@dataclass(frozen=True)
class ResourceBounds:
    cpu_cores: int
    memory_bytes: int


@dataclass(frozen=True)
class WaveBounds:
    max_rows: int
    max_chunks: int
    max_runtime_seconds: int
    resources: ResourceBounds


@dataclass(frozen=True)
class StopCriteria:
    mismatch_count: int
    require_selected_live: bool
    require_write_flush_fsync_ack: bool


@dataclass(frozen=True)
class CheckpointBoundary:
    accepted: int | None = None
    sealed_candidate: int | None = None
    live_count: int | None = None


@dataclass(frozen=True)
class WaveSpec:
    wave_id: str
    families: tuple[str, ...]
    lane_keys: tuple[str, ...]
    allowlist: tuple[str, ...]
    node_type_allowlist: tuple[str, ...]
    relation_allowlist: tuple[str, ...]
    source_rows: tuple[int, ...]
    current_rows: tuple[int, ...]
    remaining_deltas: tuple[int, ...]
    start_checkpoints: tuple[int, ...]
    end_checkpoints: tuple[int, ...]
    argv: tuple[str, ...]
    verification_argvs: tuple[tuple[str, ...], ...]
    bounds: WaveBounds
    progress_path: Path
    ack_path: Path
    ledger_path: Path
    stop_criteria: StopCriteria
    max_retries: int
    instance: str
    kg_root: str
    execution_host: str
    checkpoints: CheckpointBoundary


@dataclass(frozen=True)
class WavePlan:
    manifest_sha256: str
    manifest_lane_count: int
    waves: tuple[WaveSpec, ...]
    zero_no_work: dict[str, int]
    negative_no_work: dict[str, int]
    digest: str


@dataclass(frozen=True)
class ExecutionResult:
    returncode: int
    summary: Mapping[str, Any]


@dataclass(frozen=True)
class WriterCapability:
    token: str
    plan_digest: str
    expires_at: float


_ACTIVE_CAPABILITIES: dict[str, tuple[str, float]] = {}


class _AcceptedManifest(Sequence[Mapping[str, Any]]):
    """Immutable manifest rows whose exact source bytes passed the SHA gate."""

    def __init__(self, rows: Sequence[Mapping[str, Any]], sha256: str) -> None:
        self._rows = tuple(MappingProxyType(dict(row)) for row in rows)
        self.sha256 = sha256

    @overload
    def __getitem__(self, index: int) -> Mapping[str, Any]: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[Mapping[str, Any]]: ...

    def __getitem__(self, index: int | slice) -> Mapping[str, Any] | Sequence[Mapping[str, Any]]:
        return self._rows[index]

    def __len__(self) -> int:
        return len(self._rows)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_manifest_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    if len(rows) != len(EXPECTED_LANE_KEYS):
        raise ValueError(f"manifest must contain exactly {len(EXPECTED_LANE_KEYS)} lanes")

    lane_keys = [str(row.get("lane_key", "")) for row in rows]
    if len(set(lane_keys)) != len(lane_keys):
        raise ValueError("manifest contains duplicate lane keys")
    expected = set(EXPECTED_LANE_KEYS)
    actual = set(lane_keys)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(f"manifest lane mismatch: missing={missing}, unknown={unknown}")
    if tuple(lane_keys) != EXPECTED_LANE_KEYS:
        raise ValueError("manifest lane ordering is not the accepted deterministic order")

    for row in rows:
        family = str(row.get("family", ""))
        name = str(row.get("canonical_name", ""))
        lane_key = str(row.get("lane_key", ""))
        if family not in EXPECTED_AGGREGATES or lane_key != f"{family}:{name}":
            raise ValueError(f"invalid family/name mapping for {lane_key!r}")
        if row.get("mapping_identifiable") is not True:
            raise ValueError(f"ambiguous live destination mapping for {lane_key}")
        source = row.get("source_rows")
        current = row.get("current_lamin_rows")
        delta = row.get("remaining_delta")
        if type(source) is not int or type(current) is not int or type(delta) is not int:
            raise ValueError(f"non-integer counts for {lane_key}")
        if source < 0 or current < 0 or delta != source - current:
            raise ValueError(f"invalid unclamped arithmetic for {lane_key}")
        layer = {"node": "nodes", "edge": "edges", "evidence": "evidence"}[family]
        expected_uri = f"{EXPECTED_KG_ROOT}/{layer}/{name}.parquet"
        if row.get("source_uri") != expected_uri:
            raise ValueError(f"unexpected source URI for {lane_key}")

    for family, expected_values in EXPECTED_AGGREGATES.items():
        family_rows = [row for row in rows if row["family"] == family]
        actual_values = (
            len(family_rows),
            sum(int(row["source_rows"]) for row in family_rows),
            sum(int(row["current_lamin_rows"]) for row in family_rows),
            sum(int(row["remaining_delta"]) for row in family_rows),
        )
        if actual_values != expected_values:
            raise ValueError(
                f"{family} aggregate mismatch: expected={expected_values}, actual={actual_values}"
            )

    if sum(int(row["current_lamin_rows"]) == 0 for row in rows) != 53:
        raise ValueError("accepted manifest must preserve 53 zero-current lanes")
    negatives = {
        str(row["lane_key"]): int(row["remaining_delta"])
        for row in rows
        if int(row["remaining_delta"]) < 0
    }
    if negatives != {"node:cell_line": -165_943, "node:phenotype": -6_270}:
        raise ValueError("accepted negative deltas were changed or clamped")


def load_accepted_manifest(path: str | Path) -> _AcceptedManifest:
    manifest_path = Path(path)
    raw = manifest_path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError("manifest must be a JSON list of lane objects")
    rows = [dict(row) for row in payload]
    _validate_manifest_rows(rows)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != ACCEPTED_MANIFEST_SHA256:
        raise ValueError(
            f"manifest sha256 mismatch: expected {ACCEPTED_MANIFEST_SHA256}, got {digest}"
        )
    return _AcceptedManifest(rows, digest)


def _safe_wave_dir(artifact_root: Path, wave_id: str) -> Path:
    return artifact_root / wave_id.replace(":", "--")


def _node_wave(row: Mapping[str, Any], artifact_root: Path) -> WaveSpec:
    name = str(row["canonical_name"])
    delta = int(row["remaining_delta"])
    start = int(row["current_lamin_rows"])
    limit = min(MAX_ROWS_PER_WAVE, delta)
    directory = _safe_wave_dir(artifact_root, f"node:{name}")
    argv = (
        "uv",
        "run",
        "python",
        "-m",
        "manage_db.sync_parquet_nodes_to_lamindb",
        EXPECTED_KG_ROOT,
        "--node-types",
        name,
        "--lamin-instance",
        EXPECTED_INSTANCE,
        "--max-rows",
        str(limit),
        "--row-offset",
        str(start),
        "--batch-size",
        str(limit),
        "--write",
        "--json",
    )
    verification = tuple(arg for arg in argv if arg != "--write")
    return WaveSpec(
        wave_id=f"node:{name}",
        families=("node",),
        lane_keys=(str(row["lane_key"]),),
        allowlist=(name,),
        node_type_allowlist=(name,),
        relation_allowlist=(),
        source_rows=(int(row["source_rows"]),),
        current_rows=(int(row["current_lamin_rows"]),),
        remaining_deltas=(delta,),
        start_checkpoints=(start,),
        end_checkpoints=(start + limit,),
        argv=argv,
        verification_argvs=(verification,),
        bounds=WaveBounds(
            max_rows=limit,
            max_chunks=MAX_CHUNKS_PER_WAVE,
            max_runtime_seconds=MAX_RUNTIME_SECONDS,
            resources=ResourceBounds(cpu_cores=2, memory_bytes=4 * 1024**3),
        ),
        progress_path=(directory / "progress.jsonl").resolve(),
        ack_path=(directory / "ack.jsonl").resolve(),
        ledger_path=(directory / "checkpoint.json").resolve(),
        stop_criteria=StopCriteria(0, True, True),
        max_retries=MAX_RETRIES,
        instance=EXPECTED_INSTANCE,
        kg_root=EXPECTED_KG_ROOT,
        execution_host=EXPECTED_EXECUTION_HOST,
        checkpoints=CheckpointBoundary(),
    )


def _relation_wave(
    relation: str,
    edge_row: Mapping[str, Any],
    evidence_row: Mapping[str, Any] | None,
    artifact_root: Path,
) -> WaveSpec:
    rows = [edge_row]
    if evidence_row is not None and int(evidence_row["remaining_delta"]) > 0:
        rows.append(evidence_row)
    if relation == "enhancer_regulates_gene":
        starts = tuple(10_315_000 for _ in rows)
        checkpoints = CheckpointBoundary(
            accepted=10_315_000,
            sealed_candidate=11_345_000,
            live_count=1_345_000,
        )
    else:
        starts = tuple(int(row["current_lamin_rows"]) for row in rows)
        checkpoints = CheckpointBoundary()
    limits = tuple(min(MAX_ROWS_PER_WAVE, int(row["remaining_delta"])) for row in rows)
    ends = tuple(start + limit for start, limit in zip(starts, limits, strict=True))
    directory = _safe_wave_dir(artifact_root, f"relation:{relation}")

    argv_parts = [
        "uv",
        "run",
        "python",
        "-m",
        "manage_db.sync_parquet_edges_to_lamindb",
        EXPECTED_KG_ROOT,
        "--relation",
        relation,
        "--edge-offset",
        str(starts[0]),
        "--edge-limit",
        str(limits[0]),
    ]
    if len(rows) == 2:
        argv_parts.extend(
            [
                "--evidence-offset",
                str(starts[1]),
                "--evidence-limit",
                str(limits[1]),
            ]
        )
    else:
        argv_parts.append("--skip-evidence")
    argv_parts.extend(
        [
            "--chunk-size",
            str(MAX_ROWS_PER_WAVE),
            "--max-chunks",
            str(MAX_CHUNKS_PER_WAVE),
            "--lamin-instance",
            EXPECTED_INSTANCE,
            "--write",
            "--verify-selected-live",
            "--json",
        ]
    )
    verification = tuple(arg for arg in argv_parts if arg != "--write")
    families = tuple(str(row["family"]) for row in rows)
    return WaveSpec(
        wave_id=f"relation:{relation}",
        families=families,
        lane_keys=tuple(str(row["lane_key"]) for row in rows),
        allowlist=(relation,),
        node_type_allowlist=(),
        relation_allowlist=(relation,),
        source_rows=tuple(int(row["source_rows"]) for row in rows),
        current_rows=tuple(int(row["current_lamin_rows"]) for row in rows),
        remaining_deltas=tuple(int(row["remaining_delta"]) for row in rows),
        start_checkpoints=starts,
        end_checkpoints=ends,
        argv=tuple(argv_parts),
        verification_argvs=(verification,),
        bounds=WaveBounds(
            max_rows=max(limits),
            max_chunks=MAX_CHUNKS_PER_WAVE,
            max_runtime_seconds=MAX_RUNTIME_SECONDS,
            resources=ResourceBounds(cpu_cores=2, memory_bytes=4 * 1024**3),
        ),
        progress_path=(directory / "progress.jsonl").resolve(),
        ack_path=(directory / "ack.jsonl").resolve(),
        ledger_path=(directory / "checkpoint.json").resolve(),
        stop_criteria=StopCriteria(0, True, True),
        max_retries=MAX_RETRIES,
        instance=EXPECTED_INSTANCE,
        kg_root=EXPECTED_KG_ROOT,
        execution_host=EXPECTED_EXECUTION_HOST,
        checkpoints=checkpoints,
    )


def _wave_to_dict(wave: WaveSpec) -> dict[str, Any]:
    payload = asdict(wave)
    for key in ("progress_path", "ack_path", "ledger_path"):
        payload[key] = str(getattr(wave, key))
    return payload


def _plan_digest(
    waves: Sequence[WaveSpec],
    zero_no_work: Mapping[str, int],
    negative_no_work: Mapping[str, int],
) -> str:
    payload = {
        "manifest_sha256": ACCEPTED_MANIFEST_SHA256,
        "waves": [_wave_to_dict(wave) for wave in waves],
        "zero_no_work": dict(sorted(zero_no_work.items())),
        "negative_no_work": dict(sorted(negative_no_work.items())),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def plan_waves(
    rows: Sequence[Mapping[str, Any]],
    *,
    artifact_root: str | Path,
) -> WavePlan:
    if not isinstance(rows, _AcceptedManifest) or rows.sha256 != ACCEPTED_MANIFEST_SHA256:
        raise ValueError("planner requires rows attested by load_accepted_manifest")
    _validate_manifest_rows(rows)
    root = Path(artifact_root).expanduser().resolve()
    zero_no_work = {
        str(row["lane_key"]): 0 for row in rows if int(row["remaining_delta"]) == 0
    }
    negative_no_work = {
        str(row["lane_key"]): int(row["remaining_delta"])
        for row in rows
        if int(row["remaining_delta"]) < 0
    }

    row_by_key = {str(row["lane_key"]): row for row in rows}
    waves: list[WaveSpec] = []
    for row in rows:
        if row["family"] == "node" and int(row["remaining_delta"]) > 0:
            waves.append(_node_wave(row, root))
    for edge_key in (key for key in EXPECTED_LANE_KEYS if key.startswith("edge:")):
        edge_row = row_by_key[edge_key]
        if int(edge_row["remaining_delta"]) <= 0:
            continue
        relation = str(edge_row["canonical_name"])
        evidence_row = row_by_key.get(f"evidence:{relation}")
        waves.append(_relation_wave(relation, edge_row, evidence_row, root))

    ordered = tuple(sorted(waves, key=lambda wave: wave.wave_id))
    for wave in ordered:
        validate_wave_spec(wave)
    return WavePlan(
        manifest_sha256=ACCEPTED_MANIFEST_SHA256,
        manifest_lane_count=len(rows),
        waves=ordered,
        zero_no_work=zero_no_work,
        negative_no_work=negative_no_work,
        digest=_plan_digest(ordered, zero_no_work, negative_no_work),
    )


def _option_values(argv: Sequence[str], option: str) -> list[str]:
    values: list[str] = []
    for index, arg in enumerate(argv):
        if arg == option:
            if index + 1 >= len(argv):
                raise ValueError(f"missing value for {option}")
            values.append(str(argv[index + 1]))
    return values


def _validate_argv_array(argv: tuple[str, ...], *, verification: bool = False) -> None:
    if not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ValueError("commands must be non-empty argv arrays")
    if argv[0] in {"sh", "bash", "zsh"} or "-c" in argv:
        raise ValueError("shell command text is forbidden; use argv arrays")
    if not verification and "--write" not in argv:
        raise ValueError("executable wave command must explicitly request bounded write mode")


def validate_wave_spec(wave: WaveSpec) -> None:
    if wave.instance != EXPECTED_INSTANCE:
        raise ValueError(f"wrong Lamin instance: {wave.instance}")
    if wave.kg_root != EXPECTED_KG_ROOT or wave.kg_root.startswith("/Users/jkobject/mnt/gcs"):
        raise ValueError(f"unsafe or unexpected KG root: {wave.kg_root}")
    if wave.execution_host != EXPECTED_EXECUTION_HOST:
        raise ValueError(f"heavy wave must execute on {EXPECTED_EXECUTION_HOST}")
    if not wave.lane_keys or len(wave.lane_keys) != len(wave.remaining_deltas):
        raise ValueError("wave lane/count cardinality mismatch")
    if any(delta <= 0 for delta in wave.remaining_deltas):
        raise ValueError("zero or negative deltas cannot become executable work")
    if not wave.allowlist or len(set(wave.allowlist)) != len(wave.allowlist):
        raise ValueError("wave requires a non-empty exact allowlist")
    if any(name in {"*", "all", "ALL"} for name in wave.allowlist):
        raise ValueError("all-lane write requests are forbidden")
    if bool(wave.node_type_allowlist) == bool(wave.relation_allowlist):
        raise ValueError("wave must select exactly one node-type or relation allowlist")
    if tuple(wave.allowlist) != tuple(wave.node_type_allowlist or wave.relation_allowlist):
        raise ValueError("command allowlist is ambiguous")

    _validate_argv_array(wave.argv)
    expected_module = (
        "manage_db.sync_parquet_nodes_to_lamindb"
        if wave.node_type_allowlist
        else "manage_db.sync_parquet_edges_to_lamindb"
    )
    expected_prefix = ("uv", "run", "python", "-m", expected_module, EXPECTED_KG_ROOT)
    if wave.argv[:6] != expected_prefix:
        raise ValueError("wave argv must invoke the exact approved adapter and canonical KG root")
    if _option_values(wave.argv, "--lamin-instance") != [EXPECTED_INSTANCE]:
        raise ValueError("wave argv must target the exact accepted Lamin instance")
    if not all(wave.argv.count(name) == 1 for name in wave.allowlist):
        raise ValueError("argv does not contain the exact wave allowlist")
    if wave.node_type_allowlist:
        if _option_values(wave.argv, "--node-types") != list(wave.node_type_allowlist):
            raise ValueError("node wave must contain an exact node-type allowlist")
        if _option_values(wave.argv, "--row-offset") != [str(wave.start_checkpoints[0])]:
            raise ValueError("node argv row offset does not match the wave checkpoint")
        expected_limit = wave.end_checkpoints[0] - wave.start_checkpoints[0]
        if _option_values(wave.argv, "--max-rows") != [str(expected_limit)]:
            raise ValueError("node argv row limit does not match the wave checkpoint")
        if _option_values(wave.argv, "--batch-size") != [str(expected_limit)]:
            raise ValueError("node argv batch size must equal the bounded selected window")
        if _option_values(wave.argv, "--max-chunks"):
            raise ValueError("node adapter does not accept chunk-count overrides")
    else:
        if _option_values(wave.argv, "--relation") != list(wave.relation_allowlist):
            raise ValueError("relation wave must contain an exact relation allowlist")
        if _option_values(wave.argv, "--edge-offset") != [str(wave.start_checkpoints[0])]:
            raise ValueError("edge argv offset does not match the wave checkpoint")
        expected_edge_limit = wave.end_checkpoints[0] - wave.start_checkpoints[0]
        if _option_values(wave.argv, "--edge-limit") != [str(expected_edge_limit)]:
            raise ValueError("edge argv limit does not match the wave checkpoint")
        has_evidence = any(key.startswith("evidence:") for key in wave.lane_keys)
        if has_evidence == ("--skip-evidence" in wave.argv):
            raise ValueError("evidence must be explicit and must never be inferred from edge work")
        if has_evidence:
            if _option_values(wave.argv, "--evidence-offset") != [str(wave.start_checkpoints[1])]:
                raise ValueError("evidence argv offset does not match its independent checkpoint")
            expected_evidence_limit = wave.end_checkpoints[1] - wave.start_checkpoints[1]
            if _option_values(wave.argv, "--evidence-limit") != [str(expected_evidence_limit)]:
                raise ValueError("evidence argv limit does not match its independent checkpoint")
        elif _option_values(wave.argv, "--evidence-limit"):
            raise ValueError("edge-only wave cannot carry an inferred evidence limit")
        if _option_values(wave.argv, "--chunk-size") != [str(MAX_ROWS_PER_WAVE)]:
            raise ValueError("relation argv chunk size differs from the reviewed bound")
        if _option_values(wave.argv, "--max-chunks") != [str(MAX_CHUNKS_PER_WAVE)]:
            raise ValueError("relation argv max-chunks differs from the reviewed bound")

    bounded_options = ("--max-rows", "--edge-limit", "--evidence-limit", "--chunk-size", "--max-chunks")
    seen_bound = False
    for option in bounded_options:
        for value in _option_values(wave.argv, option):
            seen_bound = True
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError(f"non-integer bound for {option}") from exc
            if parsed <= 0:
                raise ValueError(f"{option} must be positive; zero is unbounded")
    if not seen_bound:
        raise ValueError("wave command has no explicit finite row/chunk bound")

    if not wave.verification_argvs:
        raise ValueError("wave requires selected-live verification commands")
    expected_verification = tuple(arg for arg in wave.argv if arg != "--write")
    for command in wave.verification_argvs:
        _validate_argv_array(command, verification=True)
        if command != expected_verification:
            raise ValueError("verification argv must exactly mirror the bounded write selection")
        if command[:6] != expected_prefix or "--write" in command:
            raise ValueError("verification must use the same approved adapter in read-only mode")
        if _option_values(command, "--lamin-instance") != [EXPECTED_INSTANCE]:
            raise ValueError("verification must target the exact accepted Lamin instance")
        if not all(command.count(name) == 1 for name in wave.allowlist):
            raise ValueError("verification command allowlist does not match the wave")
    if wave.max_retries < 0 or wave.max_retries > MAX_RETRIES:
        raise ValueError("automatic retries are limited to at most two")
    if not isinstance(wave.bounds, WaveBounds):
        raise ValueError("wave bounds must include finite row, chunk, runtime, and resource limits")
    if not 0 < wave.bounds.max_rows <= MAX_ROWS_PER_WAVE:
        raise ValueError("max_rows is unbounded or exceeds the code-only gate")
    if not 0 < wave.bounds.max_chunks <= MAX_CHUNKS_PER_WAVE:
        raise ValueError("max_chunks is unbounded or exceeds the code-only gate")
    if not 0 < wave.bounds.max_runtime_seconds <= MAX_RUNTIME_SECONDS:
        raise ValueError("runtime is unbounded or exceeds the code-only gate")
    if wave.bounds.resources.cpu_cores <= 0 or wave.bounds.resources.memory_bytes <= 0:
        raise ValueError("resource bounds must be positive")
    paths = (wave.progress_path, wave.ack_path, wave.ledger_path)
    if not all(path.is_absolute() for path in paths) or len(set(paths)) != len(paths):
        raise ValueError("progress, ack, and ledger paths must be distinct absolute paths")
    if wave.stop_criteria != StopCriteria(0, True, True):
        raise ValueError("wave stop criteria must fail closed on verification or durability")
    if not (
        len(wave.start_checkpoints)
        == len(wave.end_checkpoints)
        == len(wave.lane_keys)
    ):
        raise ValueError("checkpoint cardinality mismatch")
    for start, end in zip(wave.start_checkpoints, wave.end_checkpoints, strict=True):
        if start < 0 or end <= start or end - start > wave.bounds.max_rows:
            raise ValueError("wave checkpoint window is invalid or unbounded")


@contextlib.contextmanager
def issue_writer_capability(
    plan: WavePlan,
    *,
    ttl_seconds: float,
    now: float | None = None,
) -> Iterator[WriterCapability]:
    if ttl_seconds <= 0:
        raise ValueError("writer capability TTL must be positive")
    if _ACTIVE_CAPABILITIES:
        raise RuntimeError("one logical writer capability is already active")
    issued_at = time.time() if now is None else float(now)
    token = secrets.token_urlsafe(32)
    capability = WriterCapability(token, plan.digest, issued_at + ttl_seconds)
    _ACTIVE_CAPABILITIES[token] = (plan.digest, capability.expires_at)
    try:
        yield capability
    finally:
        _ACTIVE_CAPABILITIES.pop(token, None)


def run_wave(
    wave: WaveSpec,
    *,
    plan: WavePlan,
    capability: WriterCapability,
    executor: Callable[..., ExecutionResult],
    now: float | None = None,
    hostname: str | None = None,
) -> ExecutionResult:
    current_time = time.time() if now is None else float(now)
    registered = _ACTIVE_CAPABILITIES.get(capability.token)
    if registered != (capability.plan_digest, capability.expires_at):
        raise RuntimeError("forged or revoked writer capability")
    if capability.plan_digest != plan.digest:
        raise RuntimeError("writer capability belongs to a different plan")
    if current_time >= capability.expires_at:
        raise RuntimeError("stale writer capability")
    if wave not in plan.waves:
        raise RuntimeError("wave is not part of the capability-gated plan")
    validate_wave_spec(wave)
    actual_host = (socket.gethostname() if hostname is None else hostname).split(".", 1)[0]
    if actual_host != wave.execution_host:
        raise RuntimeError(
            f"refusing heavy wave on {actual_host!r}; required host is {wave.execution_host!r}"
        )

    result = ExecutionResult(returncode=1, summary={"status": "not_started"})
    for _attempt in range(wave.max_retries + 1):
        result = executor(wave.argv, timeout=wave.bounds.max_runtime_seconds)
        if result.returncode == 0:
            break
    return result


class _DirectoryHandle:
    def __init__(self, path: Path) -> None:
        self._fd = os.open(path, os.O_RDONLY)

    def flush(self) -> None:
        return None

    def fileno(self) -> int:
        return self._fd

    def close(self) -> None:
        os.close(self._fd)


class DurableWaveLedger:
    """Persist a verified subchunk with progress -> fsync -> ack -> checkpoint ordering."""

    def __init__(self, wave: WaveSpec) -> None:
        validate_wave_spec(wave)
        self.wave = wave
        self.started_monotonic = time.monotonic()

    def _fsync(self, handle: Any, label: str) -> None:
        del label
        handle.flush()
        os.fsync(handle.fileno())

    def _previous_cursors(self) -> tuple[int, int]:
        edge_start = 0
        evidence_start = 0
        for lane_key, start in zip(
            self.wave.lane_keys,
            self.wave.start_checkpoints,
            strict=True,
        ):
            if lane_key.startswith("edge:"):
                edge_start = start
            elif lane_key.startswith("evidence:"):
                evidence_start = start
        if self.wave.ledger_path.exists():
            payload = json.loads(self.wave.ledger_path.read_text(encoding="utf-8"))
            edge_start = int(payload.get("durable_edge_current_offset", edge_start))
            evidence_start = int(payload.get("durable_evidence_current_offset", evidence_start))
        return edge_start, evidence_start

    def commit_verified(
        self,
        *,
        edge_cursor: int,
        evidence_cursor: int,
        edge_attempted: int,
        evidence_attempted: int,
        selected_live_edges: int,
        selected_live_evidence: int,
        mismatch_count: int,
    ) -> dict[str, Any]:
        previous_edge, previous_evidence = self._previous_cursors()
        has_edge = any(key.startswith("edge:") for key in self.wave.lane_keys)
        has_evidence = any(key.startswith("evidence:") for key in self.wave.lane_keys)
        if edge_attempted < 0 or evidence_attempted < 0:
            raise RuntimeError("verification requires non-negative attempted rows")
        for lane_key, end in zip(
            self.wave.lane_keys,
            self.wave.end_checkpoints,
            strict=True,
        ):
            cursor = edge_cursor if lane_key.startswith("edge:") else evidence_cursor
            if cursor > end:
                raise RuntimeError("verified cursor exceeds the bounded wave checkpoint")
        if has_edge and edge_cursor - previous_edge != edge_attempted:
            raise RuntimeError("edge cursor does not match the verified source window")
        if has_evidence and evidence_cursor - previous_evidence != evidence_attempted:
            raise RuntimeError("evidence cursor does not match the verified source window")
        if not has_edge and (edge_attempted or selected_live_edges):
            raise RuntimeError("unexpected edge work for this wave")
        if not has_evidence and (evidence_attempted or selected_live_evidence):
            raise RuntimeError("unexpected evidence work for this wave")
        if (
            mismatch_count != 0
            or selected_live_edges != edge_attempted
            or selected_live_evidence != evidence_attempted
        ):
            raise RuntimeError("selected-live verification failed; checkpoint not advanced")

        elapsed = max(time.monotonic() - self.started_monotonic, 1e-9)
        source_rows = edge_attempted + evidence_attempted
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_bytes = int(usage.ru_maxrss)
        if rss_bytes < 1024**2:  # Linux reports KiB; macOS reports bytes.
            rss_bytes *= 1024
        for path in (self.wave.progress_path, self.wave.ack_path, self.wave.ledger_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        disk_free = shutil.disk_usage(self.wave.ledger_path.parent.parent).free
        timestamp = _utc_now()
        current_offsets = []
        if has_edge:
            current_offsets.append(edge_cursor)
        if has_evidence:
            current_offsets.append(evidence_cursor)
        current_offset = min(current_offsets)
        record = {
            "event": "subchunk_verified",
            "wave_id": self.wave.wave_id,
            "lane_keys": list(self.wave.lane_keys),
            "source_rows_read": source_rows,
            "edge_rows_attempted": edge_attempted,
            "edge_rows_upserted": edge_attempted,
            "evidence_rows_attempted": evidence_attempted,
            "evidence_rows_upserted": evidence_attempted,
            "selected_live_edges_found": selected_live_edges,
            "selected_live_evidence_found": selected_live_evidence,
            "source_live_mismatch_count": mismatch_count,
            "durable_edge_current_offset": edge_cursor if has_edge else None,
            "durable_evidence_current_offset": evidence_cursor if has_evidence else None,
            "current_offset": current_offset,
            "elapsed_seconds": elapsed,
            "throughput_rows_per_second": source_rows / elapsed,
            "rss_bytes": rss_bytes,
            "disk_free_bytes": disk_free,
            "iowait_seconds": 0.0,
            "last_progress_at": timestamp,
            "status": "verified_pending_ack",
        }
        progress_bytes = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")

        with self.wave.progress_path.open("ab") as handle:
            handle.write(progress_bytes)
            handle.flush()
            self._fsync(handle, "progress")

        ack = {
            "wave_id": self.wave.wave_id,
            "progress_path": str(self.wave.progress_path),
            "record_sha256": hashlib.sha256(progress_bytes).hexdigest(),
            "acknowledged_at": _utc_now(),
        }
        with self.wave.ack_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(ack, sort_keys=True) + "\n")
            handle.flush()
            self._fsync(handle, "ack")

        checkpoint = {
            **record,
            "status": "complete",
            "ack_record_sha256": ack["record_sha256"],
            "acknowledged_at": ack["acknowledged_at"],
        }
        temp_path = self.wave.ledger_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(checkpoint, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            self._fsync(handle, "ledger")
        os.replace(temp_path, self.wave.ledger_path)
        directory_handle = _DirectoryHandle(self.wave.ledger_path.parent)
        try:
            self._fsync(directory_handle, "ledger_dir")
        finally:
            directory_handle.close()
        return checkpoint


def plan_to_dict(plan: WavePlan) -> dict[str, Any]:
    return {
        "manifest_sha256": plan.manifest_sha256,
        "manifest_lane_count": plan.manifest_lane_count,
        "planned_lane_count": sum(len(wave.lane_keys) for wave in plan.waves),
        "zero_no_work_count": len(plan.zero_no_work),
        "negative_no_work_count": len(plan.negative_no_work),
        "zero_no_work": dict(sorted(plan.zero_no_work.items())),
        "negative_no_work": dict(sorted(plan.negative_no_work.items())),
        "digest": plan.digest,
        "waves": [_wave_to_dict(wave) for wave in plan.waves],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Exact accepted 72-lane delta manifest JSON")
    parser.add_argument(
        "--artifact-root",
        required=True,
        help="Absolute/task-local root for progress, ack, and checkpoint files",
    )
    parser.add_argument("--output", required=True, help="Write deterministic wave plan JSON here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = load_accepted_manifest(args.manifest)
    plan = plan_waves(rows, artifact_root=args.artifact_root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan_to_dict(plan), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
