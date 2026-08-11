# Inferred edges policy

Generated for Kanban task `t_f0ad9dff` on 2026-06-23.

Source of truth used for this policy:

- relation coverage: `docs/relation_coverage_current.md`
- schema overview: `docs/kg_schema_overview.md`
- historical audit root: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2` (read-only historical snapshot; current canonical root is `gs://jouvencekb/main`)
- bounded audit prototype: `scripts/audit_inferred_edges_candidates.py`
- bounded audit output: `artifacts/reports/t_f0ad9dff_inferred_edge_candidates.json`

This document defines candidate-generation policy only. It does **not** authorize promoting inferred links into canonical observed `edges/` files.

## Core distinction: observed vs inferred

Canonical observed edges are graph assertions supported by a source-native relation or by an already accepted canonical builder policy. They live under `main/edges/{relation}.parquet`; when source provenance exists, support lives under `main/evidence/{relation}.parquet`.

Inferred edges are second-order hypotheses generated from existing graph paths. They may be useful for retrieval, prioritization, ablation features, GNN message-passing variants, or candidate review queues, but they are not source-native observations. They must remain separable from canonical observed edges and must carry their derivation path as evidence.

Practical rule:

- observed edge: source says `x relation y`, or an accepted source-native builder deduplicates that assertion;
- inferred edge: KG contains a path `x -> ... -> y` from which we hypothesize `x relation y`;
- inferred edge must never silently masquerade as observed evidence.

## Confidence labels

Use labels at edge-candidate level, not relation-family level. A template can produce different labels depending on evidence details.

| Label | Meaning | Allowed use |
| --- | --- | --- |
| `inferred_obvious` | The path strongly entails an endpoint-level biological relation under an explicit policy, and every support step has high-quality evidence. Even here, it remains inferred. | Candidate review queue; optional inferred-edge ablation. Not canonical observed promotion. |
| `inferred_weak` | The path is biologically plausible but non-entailing, many-to-many, sign-ambiguous, source-mixed, or likely confounded. | Ranking/retrieval feature, hypothesis generation, negative-control comparisons. |
| `do_not_infer` | The path is too generic, transitive closure is semantically invalid, endpoint projection is forbidden, or leakage/confounding risk dominates. | Do not create inferred edge rows; at most use as analysis context outside KG edge exports. |

Recommended row fields for any stored inferred edge:

```text
x_id, x_type, y_id, y_type,
relation, display_relation,
inference_label,
inference_template_id,
inference_template_version,
support_edge_ids_or_hashes,
support_relations,
support_count,
support_sources,
support_min_credibility,
derivation_query_hash,
canonical_observed_overlap,
created_at,
kg_snapshot_id
```

If full edge IDs are not available yet, store deterministic hashes over `(relation, x_id, y_id, source/evidence ids)` plus enough path columns to reproduce the candidate.

## Storage model

Preferred storage for build/test:

```text
main/edges_inferred/{relation}/{template_id}.parquet
main/evidence_inferred/{relation}/{template_id}.parquet
```

or, for staged local work:

```text
artifacts/staged/<task-id>/edges_inferred/{relation}/{template_id}.parquet
artifacts/staged/<task-id>/evidence_inferred/{relation}/{template_id}.parquet
```

Do **not** write inferred rows into:

```text
main/edges/{relation}.parquet
main/evidence/{relation}.parquet
```

until there is an explicit, reviewed canonical-ingestion policy proving the rows are source-backed observed assertions rather than graph-derived hypotheses. Even if such a policy exists later, preserve inferred lineage separately so GNN experiments can exclude or include inferred links intentionally.

A relation-level `source = inferred` flag inside canonical `edges/{relation}.parquet` is not preferred because it makes accidental train/eval leakage easy. If a unified edge export is needed for a specific experiment, build it as an export artifact with manifest fields indicating `include_observed`, `include_inferred`, template IDs, and KG snapshot.

## Leakage risks for GNN training/evaluation

Inferred edges can leak labels or near-labels when generated from paths that include the target relation family or evaluation endpoints.

High-risk examples:

1. Generating `disease_associated_gene` candidates from `mutation_associated_disease` and `mutation_associated_gene` can leak disease genetics labels into gene-disease prediction tasks.
2. Generating `molecule_treats_disease` from `molecule_targets_gene + disease_associated_gene` can leak disease labels if the downstream task predicts indications and the gene-disease relation is part of the observed training graph.
3. Generating phenotype-mediated gene-disease links from `gene_associated_phenotype + disease_has_phenotype` creates dense generic shortcuts that may inflate disease prediction metrics without adding causal evidence.
4. Ontology transitive closure can create train/test contamination if splits are made after closure rather than before.
5. Any inferred edge created from validation/test target edges, or from evidence derived after the temporal cutoff, invalidates temporal or held-out evaluation.

Required controls for GNN ablations:

- materialize inferred edges after train/validation/test splits only from training-permitted support edges, or build split-specific inferred artifacts;
- record template IDs and support relations in export manifests;
- run ablations with observed-only, inferred-only, and observed+inferred variants;
- exclude inferred edges from the target relation family when evaluating that same family unless the task explicitly tests inference augmentation;
- maintain temporal/source cutoffs where applicable;
- report canonical-observed overlap rates separately from missing-candidate counts.

## Candidate relation-chain templates

### Template A: mutation + disease genetics -> candidate gene-disease

Chain:

```text
mutation_associated_gene(mutation, gene)
+ mutation_associated_disease(mutation, disease)
=> candidate disease_associated_gene(gene, disease)
```

Policy:

- Default label: `inferred_weak`.
- Upgrade only when gene attribution is supported by a reviewed direct coding/pathogenic consequence, exact splice consequence, direct protein change mapped back to the exact gene, colocalized eQTL, or explicit OpenTargets L2G evidence, and disease support has compatible strong clinical/GWAS semantics.
- Simple genomic containment (`mutation_in_gene`), LD alone, nearest-gene assignment, or ambiguous locus-to-gene mapping never supplies C2 eligibility, causal mechanism, effect direction, or sign.
- Keep colocalized-eQTL/explicit-L2G candidates statistical/conditional unless independent mechanistic evidence is also present.
- `do_not_infer` for canonical promotion into `disease_associated_gene`; use as a candidate queue only unless independent gene-disease evidence is later found.

Evidence requirements:

- support mutation ID;
- source/evidence IDs from both mutation-gene and mutation-disease edges;
- score/credibility/statistical fields where available;
- exact attribution family and source assertion: coding/pathogenic, splice, protein change, colocalized eQTL, or explicit L2G; containment-only rows are reported as rejected rather than candidates.

Bounded audit result (`100,000` mutation anchors):

- raw distinct candidate gene-disease pairs: `12,129`
- missing from canonical observed `disease_associated_gene`: `12,123`
- top sampled missing candidates include `ENSG00000148737 -> MONDO:0005148` with `42` supporting mutations.

Recommendation:

- Good first family to build/test, but only as `edges_inferred/disease_associated_gene/mutation_gene_disease.parquet`, not canonical observed edges.
- Before full build, require reviewed consequence/splice/colocalized-eQTL/explicit-L2G support. `mutation_in_gene` containment alone is never accepted C2 support.

### Template B: protein-changing mutation + disease genetics -> candidate protein-disease

Chain:

```text
mutation_causes_protein_change(mutation, protein)
+ mutation_associated_disease(mutation, disease)
=> candidate disease_associated_protein(protein, disease)
```

Policy:

- Default label: `inferred_weak`.
- This is stronger than gene-level L2G when the mutation has a direct ENSP protein-change edge, but it still does not replace protein-native disease evidence.
- Do not infer `disease_associated_protein` from ordinary `disease_associated_gene` or from gene/protein mapping alone. The support path must include direct protein-change evidence.
- Keep separate from staged/direct protein-disease work; direct protein-native source rows should win over inferred candidates.

Evidence requirements:

- support mutation ID;
- amino-acid change / ENSP support;
- mutation-disease source/evidence IDs and scores;
- optional transcript/gene context only as metadata, not as endpoint projection.

Bounded audit result (`100,000` mutation anchors):

- raw distinct candidate protein-disease pairs: `741`
- the original bounded audit predated canonical `disease_associated_protein`; the current flat layout now contains 3,243 observed edges and 35,839 evidence rows documented from PR #44.
- top sampled candidates include `ENSP00000367064 -> Orphanet:35858` with `1,032` supporting mutations.

Recommendation:

- Best first inferred family to build/test if the goal is a compact high-signal inferred layer: it is direct-protein-change anchored, has small candidate volume, and complements the staged-only `disease_associated_protein` lane without pretending to be protein-native observed evidence.

### Template C: target gene + gene-disease -> candidate molecule-disease

Chain:

```text
molecule_targets_gene(molecule, gene)
+ disease_associated_gene(gene, disease)
=> candidate molecule_treats_disease(molecule, disease)
```

Policy:

- Default label: `inferred_weak`.
- This is a repurposing hypothesis, not a treatment assertion.
- Do not infer positive treatment when action type, agonist/antagonist direction, disease mechanism, tissue context, and clinical evidence are missing.
- Never use this template to infer contraindications; positive indication and contraindication are distinct relation semantics.

Evidence requirements:

- target gene support and source/action type from `molecule_targets_gene`;
- gene-disease evidence score/provenance;
- support gene count;
- observed indication overlap flag from `molecule_treats_disease`;
- optional target action sign if available.

Bounded audit result (`5,000` molecule anchors):

- raw distinct candidate molecule-disease pairs: `3,319`
- missing from canonical observed `molecule_treats_disease`: `3,319`
- top sampled missing candidates include multiple molecules to `EFO:0007328` with `78` supporting target genes.

Recommendation:

- Build later as a drug-repurposing candidate layer after Template B. It needs stronger pharmacology filtering before it is useful for GNN training.

### Template D: shared phenotype -> candidate gene-disease

Chain:

```text
gene_associated_phenotype(gene, phenotype)
+ disease_has_phenotype(disease, phenotype)
=> candidate disease_associated_gene(gene, disease)
```

Policy:

- Default label: `do_not_infer`.
- Shared phenotype is a retrieval/ranking feature, not an edge assertion.
- It is too dense and non-specific for an inferred edge layer unless restricted by independent genetic evidence.

Evidence requirements if used as a feature:

- shared phenotype count;
- phenotype specificity/information-content weighting;
- disease/gene phenotype source provenance;
- explicit flag that this is feature context, not edge evidence.

Bounded audit result (unbounded small source tables):

- raw distinct candidate gene-disease pairs: `867,768`
- missing from canonical observed `disease_associated_gene`: `865,738`

Recommendation:

- Do not materialize as inferred edges. Use only as a feature/ranker, and preferably with information-content weighting.

### Template E: pathway membership + disease pathway involvement -> candidate gene-disease

Chain:

```text
pathway_contains_gene(pathway, gene)
+ disease_involves_pathway(pathway, disease)
=> candidate disease_associated_gene(gene, disease)
```

Policy:

- Default label: `inferred_weak` or `do_not_infer` depending on pathway specificity.
- Pathway-level involvement does not entail every member gene is disease-associated.
- Only consider as feature/ranking context unless evidence identifies causal/member subset or perturbation direction.

Evidence requirements:

- pathway ID/name;
- pathway source/provenance;
- disease-pathway evidence score;
- pathway size and gene specificity penalty.

Recommendation:

- Do not build first; pathway size creates high fan-out and likely leakage for disease tasks.

### Template F: enhancer regulation + variant enhancer overlap + variant disease -> candidate gene-disease/regulatory disease mechanism

Chain:

```text
mutation_overlaps_enhancer(mutation, enhancer)
+ enhancer_regulates_gene(enhancer, gene)
+ mutation_associated_disease(mutation, disease)
=> candidate disease_associated_gene(gene, disease)
```

Policy:

- Default label: `do_not_infer` for v1.
- C3 is removed from the active allowlist because the pilot was dominated by contextual fan-out and locus-local path multiplication.
- Retain enhancer overlap and enhancer-gene scores only as source/context features. No candidate edge is generated in v1.
- Reconsideration requires a new reviewed human decision, exact biosample/tissue compatibility, strict path deduplication, and a bounded pilot proving that combinatorial fan-out is controlled.

Recommendation:

- Excluded from v1. Future-only behind a new reviewed decision; do not materialize C3 candidates from the current relations.

### Template G: ontology closure within the same relation family

Examples:

```text
disease_subtype_of_disease(child, parent)
+ molecule_treats_disease(molecule, child)
=> candidate molecule_treats_disease(molecule, parent)
```

```text
phenotype_subtype_of_phenotype(child, parent)
+ disease_has_phenotype(disease, child)
=> candidate disease_has_phenotype(disease, parent)
```

Policy:

- Default label: `inferred_obvious` only for explicitly monotonic ontology semantics and only when relation meaning permits propagation.
- Many biomedical predicates are not safely monotonic. For example, treating a child disease does not always imply treating the parent category in a clinically useful sense.
- Store as ontology-expanded derived views, not as observed edges.

Evidence requirements:

- ontology version;
- closure depth;
- original asserted edge;
- closure path.

Recommendation:

- Useful for ontology-aware retrieval/export, but maintain as separate closure artifacts and split-aware evaluation views.

## Source/evidence requirements by confidence

### `inferred_obvious`

All support edges must have:

- canonical observed support or reviewed staged support;
- source/evidence rows or accepted source-native builder provenance;
- compatible endpoint semantics;
- no forbidden projection, e.g. no RNA/gene projection into protein relation;
- no target-label leakage for the intended evaluation;
- reproducible derivation query and KG snapshot.

### `inferred_weak`

Must have:

- at least two independent support edges or one mechanistic support edge plus one association support edge;
- support count and source list;
- anti-join status against canonical observed edge file if the target relation is canonical;
- explicit label that it is a hypothesis.

### `do_not_infer`

Assign when:

- the chain is generic many-to-many fan-out;
- direction/sign is absent or biologically ambiguous;
- relation semantics are non-transitive;
- endpoint projection violates current KG doctrine;
- support includes staged-only/deferred relations that have not been reviewed;
- the edge would be near-label leakage for the target task.

## Candidate-generation plan

1. Keep a template registry in code/docs with stable IDs, e.g. `mutation_protein_disease_v1`.
2. For each template, write a DuckDB generator that:
   - reads only canonical `main/edges` and approved task-scoped staged inputs;
   - records KG snapshot/root;
   - records support relations and support counts;
   - anti-joins observed canonical target relation when present;
   - writes to `artifacts/staged/<task-id>/edges_inferred/...` first.
3. Add validation:
   - endpoint anti-joins against canonical node tables;
   - support path reproducibility check;
   - observed-overlap count;
   - duplicate check on `(x_id, y_id, relation, template_id)`;
   - leakage report listing target relation and support relations.
4. Use inferred artifacts only in explicit GNN exports with manifest switches.
5. Require reviewer acceptance before copying any inferred layer to a durable `main/edges_inferred/` location.

## First family to build/test

Recommended first build/test: Template B, `mutation_causes_protein_change + mutation_associated_disease => inferred disease_associated_protein`.

Reasons:

- compact candidate volume in the bounded audit (`741` distinct protein-disease pairs from `100,000` mutation anchors);
- directly protein-change anchored, avoiding forbidden gene/RNA-to-protein projection;
- complements but does not replace staged-only protein-native disease association work;
- useful for GNN ablation because it creates a clear inferred layer that can be included/excluded;
- lower fan-out and less generic than phenotype/pathway templates.

Second choice: Template A, but only with reviewed coding/pathogenic, splice, direct protein-change, colocalized-eQTL, or explicit-L2G attribution. Simple `mutation_in_gene` containment is rejected.

Do not build Template D as edges; keep it as a feature/ranking baseline.

## Formal registry result retained from PR #41

The accepted fail-closed run evaluated 24 templates and materialized 701 joined paths. Of those paths, 377 had known pharmacological action and 596 had known disease direction, but 0 had known disease mechanism. It therefore emitted 0 inferred edge rows and 0 inferred evidence rows and created no placeholder Parquet. This is the correct outcome under the operand contract; it must not be reclassified as a missing build or used to justify relaxing mechanism requirements. See `docs/relation-provenance-and-gaps.md`.
