# Relation/evidence terminal backlog

This backlog is derived from the deterministic
[`relation-evidence-ledger.json`](relation-evidence-ledger.json), not from deleted
staging prefixes or dated local audit outputs. Canonical identity comes from the
flat-layout catalogue at `gs://jouvencekb/main`.

Current denominators are `67` active schema relations, `43` canonical edge tables,
`22` canonical evidence tables, `21` canonical edges without matching evidence,
and `24` active schema relations without canonical edge.

## Canonical edges without evidence (21)

Every relation is routed exactly once. Missing evidence is not uniformly a defect.

### Accepted no-evidence structural/ontological (7)

`gene_has_transcript`, `transcript_encodes_protein`, `pathway_child_of_pathway`,
`disease_subtype_of_disease`, `phenotype_subtype_of_phenotype`,
`tissue_subtype_of_tissue`, `organism_has_tissue`.

Terminal route: retain the documented exception. Add evidence only from a
release-pinned source; never create placeholder evidence.

### Evidence backfill, source known (5)

`cell_line_derived_from_tissue`, `disease_has_phenotype`,
`gene_associated_phenotype`, `molecule_in_pathway`, `organism_has_gene`.

Next bounded action: stage evidence against the unchanged canonical edge generation,
then verify relation/endpoint support, source release, mapping and exceptions.

### Provenance recovery required (4)

`molecule_associated_phenotype`, `molecule_contraindicates_disease`,
`molecule_parent_of_molecule`, `molecule_synergizes_molecule`.

These are four of the five legacy molecule `provenance-gap` relations. The fifth,
`molecule_treats_disease`, has 8,285 later evidence rows but its original 14,135-edge
lineage remains unresolved. All five require release-pinned native inputs/checksums,
exact assertions and endpoint mapping/quarantine, immutable producer identity, a
verified rebuild/comparison command, parity/exception accounting and independent
review. See [`relation-provenance-and-gaps.md`](relation-provenance-and-gaps.md).

### Metadata-only, graph-disconnected (2)

`dataset_contains_cell_line`, `dataset_contains_tissue`.

Terminal route: retain as reversible metadata inventory and keep excluded from
default graph training/inference. An evidence file is not required for adjacency
because these relations are not default adjacency.

### Relation-policy decision required (3)

`tissue_expresses_gene`, `cell_type_expresses_gene`,
`cell_line_expresses_gene`.

Next bounded action: decide edge-versus-feature policy and threshold/value retention.
If they remain edges, stage source/value evidence; no RNA-to-protein projection.

## Active relations without canonical edge (24)

No prescribed current source proves an immutable staged object identity for these
relations. Historical row counts alone are labelled
`historical-claim-unverified-no-current-object-identity`; deleted PRISM staging is
`deleted-historical-only`. A future candidate must have a task-scoped immutable URI
or path, generation/checksum, producer commit and validation receipt.

### Source audit / deferred (9)

`enhancer_regulates_transcript`, `cell_line_expresses_protein`,
`pathway_contains_protein`, `molecule_targets_protein`,
`cell_type_found_in_tissue`, `cell_type_involved_in_disease`,
`cell_type_subtype_of_cell_type`, `cell_line_models_disease`,
`cell_line_derived_from_cell_type`.

### Feature/context (2)

`gene_coexpressed_gene`, `disease_comorbid_disease`.

### Schema-only/missing (5)

`cell_type_expresses_protein`, `tf_regulates_gene`,
`transcript_interacts_gene`, `cell_type_responds_to_molecule`,
`phenotype_observed_in_tissue`.

### Metadata-only (5)

`paper_produced_dataset`, `paper_cites_paper`, `dataset_contains_disease`,
`dataset_contains_molecule`, `dataset_contains_cell_type`.

### Explicit policy defer (3)

`tf_binds_enhancer`, `transcript_interacts_protein`,
`cell_line_responds_to_molecule`.

For `cell_line_responds_to_molecule`, PR #15 is historical builder evidence only.
A reprise starts by refetching the five checksum-pinned PRISM 20Q2 files and
producing a new task-scoped candidate; deleted staging is never promotable.

## Candidate/non-active relations

`protein_interacts_with_enhancer` and `protein_interacts_with_transcript` remain
outside `RELATIONS` and outside all denominators. They require explicit source and
endpoint policy before schema extension.

## Promotion gate for future work

1. Build only in task-scoped staging; no placeholder/zero-row canonical tables.
2. Record native source release/checksum and endpoint mapping/quarantine.
3. Validate endpoint anti-joins, duplicate keys and edge/evidence support.
4. Preserve source-specific predicates, scores, assays, context and record IDs.
5. Freeze immutable producer and artifact identities.
6. Require independent review before any canonical write.
7. Regenerate the ledger and require `--check` after catalogue refresh.