"""Rebuild the five legacy molecule provenance-gap lineages from TxGNN kg.csv.

The builder is deliberately task-scoped: it only writes beneath ``--output-dir`` and
never opens the canonical store for mutation. Full replay belongs on txgnn-worker;
small fixture replay is supported locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import urllib.request
import uuid
from dataclasses import dataclass
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


def acquire_source(
    url: str,
    destination: Path,
    *,
    expected_size: int = TXGNN_DATASET["size"],
    expected_md5: str = TXGNN_DATASET["md5"],
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
    canonical_dir: Path | None,
    canonical_manifest: Path | None = None,
    chunksize: int,
) -> None:
    if not fixture:
        if socket.gethostname() != "txgnn-worker":
            raise RuntimeError("full replay must run on txgnn-worker")
        resolved_output = output_dir.resolve(strict=False)
        allowed_root = (Path.cwd() / "artifacts" / "staged" / "t_86299745").resolve(strict=False)
        if not resolved_output.is_relative_to(allowed_root) or resolved_output == allowed_root:
            raise ValueError("full replay output must be under artifacts/staged/t_86299745/")
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
    for chunk in iter_csv(source, chunksize):
        chunks.append(build_candidates(chunk, source_offset_start=source_offset))
        source_offset += len(chunk)
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

    manifest: dict[str, object] = {
        "task_id": "t_86299745",
        "status": "staged-only",
        "canonical_write": False,
        "source_contract": TXGNN_DATASET,
        "source_identity": source_identity,
        "canonical_snapshot_manifest": str(canonical_manifest) if canonical_manifest else None,
        "relations": {
            relation: {
                **SOURCE_ASSERTIONS[relation],
                "canonical_generation": CANONICAL_GENERATIONS[relation],
                "edge_rows": len(combined.edges[relation]),
                "evidence_rows": len(combined.evidence[relation]),
            }
            for relation in SOURCE_ASSERTIONS
        },
        "mapping_quarantine_rows": len(combined.rejections),
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
        (output_dir / "parity_report.json").write_text(json.dumps(parity, indent=2, sort_keys=True) + "\n")
        manifest["parity_report"] = "parity_report.json"

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Already acquired release-pinned TxGNN kg.csv")
    parser.add_argument("--acquire-to", type=Path, help="Create-only acquisition destination for TxGNN kg.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="New absent task-scoped output directory")
    parser.add_argument("--canonical-dir", type=Path, help="Read-only flat canonical snapshot for parity")
    parser.add_argument("--canonical-manifest", type=Path, help="Snapshot identity with exact frozen edge generations")
    parser.add_argument("--fixture", action="store_true", help="Permit a bounded fixture instead of exact source bytes")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args(argv)
    if (args.source is None) == (args.acquire_to is None):
        parser.error("provide exactly one of --source or --acquire-to")
    source = args.source
    if args.acquire_to is not None:
        acquire_source(TXGNN_DATASET["url"], args.acquire_to)
        source = args.acquire_to
    write_replay(
        source,
        args.output_dir,
        fixture=args.fixture,
        canonical_dir=args.canonical_dir,
        canonical_manifest=args.canonical_manifest,
        chunksize=args.chunksize,
    )


if __name__ == "__main__":
    main()
