# 04 — Relations

## Current source of truth

- Machine-readable ledger: `docs/relation-evidence-ledger.json`.
- Generated human table: `docs/relation_coverage_current.md`.
- Terminal backlog: `docs/relation_backlog_prioritized.md`.
- Five legacy molecule lineage gaps: `docs/relation-provenance-and-gaps.md`.
- Generator/checker: `scripts/build_relation_evidence_ledger.py`.
- Reopened source/recovery freeze: `docs/relation-expansion-source-contract.md`
  and `.json`; checker: `scripts/build_relation_expansion_source_contract.py`.

Current flat-layout catalogue denominator:

- `67` active declared relations;
- `43` canonical edge tables (`103,181,903` rows);
- `22` canonical evidence tables (`78,035,525` rows);
- `21` canonical edge tables without matching evidence;
- `24` active schema relations without canonical edge;
- `0` evidence tables without canonical edge.

The old `40/18/22/27` June denominator and old staging row counts are historical,
not current dispatch truth.

## No-evidence routing

The 21 canonical edge tables without evidence are fully classified:

- accepted no-evidence structural/ontological: `8` (including the accepted
  table-provenance-only `organism_has_gene` structural/reference exception);
- evidence backfill, source known: `4`;
- provenance recovery required: `4`;
- metadata-only, graph-disconnected: `2`;
- relation-policy decision required: `3`.

Missing evidence is not automatically a defect. Do not fabricate evidence for
structural/ontological or graph-disconnected metadata relations.

## Legacy provenance verdict

`molecule_associated_phenotype`, `molecule_contraindicates_disease`,
`molecule_parent_of_molecule`, `molecule_synergizes_molecule`, and the original
edge lineage of `molecule_treats_disease` remain `provenance-gap`. Documentation
is complete; scientific provenance is unresolved. Later evidence for
`molecule_treats_disease` does not reconstruct the original edge build.

PR #44 documents the current source-backed canonical
`disease_associated_protein` lane. PR #15 is a historical PRISM builder reference
only: `cell_line_responds_to_molecule` is noncanonical and its deleted staging is
not promotable. PR #41 remains a valid fail-closed zero-row inferred result and
does not authorize placeholder Parquets.

## Noncanonical active relations

The 24 noncanonical active relations are classified once in the ledger:

- source-audit/deferred: `9`;
- feature/context: `2`;
- schema-only/missing: `5`;
- metadata-only: `5`;
- explicit-policy-defer: `3`;
- current immutable staged candidate proven by prescribed sources: `0`.

Historical staged row counts are not current object identities. Future work must
create a newly identified task-scoped candidate before review or promotion.

## Reopened expansion source freeze

The source/recovery contract now covers all 24 noncanonical active relations,
the five molecule provenance gaps, the three retained expression relations, and
`organism_has_gene`. It preserves ReMap's 1,224,536/6,356,561 bounded staged pilot
without calling the CRM compact sidecar final topology; the deleted PRISM #15
builder/file/checksum/mapping contract; current flat `raw/` Reactome and
Cellosaurus identities; and explicit source/refetch gaps where no lineage is
pinned. Existing non-zero expression topology is retained; future evidence and
features preserve numeric values and deterministic source/context-specific
`low|medium|high` quantiles with exact groups and cutoffs. `tf_regulates_gene`
remains inferred/context-specific only, never an observed source-native table.
The new 31-day GCS soft-delete policy is effective only from
2026-08-12T09:27:50.492Z and is not retroactive; bounded deleted-object probes
found no historical PRISM staging, so its only recovery route is exact Figshare
refetch/checksum verification plus the historical builder.

## Definition of terminal relation work

A relation is terminal only when either canonical-promoted and independently
reviewed, or explicitly accepted as noncanonical/deferred with an honest reason.
Every canonical catalogue refresh must regenerate the ledger and pass its drift,
gap-preservation, stale-root and denominator checks.