# Causal semantics as features of existing edges

Status: **authoritative modeling doctrine**

Decision owner: Jérémie Kalfon

Decision date: 2026-07-19

## Decision

Jouvence preserves broad, stable biological relation identities. Causal mechanism, direction of effect, pharmacological action, pathogenicity, response polarity, and experimental context are **typed features of those existing edges**, supported by row-level evidence. They are not separate relation names.

The deterministic machine-readable companion to this doctrine is
[`causal_edge_feature_inventory.json`](causal_edge_feature_inventory.json). It is
the sole current exact-count inventory for this contract; failed-lineage or
task-local inventories are historical evidence, not alternative contracts.

For example, Jouvence keeps:

```text
molecule ─molecule_targets_gene→ gene
gene ─disease_associated_gene→ disease
mutation ─mutation_associated_disease→ disease
mutation ─mutation_affects_molecule_response→ molecule
```

It must not create relation families such as:

```text
molecule_inhibits_gene
gene_gof_causes_disease
gene_lof_causes_disease
mutation_confers_drug_resistance
```

unless the endpoint types or the underlying biological assertion genuinely differ from an existing relation. GoF/LoF, inhibitor/agonist, risk/protection, sensitivity/resistance, and similar qualifiers normally belong in columns and evidence.

## Storage contract

### Edge table

`edges/<relation>.parquet` contains one deduplicated `A → B` graph assertion and compact normalized features needed by graph consumers.

Illustrative row:

| x_id | y_id | relation | causal_mechanisms | mechanism_status | effect_directions | evidence_count |
| --- | --- | --- | --- | --- | --- | ---: |
| `ENSG…` | `MONDO…` | `disease_associated_gene` | `[loss_of_function]` | `consensus` | `[risk]` | 6 |

### Evidence table

`evidence/<relation>.parquet` contains every source assertion separately, including raw values, provenance, study and biological context.

Illustrative rows:

| edge_key | causal_mechanism | effect_direction | inheritance_mode | source | source_record_id | context |
| --- | --- | --- | --- | --- | --- | --- |
| `…` | `loss_of_function` | `risk` | `recessive` | `ClinGen` | `…` | `…` |
| `…` | `gain_of_function` | `risk` | `dominant` | `ClinVar` | `…` | `…` |

High-cardinality raw text, PMIDs, assay records, source payloads, populations, doses, times, and biosample details remain in evidence rather than being duplicated into the edge row.

## Biological assertion versus evidence modality

The relation table represents the accepted biological assertion. The evidence table records how that assertion was observed or derived: RNA assay, proteomics, clinical record, source dataset, sample, threshold, time, and other context. A source modality must not silently redefine the biological meaning of the relation.

In particular, a directly observed protein product is sufficient biological support that its encoding gene is expressed in that context. Therefore:

```text
x_expresses_protein(x, protein)
+ exact protein -> transcript -> gene mapping
=> inferred x_expresses_gene(x, gene)
```

is approved. The derived gene-expression edge must retain `support_mode=protein_product_observed`, the supporting protein/isoform, mapping version, source assertion IDs, and context in `evidence_inferred/`. It must not claim that RNA itself was measured. The converse remains invalid: RNA/gene expression does not guarantee that a particular protein or isoform was produced.

Likewise, an accepted projection from a protein-level disease association to its encoding gene is a biological endpoint projection, while the protein-native assertion remains its evidence:

```text
disease_associated_protein(protein, disease)
+ exact protein -> transcript -> gene mapping
=> inferred disease_associated_gene(gene, disease)
```

The reverse gene-to-protein projection is not automatic because the causal transcript, isoform, or protein product may be unknown.

## Source-native relation identity and direction

Relation direction follows the source-native assertion and the canonical endpoint
types; identifier mappings do not justify aliases or reversed duplicates. A
protein-native disease assertion remains
`disease_associated_protein(protein, disease)`, and an accepted one-way endpoint
projection uses `disease_associated_gene(gene, disease)` while retaining the
protein assertion as derivation evidence.

RNA or gene-level expression uses `x_expresses_gene`; a direct protein or isoform
measurement uses `x_expresses_protein`. A protein-to-gene biological projection
must preserve `support_mode=protein_product_observed` and must not claim an RNA
measurement. Response assertions remain `cell_type_responds_to_molecule` and
`cell_line_responds_to_molecule`. Duplicate spellings or directions for the same
source assertion must be normalized to one canonical relation, not introduced as
aliases.

## Aggregation and conflict policy

An edge may have several evidence rows. Each normalized edge feature must carry an explicit aggregation state:

- `single`: one usable assertion;
- `consensus`: several compatible assertions;
- `conflicting`: incompatible assertions exist;
- `unknown`: no usable assertion is available.

The aggregation enum is exactly `single|consensus|conflicting|unknown`. Null,
empty, or otherwise unusable source values are inputs to aggregation, not a fifth
state; zero usable assertions always maps to `unknown`.

A conflict is data, not missingness. It must remain visible, for example:

```text
causal_mechanisms = [gain_of_function, loss_of_function]
mechanism_status = conflicting
```

Inference and downstream consumers must fail closed on `conflicting` or `unknown` whenever a known sign or mechanism is required. They must never select one source silently.

## Authoritative reproduced inventory

These exact local inventories were independently reproduced before this
consolidation. This documentation-and-validation revision does not reread cloud,
GCS, FUSE, LaminDB, or canonical data.

| Source lane | Existing broad relation | Exact inventory | Causal-feature consequence |
| --- | --- | ---: | --- |
| ChEMBL target | `molecule_targets_protein` | 2,119 edges; 2,132 action-bearing assertions | Action multiplicity requires source-backed normalization; no silent sign selection. |
| UniProt disease | `disease_associated_protein` | 3,243 edges; 35,839 evidence assertions | Category-to-mechanism/direction normalization remains review-required. |
| Transcript consequence | `mutation_affects_transcript` | 2,599,922 rows | Consequence class alone does not establish LoF or GoF. |
| Contained gene | `mutation_in_gene` | 2,599,525 rows | Structural containment supplies no C2 eligibility, sign, direction, or mechanism. |
| Legacy contraindication | `molecule_contraindicates_disease` | 30,675 distinct pairs; 0 evidence assertions | Provenance-free pairs cannot support signed inference or anti-join completeness; exact missing lineage is tracked in `relation-provenance-and-gaps.md`. |

PR #44 subsequently established a recoverable source-backed canonical `disease_associated_protein` lane with 3,243 edges and 35,839 evidence rows in the flat `main` layout. Its scientific limitation is unchanged: 1 edge has known mechanism and none of the 701 joined paths has known disease mechanism.

The JSON companion fixes these values as one authoritative contract. It also
records the remaining unknowns instead of presenting absent source normalization
or provenance as resolved.

## Normalized feature families

The exact enum contract is versioned and must be derived from source-backed assertions. The following fields are the intended core.

### `molecule_targets_gene` / `molecule_targets_protein`

Compact edge features:

```text
action_types
action_direction
target_modulation
action_status
evidence_count
```

Candidate normalized values include `inhibitor`, `agonist`, `antagonist`, `blocker`, `degrader`, `activator`, and `binder_unknown_effect`. Raw source action strings remain in evidence.

### `disease_associated_gene` / `disease_associated_protein`

Compact edge features:

```text
causal_mechanisms
mechanism_status
effect_directions
effect_direction_status
inheritance_modes
causal_support_level
evidence_count
```

Candidate mechanism values include `loss_of_function`, `gain_of_function`, `dominant_negative`, `haploinsufficiency`, `dosage_gain`, `hypomorphic`, and `unknown`.

The broad relation may also contain non-causal associations. `causal_support_level` must distinguish causal/mechanistic support from statistical association, biomarker, expression, literature, or model-organism evidence.

### `mutation_associated_disease`

Compact edge features may include:

```text
effect_alleles
beta
odds_ratio
effect_directions
clinical_significance
germline_somatic
association_status
evidence_count
```

Evidence retains study locus, cohort/population, confidence interval, source method, disease-specific assertion, and raw effect estimates.

### `mutation_causes_protein_change` / `mutation_affects_transcript`

Compact edge features may include:

```text
variant_consequence_classes
functional_mechanisms
functional_mechanism_status
transcript_or_isoform_context
evidence_count
```

A consequence class such as `missense`, `stop_gained`, `frameshift`, or splice consequence must not be converted automatically into LoF or GoF. Functional mechanism requires explicit source support.

### `mutation_affects_molecule_response`

Compact edge features may include:

```text
response_categories
response_directions
response_status
disease_context_status
evidence_count
```

Required category separation:

- `efficacy`;
- `toxicity`;
- `dosage`;
- `metabolism_pk`.

Directions may include `sensitive`, `resistant`, `increased_efficacy`, `decreased_efficacy`, `increased_toxicity`, `decreased_exposure`, and `unknown`, subject to a reviewed source normalization policy.

## Inference contract

Inference rules consume normalized edge/evidence features; they do not infer from relation names alone.

### Signed treatment or harm

```text
molecule_targets_gene.action_direction
× disease_associated_gene.causal_mechanism/effect_direction
⇒ inferred molecule_treats_disease or molecule_contraindicates_disease
```

Only compatible, source-backed signs may yield a candidate. Missing or conflicting polarity yields zero.

### Allelic triangulation

```text
drug target action
× explicit variant functional mechanism
× disease-specific effect direction
⇒ inferred signed drug–disease effect
```

Generic amino-acid change, genomic containment, LD alone, or proximity is not a functional sign.

### Pharmacogenomic drug–disease candidate

The requested endpoint remains a direct inferred `molecule → disease` edge. Only efficacy/benefit-compatible evidence with compatible disease context may produce `molecule_treats_disease`. Resistance, toxicity, dosage, pharmacokinetics, missing disease context, or conflicting direction must not be laundered into treatment.

## Current inference scope decisions

- C1 variant–protein–disease remains a staged hypothesis/coverage-repair lane, with direct protein consequence and disease-specific evidence required.
- C2 variant–gene–disease is restricted to direct coding/pathogenic, splice, or colocalized-eQTL/explicit-L2G support. Simple containment, LD-only, or nearest-gene assignment is excluded.
- C3 variant–enhancer–gene–disease is removed entirely from v1.
- H1 signed drug–target–disease and direct pharmacogenomic C5 remain fail-closed until the required edge features are materially present and reviewed.

### Approved relation-composition allowlist

All strong/structural and conditional candidates below are in scope for staged generation. Their epistemic class must be preserved; a conditional candidate must not be relabeled as an observed or certain edge.

1. **Mutation consequence -> gene attribution.** `mutation_affects_transcript + gene_has_transcript` and `mutation_causes_protein_change + transcript_encodes_protein + gene_has_transcript` may support `mutation_associated_gene` with exact transcript/protein/assembly mapping and an explicit attribution feature. `mutation_in_gene` containment alone remains insufficient.
2. **Mutation–disease–phenotype.** The complete triangle is accepted as a coherence feature. `mutation_associated_disease + disease_has_phenotype -> mutation_associated_phenotype` is a conditional downstream candidate only, preserving disease context, penetrance limits, and source independence. Shared phenotype alone must not infer a mutation–disease edge.
3. **Cell-type -> tissue existential expression.** `cell_type_found_in_tissue + cell_type_expresses_gene` may yield inferred `tissue_expresses_gene` meaning that at least one compatible population in the tissue expresses the gene. Evidence must preserve the supporting cell type and context; it is not a claim of a bulk assay.
4. **Protein-changing mutation -> disease/phenotype endpoints.** A disease- or phenotype-associated mutation with an exact protein consequence may generate conditional protein/gene–disease or gene–phenotype candidates. Pathogenicity, isoform, assembly, and disease/phenotype context determine strength.
5. **Protein expression -> gene expression.** `x_expresses_protein + exact protein-to-gene mapping -> inferred x_expresses_gene` is approved as a biological implication. Protein observation is evidence; no RNA measurement is asserted. The reverse is not approved.
6. **Protein–disease -> gene–disease.** `disease_associated_protein + exact protein-to-gene mapping -> inferred disease_associated_gene` is approved. The reverse remains conditional and requires protein/isoform-specific support.
7. **Pathway triangles.** Gene/protein disease association plus pathway membership certainly supports a derived “pathway contains an associated member” feature. It may support a conditional pathway–disease candidate only with specificity, multiple independent members or pathway-native evidence, and a circularity check. A disease pathway does not imply association of every member.
8. **Disease–phenotype–tissue.** Two sides may generate only a conditional localization candidate; the complete triangle is accepted as a coherence feature. Preserve anatomical specificity, clinical context, and source independence. Never form a Cartesian product of all disease tissues and phenotypes.
9. **Signed pharmacology and pharmacogenomics.** Signed treatment/harm, allelic triangulation, and efficacy-qualified direct molecule–disease candidates remain approved but fail closed until polarity and context features exist.

The following generic joins remain excluded: gene/RNA expression -> protein expression; shared phenotype -> disease identity; pathway involvement -> every member gene; generic cell/cell-line response plus a molecule-associated phenotype without a matched readout, direction, dose/time, and context.

## Validation requirements

Any enrichment of existing edge/evidence tables must prove:

1. relation names and endpoint identities are unchanged;
2. edge row identity and edge/evidence pairing are conserved;
3. normalized enums are versioned and source-backed;
4. every emitted aggregation status is one of `single`, `consensus`, `conflicting`, or `unknown`, with null/unusable inputs counted under `unknown`;
5. evidence conflicts cannot be overwritten by direct or alias fields;
6. graph loaders remain backward-compatible with optional feature columns;
7. toxicity/PK does not become efficacy, and generic consequence does not become LoF/GoF;
8. outputs are staged and independently reviewed before canonical promotion;
9. inference outputs remain under `edges_inferred/` and `evidence_inferred/`, never observed `edges/`.

## Source priorities

Before rerunning signed inference, prioritize at most three source-native enrichments:

1. pharmacological action/modulation on `molecule_targets_gene/protein`;
2. causal mechanism and disease-direction support on `disease_associated_gene/protein`;
3. effect direction and qualified response on `mutation_associated_disease` and `mutation_affects_molecule_response`.

Candidate sources include OpenTargets action type and direction-of-effect, credible-set effect fields, ClinVar/UniProt variants, ClinGen dosage sensitivity, CIViC, and disease-specific contraindication sources. SIGNOR causalTab may provide directed signed regulatory evidence, but its semantics must still be represented as features/evidence of an approved broad relation rather than relation-name proliferation.

## Status discipline

A documented contract is not a materialized dataset. Use these labels precisely:

- `contract documented`;
- `source fields audited`;
- `staged feature enrichment built`;
- `independently validated`;
- `canonical promoted`;
- `signed inference rerun`.

Do not claim scientific novelty from absence in Jouvence. Anti-join inferred candidates against canonical observed edges, relevant staged source-native lanes, and direct evidence inventories before calling a link missing.
