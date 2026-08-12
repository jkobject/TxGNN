#!/usr/bin/env python3
"""Build the deterministic active relation/evidence ledger from schema and catalog.

The flat-layout Parquet catalog is the authority for canonical object presence and
identity. Policy classifications below are deliberately explicit and exhaustive:
adding/removing an active schema relation makes generation fail until it is routed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manage_db.kg_schema import CANDIDATE_RELATIONS, RELATIONS

DEFAULT_CATALOG = ROOT / "docs/parquet-catalog/inventory.json"
DEFAULT_JSON = ROOT / "docs/relation-evidence-ledger.json"
DEFAULT_MARKDOWN = ROOT / "docs/relation_coverage_current.md"

PROVENANCE_GAPS = {
    "molecule_associated_phenotype",
    "molecule_contraindicates_disease",
    "molecule_parent_of_molecule",
    "molecule_synergizes_molecule",
    "molecule_treats_disease",
}

NO_EVIDENCE_ROUTES = {
    "accepted-no-evidence-structural/ontological": {
        "gene_has_transcript",
        "transcript_encodes_protein",
        "pathway_child_of_pathway",
        "disease_subtype_of_disease",
        "phenotype_subtype_of_phenotype",
        "tissue_subtype_of_tissue",
        "organism_has_gene",
        "organism_has_tissue",
    },
    "evidence-backfill-source-known": {
        "cell_line_derived_from_tissue",
        "disease_has_phenotype",
        "gene_associated_phenotype",
        "molecule_in_pathway",
    },
    "provenance-recovery-required": {
        "molecule_associated_phenotype",
        "molecule_contraindicates_disease",
        "molecule_parent_of_molecule",
        "molecule_synergizes_molecule",
    },
    "metadata-only-graph-disconnected": {
        "dataset_contains_cell_line",
        "dataset_contains_tissue",
    },
    "relation-policy-decision-required": {
        "cell_line_expresses_gene",
        "cell_type_expresses_gene",
        "tissue_expresses_gene",
    },
}

NONCANONICAL_CLASSIFICATIONS = {
    "source-audit/deferred": {
        "enhancer_regulates_transcript",
        "cell_line_expresses_protein",
        "pathway_contains_protein",
        "molecule_targets_protein",
        "cell_type_found_in_tissue",
        "cell_type_involved_in_disease",
        "cell_type_subtype_of_cell_type",
        "cell_line_models_disease",
        "cell_line_derived_from_cell_type",
    },
    "feature/context": {
        "gene_coexpressed_gene",
        "disease_comorbid_disease",
    },
    "schema-only/missing": {
        "cell_type_expresses_protein",
        "tf_regulates_gene",
        "transcript_interacts_gene",
        "cell_type_responds_to_molecule",
        "phenotype_observed_in_tissue",
    },
    "metadata-only": {
        "paper_produced_dataset",
        "paper_cites_paper",
        "dataset_contains_disease",
        "dataset_contains_molecule",
        "dataset_contains_cell_type",
    },
    "explicit-policy-defer": {
        "tf_binds_enhancer",
        "transcript_interacts_protein",
        "cell_line_responds_to_molecule",
    },
    # No prescribed source proves a current immutable staged object. Historical
    # row counts or deleted prefixes are not sufficient object identity.
    "current-immutable-staged-candidate": set(),
}

SPECIAL_NEXT_ACTIONS = {
    "molecule_associated_phenotype": "Recover the release-pinned constituent file, crosswalk and rejection manifest; build a bounded pair comparison.",
    "molecule_contraindicates_disease": "Recover/select a contraindication-specific source and mapping policy; never reuse positive indication evidence.",
    "molecule_parent_of_molecule": "Recover a release-pinned chemical hierarchy and prove parent orientation and endpoint mapping.",
    "molecule_synergizes_molecule": "Recover exact screen files, score threshold, context and pair-orientation policy before an evidence audit.",
    "molecule_treats_disease": "Partition supported/unsupported edge keys and recover the original indication lineage before replacement.",
    "cell_line_responds_to_molecule": "Refetch the five checksum-pinned PRISM files and create a new task-scoped candidate; deleted staging is not promotable.",
    "organism_has_gene": "Retain the accepted structural/reference exception and record table-level source/release provenance; never fabricate row evidence.",
    "tissue_expresses_gene": "Retain non-zero topology; recover numeric expression and add deterministic source/context-specific low|medium|high quantile bins with exact groups and cutoffs.",
    "cell_type_expresses_gene": "Retain non-zero topology; recover numeric expression and add deterministic source/context-specific low|medium|high quantile bins with exact groups and cutoffs.",
    "cell_line_expresses_gene": "Retain non-zero topology; recover numeric expression and add deterministic source/context-specific low|medium|high quantile bins with exact groups and cutoffs.",
    "tf_regulates_gene": "Keep absent as an observed table; only a reviewed context-compatible tf_binds_enhancer + enhancer_regulates_gene derivation may enter inferred tables with full path evidence.",
}

ROUTE_ACTIONS = {
    "accepted-no-evidence-structural/ontological": "Retain the documented no-evidence exception; add evidence only from a release-pinned source, never fabricate it.",
    "evidence-backfill-source-known": "Stage a source-pinned evidence backfill and verify support against the unchanged canonical edge generation.",
    "provenance-recovery-required": "Recover exact source, mapping/quarantine and producer lineage before any comparison or backfill.",
    "metadata-only-graph-disconnected": "Retain as metadata-only inventory and keep excluded from default training adjacency.",
    "relation-policy-decision-required": "Decide edge-versus-feature policy before any evidence backfill or topology change.",
}

CLASS_ACTIONS = {
    "source-audit/deferred": "Re-audit the named native source and produce a newly identified immutable candidate before review.",
    "feature/context": "Keep outside canonical topology unless a source, threshold and leakage policy is approved.",
    "schema-only/missing": "Select and approve a source-native endpoint/evidence policy before building.",
    "metadata-only": "Keep graph-disconnected as provenance/catalog metadata; do not promote as training adjacency.",
    "explicit-policy-defer": "Keep deferred under the existing policy; any reprise requires a fresh task-scoped artifact and review.",
    "current-immutable-staged-candidate": "Validate the immutable candidate identity and route it through independent promotion review.",
}


def _single_owner_map(groups: dict[str, set[str]], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for owner, names in groups.items():
        for name in names:
            if name in result:
                raise ValueError(f"{name} appears twice in {label}: {result[name]} and {owner}")
            result[name] = owner
    return result


def _catalog_tables(catalog: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    tables = {"edges": {}, "evidence": {}}
    for dataset in catalog["datasets"]:
        layer = dataset.get("layer")
        if layer not in tables:
            continue
        name = dataset["name"]
        if name in tables[layer]:
            raise ValueError(f"duplicate catalog table: {layer}/{name}")
        objects = dataset.get("objects", [])
        if len(objects) != 1:
            raise ValueError(f"expected one flat-layout object for {layer}/{name}, got {len(objects)}")
        obj = objects[0]
        tables[layer][name] = {
            "uri": obj["uri"],
            "rows": obj["rows"],
            "generation": obj["generation"],
            "md5_base64": obj.get("md5_base64"),
        }
    return tables


def build_ledger(catalog_path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text())
    tables = _catalog_tables(catalog)
    active_names = [relation.name for relation in RELATIONS]
    if len(active_names) != len(set(active_names)):
        raise ValueError("RELATIONS contains duplicate active relation names")
    if len(active_names) != 67:
        raise ValueError(f"expected 67 active relations, got {len(active_names)}")

    edge_names = set(tables["edges"])
    evidence_names = set(tables["evidence"])
    active_set = set(active_names)
    unknown_edges = edge_names - active_set
    unknown_evidence = evidence_names - active_set
    if unknown_edges or unknown_evidence:
        raise ValueError(
            f"catalog contains non-active relation tables: edges={sorted(unknown_edges)}, "
            f"evidence={sorted(unknown_evidence)}"
        )
    evidence_without_edge = evidence_names - edge_names
    if evidence_without_edge:
        raise ValueError(f"evidence without edge: {sorted(evidence_without_edge)}")

    no_evidence = edge_names - evidence_names
    route_by_relation = _single_owner_map(NO_EVIDENCE_ROUTES, "no-evidence routes")
    if set(route_by_relation) != no_evidence:
        raise ValueError(
            "no-evidence route coverage drift: "
            f"missing={sorted(no_evidence - set(route_by_relation))}, "
            f"extra={sorted(set(route_by_relation) - no_evidence)}"
        )

    noncanonical = active_set - edge_names
    class_by_relation = _single_owner_map(
        NONCANONICAL_CLASSIFICATIONS, "noncanonical classifications"
    )
    if set(class_by_relation) != noncanonical:
        raise ValueError(
            "noncanonical classification drift: "
            f"missing={sorted(noncanonical - set(class_by_relation))}, "
            f"extra={sorted(set(class_by_relation) - noncanonical)}"
        )

    relations = []
    for relation in RELATIONS:
        edge = tables["edges"].get(relation.name)
        evidence = tables["evidence"].get(relation.name)
        no_evidence_route = route_by_relation.get(relation.name)
        noncanonical_class = class_by_relation.get(relation.name)
        if relation.name in PROVENANCE_GAPS:
            provenance_status = "provenance-gap"
            accepted_status = "canonical-present-provenance-unresolved"
        elif edge and evidence:
            provenance_status = "source-backed-evidence-present"
            accepted_status = "canonical-present"
        elif edge:
            provenance_status = no_evidence_route
            accepted_status = (
                "canonical-metadata-only"
                if no_evidence_route == "metadata-only-graph-disconnected"
                else "canonical-present"
            )
        else:
            provenance_status = "not-canonical"
            accepted_status = noncanonical_class

        if edge:
            staged_artifact_status = "not-applicable-canonical"
            default_action = (
                ROUTE_ACTIONS[no_evidence_route]
                if no_evidence_route is not None
                else "Retain canonical objects; rerun source/evidence validation when the source release changes."
            )
            next_action = SPECIAL_NEXT_ACTIONS.get(
                relation.name,
                default_action,
            )
        else:
            assert noncanonical_class is not None
            staged_artifact_status = (
                "deleted-historical-only"
                if relation.name == "cell_line_responds_to_molecule"
                else "historical-claim-unverified-no-current-object-identity"
            )
            next_action = SPECIAL_NEXT_ACTIONS.get(
                relation.name, CLASS_ACTIONS[noncanonical_class]
            )

        relations.append(
            {
                "relation": relation.name,
                "x_type": relation.source.value,
                "y_type": relation.target.value,
                "kind": relation.kind.value,
                "direct": relation.direct,
                "schema_status": relation.status.value,
                "canonical_edge": edge,
                "canonical_evidence": evidence,
                "provenance_status": provenance_status,
                "accepted_status": accepted_status,
                "no_evidence_route": no_evidence_route,
                "noncanonical_classification": noncanonical_class,
                "staged_artifact_status": staged_artifact_status,
                "next_bounded_action": next_action,
            }
        )

    summary = {
        "active_relations": len(active_names),
        "canonical_edge_tables": len(edge_names),
        "canonical_evidence_tables": len(evidence_names),
        "canonical_edges_without_evidence": len(no_evidence),
        "schema_relations_without_canonical_edge": len(noncanonical),
        "evidence_without_edge": len(evidence_without_edge),
        "canonical_edge_rows": sum(x["rows"] for x in tables["edges"].values()),
        "canonical_evidence_rows": sum(x["rows"] for x in tables["evidence"].values()),
        "no_evidence_routes": dict(sorted(Counter(route_by_relation.values()).items())),
        "noncanonical_classifications": dict(
            sorted(Counter(class_by_relation.values()).items())
        ),
        "provenance_gaps": sorted(PROVENANCE_GAPS),
    }
    expected = (67, 43, 22, 21, 24, 0)
    observed = tuple(
        summary[key]
        for key in (
            "active_relations",
            "canonical_edge_tables",
            "canonical_evidence_tables",
            "canonical_edges_without_evidence",
            "schema_relations_without_canonical_edge",
            "evidence_without_edge",
        )
    )
    if observed != expected:
        raise ValueError(f"denominator drift: expected {expected}, got {observed}")

    return {
        "schema_version": "relation-evidence-ledger-v1",
        "catalog_source": str(catalog_path.relative_to(ROOT)),
        "canonical_root": catalog["canonical_root"],
        "catalog_as_of": sorted({d["as_of"] for d in catalog["datasets"]})[-1],
        "summary": summary,
        "relations": relations,
        "candidate_relations": [
            {
                "relation": relation.name,
                "x_type": relation.source.value,
                "y_type": relation.target.value,
                "kind": relation.kind.value,
                "direct": relation.direct,
                "recommendation": relation.recommendation,
            }
            for relation in CANDIDATE_RELATIONS
        ],
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    summary = ledger["summary"]
    lines = [
        "# Current relation/evidence coverage",
        "",
        "This file is generated by `scripts/build_relation_evidence_ledger.py` from",
        "`manage_db/kg_schema.py` and `docs/parquet-catalog/inventory.json`. Run the",
        "generator with `--check` to detect drift. Historical staged row counts are not",
        "current object identities; the ledger labels them accordingly.",
        "",
        "## Exact denominators",
        "",
        f"- Active schema relations: `{summary['active_relations']}`",
        f"- Canonical edge tables: `{summary['canonical_edge_tables']}`",
        f"- Canonical evidence tables: `{summary['canonical_evidence_tables']}`",
        f"- Canonical edge tables without matching evidence: `{summary['canonical_edges_without_evidence']}`",
        f"- Active schema relations without canonical edge: `{summary['schema_relations_without_canonical_edge']}`",
        f"- Evidence tables without canonical edge: `{summary['evidence_without_edge']}`",
        f"- Canonical edge rows: `{summary['canonical_edge_rows']:,}`",
        f"- Canonical evidence rows: `{summary['canonical_evidence_rows']:,}`",
        "",
        "## No-evidence routes",
        "",
    ]
    for route, count in summary["no_evidence_routes"].items():
        names = [
            row["relation"]
            for row in ledger["relations"]
            if row["no_evidence_route"] == route
        ]
        lines.append(f"- `{route}`: `{count}` — " + ", ".join(f"`{name}`" for name in names))
    lines.extend(
        [
            "",
            "The five molecule gaps remain `provenance-gap`. Documentation is complete;",
            "scientific provenance is unresolved until the release-pinned input, exact source",
            "assertion, mapping/quarantine, immutable producer, verified rebuild/comparison,",
            "parity/exception manifest, and independent review all exist. Later support for",
            "`molecule_treats_disease` does not reconstruct its original edge lineage. See",
            "[`relation-provenance-and-gaps.md`](relation-provenance-and-gaps.md).",
            "",
            "## One row per active relation",
            "",
            "| Relation | Endpoints | Edge rows / generation | Evidence rows / generation | Provenance / route | Accepted status | Staged identity | Next bounded action |",
            "| --- | --- | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for row in ledger["relations"]:
        edge = row["canonical_edge"]
        evidence = row["canonical_evidence"]
        edge_text = "—" if edge is None else f"{edge['rows']:,} / `{edge['generation']}`"
        evidence_text = (
            "—" if evidence is None else f"{evidence['rows']:,} / `{evidence['generation']}`"
        )
        route = row["no_evidence_route"] or row["noncanonical_classification"] or "evidence-present"
        lines.append(
            f"| `{row['relation']}` | `{row['x_type']}→{row['y_type']}` | {edge_text} | "
            f"{evidence_text} | `{row['provenance_status']}` / `{route}` | "
            f"`{row['accepted_status']}` | `{row['staged_artifact_status']}` | "
            f"{row['next_bounded_action']} |"
        )
    lines.extend(
        [
            "",
            "## Candidate / non-active relations",
            "",
            "These are not part of the 67-relation denominator.",
            "",
            "| Candidate | Endpoints | Recommendation |",
            "| --- | --- | --- |",
        ]
    )
    for row in ledger["candidate_relations"]:
        lines.append(
            f"| `{row['relation']}` | `{row['x_type']}→{row['y_type']}` | {row['recommendation']} |"
        )
    return "\n".join(lines) + "\n"


def _check_or_write(path: Path, content: str, check: bool) -> None:
    if check:
        if not path.exists() or path.read_text() != content:
            raise SystemExit(f"generated output is stale: {path.relative_to(ROOT)}")
    else:
        path.write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    ledger = build_ledger(args.catalog)
    json_text = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    markdown_text = render_markdown(ledger)
    _check_or_write(args.json_output, json_text, args.check)
    _check_or_write(args.markdown_output, markdown_text, args.check)
    print(json.dumps(ledger["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
