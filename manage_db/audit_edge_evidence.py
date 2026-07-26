"""Audit evidence/support coverage for canonical TxGNN KG edges."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from manage_db import kg_evidence, kg_storage


@dataclass(frozen=True)
class EvidenceRelationReport:
    relation: str
    edge_rows: int
    evidence_rows: int
    edges_without_evidence: int
    evidence_without_edge: int
    edge_object_exists: bool = True
    evidence_object_exists: bool = True

    @property
    def ok(self) -> bool:
        return (
            self.edge_object_exists
            and self.evidence_object_exists
            and self.edges_without_evidence == 0
            and self.evidence_without_edge == 0
        )


@dataclass(frozen=True)
class EvidenceAudit:
    kg_uri: str
    relation_reports: dict[str, EvidenceRelationReport]
    root_exists: bool = True

    @property
    def ok(self) -> bool:
        return self.root_exists and all(report.ok for report in self.relation_reports.values())


def _edge_keys(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    return set(df["relation"].astype(str) + "|" + df["x_id"].astype(str) + "|" + df["y_id"].astype(str))


def _kg_root_exists(kg_path: str | Path) -> tuple[str, bool]:
    canonical = kg_storage._normalize_uri(str(kg_path))
    fs, path = kg_storage.url_to_fs(canonical)
    return canonical, fs.exists(path.rstrip("/"))


def audit_edge_evidence(
    kg_path: str | Path,
    *,
    relations: list[str] | None = None,
    fail_on_missing: bool = False,
) -> EvidenceAudit:
    """Compare canonical edge rows and evidence rows relation-by-relation."""

    canonical, root_exists = _kg_root_exists(kg_path)
    if fail_on_missing and not root_exists:
        return EvidenceAudit(kg_uri=canonical, relation_reports={}, root_exists=False)

    root = kg_storage.open_kg_root(str(kg_path))
    evidence_relations = set(kg_evidence.list_evidence(root))
    edge_relations = set(root.list_edges())
    selected = set(relations) if relations else evidence_relations | edge_relations

    reports: dict[str, EvidenceRelationReport] = {}
    for relation in sorted(selected):
        edge_keys: set[str] = set()
        evidence_keys: set[str] = set()
        edge_rows = 0
        evidence_rows = 0

        if relation in edge_relations:
            edges = kg_storage.read_edges(root, relation, columns=["relation", "x_id", "y_id"])
            edge_rows = len(edges)
            edge_keys = _edge_keys(edges)
        if relation in evidence_relations:
            evidence = kg_evidence.read_evidence(root, relation, columns=["edge_key", "relation", "x_id", "y_id"])
            evidence_rows = len(evidence)
            evidence_keys = set(evidence["edge_key"].astype(str)) if "edge_key" in evidence else _edge_keys(evidence)

        reports[relation] = EvidenceRelationReport(
            relation=relation,
            edge_rows=edge_rows,
            evidence_rows=evidence_rows,
            edges_without_evidence=len(edge_keys - evidence_keys),
            evidence_without_edge=len(evidence_keys - edge_keys),
            edge_object_exists=relation in edge_relations,
            evidence_object_exists=relation in evidence_relations,
        )

    return EvidenceAudit(kg_uri=root.uri, relation_reports=reports)


def _to_jsonable(audit: EvidenceAudit) -> dict[str, Any]:
    return {
        "kg_uri": audit.kg_uri,
        "ok": audit.ok,
        "root_exists": audit.root_exists,
        "relation_reports": {
            relation: asdict(report) | {"ok": report.ok}
            for relation, report in audit.relation_reports.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Jouvence edge evidence coverage.")
    parser.add_argument("kg_path", help="Path or gs:// URI to a KG root.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--relations",
        nargs="*",
        default=None,
        help="Optional relation names to audit. Defaults to all edge/evidence relations.",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit non-zero if edges lack evidence or evidence lacks a canonical edge.",
    )
    args = parser.parse_args(argv)

    audit = audit_edge_evidence(
        args.kg_path,
        relations=args.relations,
        fail_on_missing=args.fail_on_missing,
    )
    payload = _to_jsonable(audit)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"KG evidence audit: {audit.kg_uri}")
        for relation, report in audit.relation_reports.items():
            missing = []
            if not report.edge_object_exists:
                missing.append("missing_edge_object")
            if not report.evidence_object_exists:
                missing.append("missing_evidence_object")
            missing_suffix = f" {' '.join(missing)}" if missing else ""
            print(
                f"  {relation}: edges={report.edge_rows} evidence={report.evidence_rows} "
                f"edges_without_evidence={report.edges_without_evidence} "
                f"evidence_without_edge={report.evidence_without_edge}{missing_suffix}"
            )
    return 1 if args.fail_on_missing and not audit.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
