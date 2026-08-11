# Relation backlog prioritized

Kanban task: `t_cf77187d`  
Workspace: `/Users/jkobject/.openclaw/workspace/work/txgnn`  
Source of truth consumed: `docs/relation_coverage_current.md` from parent `t_0b1f53d9`, accepted by reviewer `t_23c72d69`.

This is an execution plan for relations that are not fully done after REL-AUDIT. It deliberately avoids one giant ingestion card. Each wave below is source-native, has explicit evidence requirements, and must pass validation before canonical promotion.

## Global promotion doctrine

1. Do not invent placeholder Parquets. A relation with no accepted source-backed rows remains absent from canonical `main/edges` and `main/evidence`.
2. Relation names follow native endpoint and assertion. Evidence-specific predicates, scores, assays, releases, and provenance remain in `evidence/{relation}.parquet` and relation metadata.
3. Do not project gene/RNA rows into protein relations. Protein relations require direct protein/isoform evidence or direct protein measurement.
4. Do not derive `tf_regulates_gene`, `tf_binds_enhancer`, `transcript_interacts_protein`, `transcript_interacts_gene`, or `protein_interacts_protein` from canonical broad `gene_interacts_gene` rows.
5. ReMap all-peak finalization from the old broad run is stopped/deferred, and the already accepted CRM sidecar remains bounded `crm_aggregated_support` QA/support material. New ReMap CRM/peak/motif work should follow `docs/remap_crm_canonical_readiness.md` (`t_f558cee3`): stage `tf_binds_enhancer` edge/evidence candidates with explicit ReMap peak, CRM reconstruction, motif, metadata, and leakage fields before any canonical write.
6. Canonical promotion gate for every batch:
   - build in scratch or staging only;
   - validate x/y endpoint anti-joins against mounted canonical nodes using DuckDB where scale requires it;
   - validate edges-without-evidence and evidence-without-edge are zero when source provenance exists;
   - run `manage_db.audit_edge_evidence` or equivalent targeted support audit;
   - write a promotion report under `docs/` and a machine-readable validation report under `artifacts/reports/<task-id>/`;
   - update `docs/relation_coverage_current.md` or rerun REL-AUDIT after promotion;
   - reviewer approval before canonical writes are treated as done.

## Priority model

Priority is based on:

- P0: staged rows already exist, source-native semantics are clear, evidence exists, relation has high modeling value, and no human policy block remains.
- P1: staged rows exist but promotion needs a semantic decision or a narrower validation gate.
- P2: schema relation is missing/staged-zero/source-audit-only and needs source selection before build.
- P3: feature/context or explicitly deferred families that should not become canonical edges without a new policy decision.

## Wave A — P0/P1 genomic direct bounded rebuild

Policy source: `docs/mutation_genomic_relations_promotion_policy.md`. That policy is stricter than the REL-AUDIT row-count table: the prior staged pilot passed mechanical endpoint/evidence checks but must **not** be promoted as-is because it over-expands broad VEP context into graph edges.

Relations:

| Relation | Source / current artifact | Endpoint type | Schema status | Evidence policy | Validation requirements | Canonical promotion gate |
| --- | --- | --- | --- | --- | --- | --- |
| `mutation_in_gene` | relation-specific canonical promotion by `t_1cfcd48f` from full all-25-part containment-gated candidate `t_2bb8e7de` | `mutation→gene` | active relation, `canonical promoted / review-accepted`, 2,599,525 canonical edges / 2,599,525 evidence rows / 2,599,525 containment-proof rows in `v2/proof`; bounded predecessor `t_5120f845` had 10,852 staged rows; older VEP-only pilot 1,568,719 / 1,568,719 rejected for promotion | physical/genomic containment only; never L2G/GWAS association; require OpenTargets `target.genomicLocation` point-in-gene proof or accepted equivalent; exclude upstream/downstream/intergenic/regulatory-neighborhood VEP target context | post-write canonical validation passed: live endpoint anti-joins 0/0, duplicate edge/evidence/proof keys 0, edge/evidence/proof gaps 0, containment failures 0, leakage rows 0, staged/canonical sha256 matches | accepted by `t_18a346a4` and reconfirmed at unchanged object generations by `t_2d1f767d`; rerun endpoint/evidence/proof audit when upstream source changes |
| `mutation_affects_transcript` | full OpenTargets 26.03 VEP transcript consequence rebuild from `t_f32f1f5b`, canonical-promoted by `t_225ae18c` | `mutation→transcript` | active relation, `canonical promoted` / `review-accepted`, 2,599,922 canonical edges / 2,599,922 evidence rows | transcript-local coding/splice/UTR/intron/exon/NMD/noncoding-transcript consequences only; no upstream/downstream/intergenic context; `isEnsemblCanonical == true` required | post-write canonical validation passed: mutation/transcript endpoint anti-joins 0, duplicate edge keys 0, edge/evidence support gaps 0, disallowed/null SO rows 0, L2G/GWAS leakage 0 | independent review accepted promotion report `docs/mutation_affects_transcript_canonical_promotion_t_225ae18c.md`; rerun validation if upstream source changes |
| `mutation_overlaps_enhancer` | coordinate-only context/support feature; support-gated canonical promotion by `t_00551bc3` from reviewed full candidate `t_73c67c1b` | `mutation→enhancer` | active relation, `canonical promoted / review-accepted`, 1,664,278 canonical edges / 1,664,278 evidence rows; coordinate-only overlap remains `context/support feature-only; not canonical edge`; prior downstream-gated context smoke 1,670,937 / 1,670,937 and `t_0aa76f3b` bounded support-gated edge/evidence pilot 149,107 / 149,107 remain historical pilots | coordinate overlap alone is contextual, not causal; externally supported overlap may be staged or promoted only when support comes from eQTL, GWAS/L2G, ClinVar/OpenTargets variant disease/gene evidence, MPRA, allele-specific regulatory evidence, or similar sources and is preserved in evidence rows; downstream disease/gene support is not by itself proof of enhancer perturbation | post-write canonical validation passed for the reviewed support-gated candidate: live mutation/enhancer endpoint anti-joins 0/0, duplicate/gap checks 0, staged/canonical SHA256 parity, support-gate audit, and targeted edge/evidence audit | accepted by `t_d11a3bb7` and reconfirmed at unchanged object generations by `t_2d1f767d`; rerun endpoint/evidence/support audit when upstream support or enhancer interval sources change; do not promote raw coordinate-overlap rows |

Rationale: high-value relation family, but existing broad pilots remain policy-disqualified for direct canonical promotion. `mutation_affects_transcript`, containment-gated `mutation_in_gene`, and support-gated `mutation_overlaps_enhancer` are independently review-accepted for their exact promoted revisions; coordinate-overlap-only rows remain contextual/support-only.

Child pipeline created from this plan: builder → tester → reviewer.

## Wave B — P0 protein-native and pharmacology mechanism staged promotion

Relations:

| Relation | Source / current artifact | Endpoint type | Schema status | Evidence policy | Validation requirements | Canonical promotion gate |
| --- | --- | --- | --- | --- | --- | --- |
| `pathway_contains_protein` | Reactome UniProt2Reactome staged pilot (`docs/reactome_pathway_contains_protein_staged_pilot.md`) | `pathway→protein` | active relation, `staged-only/deferred`, 15,436 edges / 18,068 evidence rows | direct UniProt/protein pathway membership only; preserve pathway release/subdatabase/membership evidence | pathway/protein anti-joins; all-level pathway semantic decision; no expansion from gene pathway memberships | promote only after all-level-vs-leaf pathway semantics are documented and accepted |
| `molecule_targets_protein` | ChEMBL protein-native staged pilot (`docs/source_native_molecule_targets_protein_chembl_pilot.md`) | `molecule→protein` | active relation, `staged-only/deferred`, 2,119 / 2,132 | direct protein/isoform target endpoints only; preserve action/mechanism/source record/confidence | molecule/protein anti-joins; action type distribution; no projection from existing `molecule_targets_gene` | promote when evidence support and endpoint anti-joins pass and stale gene-level source tokens remain absent |
| `disease_associated_protein` | protein-native disease-association staged pilot | `protein→disease` | active relation, `staged-only/deferred`, 3,243 / 35,839 | protein-specific causal/directed disease evidence only; no inference from `disease_associated_gene` | protein/disease anti-joins; evidence rows preserve predicate/measurement/source/score; many-evidence-per-edge support audit | promote only if source-specific protein evidence is documented and relation direction remains `protein→disease` |
| `protein_interacts_protein` HCI weighted support | HCI/humanPPI HCI90 policy subset (`docs/hci_ppi_isoform_policy_candidate_t_64ffe8a1.md`) | `protein→protein` | canonical BioGRID remains present; HCI is `staged-only/review-required`, 769 edges / 769 evidence rows | computational predicted physical/structural PPI support only; preserve RF2-PPI/AF2/AFM probabilities, expected precision tier, source database support, and UniProt provenance; lower credibility than BioGRID/IntAct experimental evidence | endpoint anti-joins pass for conservative UniProt→single-ENSP subset; 70 overlap current canonical BioGRID; multi-isoform/missing endpoints excluded pending reviewed canonicalization; leakage caveat for STRING/database-support fields | no canonical promotion until isoform/canonicalization policy, overlap/evidence merge policy, and leakage handling are reviewed |

Rationale: source-native protein endpoints are central to the KG's expanded biomedical mechanism layer and are small enough for fast targeted QA. Keep current canonical BioGRID `protein_interacts_protein` readback as the validated baseline; HCI/humanPPI remains staged-only computational weighted support until reviewed canonicalization/leakage policy exists, and PTM/complex decomposition remains separate/future unless schema changes add PTM/complex nodes.

Child pipeline created from this plan: builder → tester → reviewer.

## Wave C — P0/P1 experimental pharmacology and cell-line context staged promotion

Relations:

| Relation | Source / current artifact | Endpoint type | Schema status | Evidence policy | Validation requirements | Canonical promotion gate |
| --- | --- | --- | --- | --- | --- | --- |
| `cell_line_gene_essentiality` | staged DepMap/Project Score essentiality pilot | `cell_line→gene` | active relation, `staged-only/deferred`, 1,433,992 / 1,433,992 | dependency/essentiality measurement; preserve score/effect/study/threshold in evidence | cell line/gene anti-joins; score/effect distribution sanity; threshold and sign documented | promote when threshold policy is explicit and evidence support is complete |
| `cell_line_responds_to_molecule` | historical GDSC/PRISM viability lanes; PR #15 PRISM 20Q2 builder is preserved only at exact head `3d65b66e15df03abb8c08e08de6e127134d31bcc` and its old staging was deleted | `cell_line→molecule` | active relation, non-canonical / deferred; no current immutable PRISM 20Q2 candidate | direct drug-screen response/viability only; preserve every qualifying source curve plus study, assay, dose/response/effect | fresh source checksums; exact ACH and unique InChIKey mappings; endpoint/evidence/pooling-context/determinism gates | future reprise requires a newly versioned task-local candidate and review; historical staging is not promotable |
| `cell_line_expresses_protein` | staged direct cell-line proteomics pilot | `cell_line→protein` | active relation, `staged-only/deferred`, 3,083 / 3,090 | direct proteomics only; no RNA projection | cell line/protein anti-joins; evidence provenance; no mRNA-derived rows | promote only if source is direct protein measurement and missing 7 evidence-edge discrepancy is explained/fixed |
| `cell_type_found_in_tissue` | staged Cell Ontology/UBERON | `cell_type→tissue` | active relation, `staged-only/deferred`, 958 / 958 | ontology/anatomy mapping evidence, not expression inference | cell type/tissue anti-joins; provenance/source ontology release | may be promoted with Wave D if ontological batch is preferred |

Rationale: high model value for perturbation/pharmacology tasks and mostly staged with evidence. `cell_type_found_in_tissue` is included as a useful context relation but may be moved to Wave D for lower-risk ontology promotion.

Child pipeline created from this plan: builder → tester → reviewer.

## Wave D — P1/P2 ontology, metadata, and literature staged hygiene

Relations:

| Relation | Source / current artifact | Endpoint type | Schema status | Evidence policy | Validation requirements | Canonical promotion gate |
| --- | --- | --- | --- | --- | --- | --- |
| `cell_type_subtype_of_cell_type` | staged Cell Ontology IS-A | `cell_type→cell_type` | active relation, `staged-only/deferred`, 4,526 / 4,526 | ontology hierarchy evidence/release | endpoint anti-joins; acyclicity/self-loop checks; evidence support | promote as low-risk ontology if hierarchy semantics match existing nodes |
| `cell_line_models_disease` | staged curated annotation | `cell_line→disease` | active relation, `staged-only/deferred`, 983 / 1,218 | curated disease model evidence; preserve source/model assertion | endpoint anti-joins; many-evidence support audit; disease mapping provenance | promote when Cellosaurus/source disease mapping policy is accepted |
| `cell_line_derived_from_cell_type` | staged Cellosaurus | `cell_line→cell_type` | active relation, `staged-only/deferred`, 65 / 65 | direct curated derivation only | endpoint anti-joins; evidence support | promote with cell-line context tranche if source release documented |
| `paper_produced_dataset` | staged provenance | `paper→dataset` | active relation, `staged-only/deferred`, 4 / 4 | provenance metadata | endpoint anti-joins; evidence support | promote only if paper and dataset nodes are canonical and durable |
| `paper_cites_paper` | staged citation graph | `paper→paper` | active relation, `staged-only/deferred`, 16 / 16 | citation metadata | endpoint anti-joins; source IDs | low priority unless literature graph is needed downstream |
| `dataset_contains_molecule` | staged measured entity | `dataset→molecule` | active relation, `staged-only/deferred`, 1,000 / 1,000 | dataset membership/provenance | endpoint anti-joins; evidence support | promote only if dataset node policy accepted |
| `dataset_contains_cell_type` | staged measured entity | `dataset→cell_type` | active relation, `staged-only/deferred`, 100 / 100 | dataset membership/provenance | endpoint anti-joins; evidence support | promote only if dataset node policy accepted |
| `dataset_contains_disease` | staged zero-row artifact | `dataset→disease` | active relation, `staged-only/deferred`, 0 / 0 | no placeholder rows | keep absent until source-backed rows exist | no canonical Parquet until non-empty source-backed rows exist |

Rationale: valuable for provenance/context and likely technically easy, but lower modeling priority than genomic/protein/pharmacology relations. Zero-row `dataset_contains_disease` must remain absent from canonical edge/evidence outputs.

## Wave E — canonical edges lacking evidence files or evidence-only updates

These relations already have canonical edge files. They should not block missing-relation promotion, but they need evidence policy/backfill or a decision to treat them as feature/context.

The five legacy molecule relations tracked in `docs/relation-provenance-and-gaps.md` are not generic evidence-backfill chores. They remain `provenance-gap` until release-pinned native inputs, exact endpoint crosswalk/quarantine policy, original producer identity, and a verified comparison command are reviewed together. A migration receipt or later partial evidence file is not sufficient.

| Relation(s) | Current issue | Priority | Required work |
| --- | --- | --- | --- |
| `molecule_synergizes_molecule` | 2,672,628 canonical edges; no current canonical evidence and no current immutable staged backfill; original screen/threshold/pair-orientation lineage is incomplete | P1 provenance recovery | recover exact combination-screen inputs and semantics, then stage a bounded evidence audit; do not promote from deleted/legacy staging |
| `molecule_treats_disease` | 14,135 canonical edges retain an incomplete original TxData lineage; 8,285 later canonical support rows do not reconstruct the original edge build | P1 provenance recovery | partition supported/unsupported edge keys and recover the original indication source before any replacement proposal; never reuse positive evidence for contraindications |
| expression edges: `tissue_expresses_gene`, `cell_type_expresses_gene`, `cell_line_expresses_gene` | canonical edges without evidence file; relation-vs-feature policy still needs confirmation | P1/P2 | decide whether expression remains KG edges or migrates to feature/context; if edges remain, add source/value evidence with thresholds |
| central dogma / ontology / metadata edges (`gene_has_transcript`, `transcript_encodes_protein`, `pathway_child_of_pathway`, `molecule_in_pathway`, `disease_subtype_of_disease`, `disease_has_phenotype`, `phenotype_subtype_of_phenotype`, `tissue_subtype_of_tissue`, `cell_line_derived_from_tissue`, `organism_has_gene`, `organism_has_tissue`, `dataset_contains_cell_line`, `dataset_contains_tissue`, `gene_associated_phenotype`) | canonical edge files lack evidence files | P2 | backfill evidence only where source provenance is available and useful; otherwise document accepted no-evidence exception, never fabricate evidence |
| `molecule_associated_phenotype`, `molecule_parent_of_molecule` | canonical edges lack evidence and exact accepted constituent-source/crosswalk lineage | P2 provenance recovery | recover exact source/release, orientation where applicable, endpoint crosswalk and rejection manifest before deciding rebuild versus documented no-evidence exception |
| `molecule_contraindicates_disease` | 30,675 canonical pairs lack evidence and a contraindication-specific accepted source | P2 source selection | find or recover a contraindication-specific source; do not use positive clinical indication rows |

## Wave F — schema-only or source-audit-only relations needing source selection before build

No builder should create canonical/staged edge Parquets for these without an accepted source and endpoint policy first.

| Relation | Current status | Required source-native decision before build |
| --- | --- | --- |
| `tf_regulates_gene` | `schema-only/missing` | choose a source with explicit TF→target regulation, direction/sign/effect/assay; current policy says do not populate for now |
| `cell_type_expresses_protein` | `schema-only/missing` | direct HPA/cell-type protein staining or abundance table; no RNA projection |
| `transcript_interacts_gene` | `schema-only/missing` | source-native RNA/transcript→gene regulatory/mechanism assertions; no ceRNA/correlation/disease-association edges |
| `cell_type_responds_to_molecule` | `schema-only/missing` | concrete single-cell drug perturbation source and response score policy |
| `disease_manifests_in_tissue` | `canonical promoted / review-accepted` by `t_efac22a4`, reconfirmed by `t_2d1f767d`: 19 canonical edges / 29 evidence rows from the approved bounded HPA/TCGA candidate | keep the relation scoped to cancer-context-specific HPA Pathology Atlas / TCGA cancer prognostics semantics, not a broad all-disease pathology graph; rerun validation if source mappings change |
| `phenotype_observed_in_tissue` | `schema-only/missing`; `t_badd3e1e` source audit emitted 0 staged rows | directed tissue manifestation context with phenotype observation provenance; HPO/HPOA disease→phenotype plus anatomy-like names remains rejected as fake tissue inference |
| `enhancer_regulates_transcript` | `source-audit-only/deferred` | ENST/TSS-native regulatory source; not enhancer→gene expansion to all transcripts |
| `cell_type_involved_in_disease` | `source-audit-only/deferred`; `t_badd3e1e` source-gap JSON only, no edge file | approved scRNA disease-enrichment source and endpoint policy with CL plus EFO/MONDO endpoints, statistics, provenance, and leakage policy |

## Wave G — keep as feature/context unless policy changes

| Relation | Decision |
| --- | --- |
| `gene_coexpressed_gene` | `t_badd3e1e` recommendation: `defer`; keep as feature/context unless a concrete sparse coexpression network edge policy is approved, including source, context, threshold/top-k, symmetry handling, and leakage guard |
| `disease_comorbid_disease` | `t_badd3e1e` recommendation: `needs_source`; keep as feature/context unless an EHR/co-occurrence source and privacy/provenance policy is approved; do not synthesize from shared annotations/phenotypes/treatments |
| ReMap broad all-peak legacy output | stopped/deferred; do not create canonical promotion cards from the old all-peak output |
| ReMap CRM/peak/motif `tf_binds_enhancer` | user-approved direction is a new bounded staged `tf_binds_enhancer` edge/evidence pilot with ReMap peak fields, CRM reconstructed-support fields, optional motif support, metadata coverage, endpoint/evidence audits, and leakage policy; the existing CRM feature sidecar remains bounded QA/support and must not be silently reinterpreted or overwritten |
| miRNA / mature miRNA / PTM / protein complex candidate families | not active `RELATIONS`; require schema extension and node/relation policy before canonical edge work |

## Wave H — `t_badd3e1e` relation gaps source-audit and bounded prototypes

Report: `docs/relation_gaps_wave_t_badd3e1e.md`. Fresh task-scoped staged artifacts live under `artifacts/staged/t_badd3e1e/`; no canonical Parquets were written.

| Relation | Fresh artifact/counts | Recommendation | Next gate |
| --- | --- | --- | --- |
| `disease_manifests_in_tissue` | canonical promoted by `t_5fe137a0`, 19 edges / 29 evidence rows; endpoint/evidence support pass | `canonical promoted / review-accepted` | accepted only for the narrow HPA/TCGA promotion; no broader relation-gap batch promotion |
| `phenotype_observed_in_tissue` | audited empty staged edge/evidence files; HPO/HPOA/UBERON source audit rows | `needs_source` | select a direct tissue→phenotype observation source; do not derive from disease→phenotype or anatomy-like HP names |
| `disease_comorbid_disease` | audited empty staged edge/evidence files | `needs_source` | select accessible/licensable EHR/co-occurrence source plus privacy/provenance policy |
| `cell_type_involved_in_disease` | `artifacts/staged/t_badd3e1e/cell-type-context-relations/reports/cell_type_involved_in_disease_source_gap.json`; no edge file | `needs_source` | select explicit disease-cell enrichment/annotation source with CL and EFO/MONDO endpoints |
| `gene_coexpressed_gene` | no edge artifact built | `defer` | approve sparse coexpression edge policy first, or keep as feature/context |

## Concrete top-priority child card fan-out

Create the following child pipelines from this REL-PLAN card:

1. Wave A genomic direct staged promotion:
   - accepted baseline: `mutation_affects_transcript`, containment-gated `mutation_in_gene`, and support-gated `mutation_overlaps_enhancer` are canonical promoted/review-accepted for the exact validated revisions.
   - future replacements/extensions: rerun endpoint/evidence/proof/support and semantic leakage checks before writing; coordinate-only `mutation_overlaps_enhancer` remains staged/context/feature.
   - reviewer: require a new immutable revision and independent gate for any future replacement or extension; current acceptance does not authorize raw coordinate-overlap promotion.
2. Wave B protein-native mechanism promotion:
   - builder: prepare promotion candidates for `pathway_contains_protein`, `molecule_targets_protein`, and `disease_associated_protein`.
   - tester: endpoint/evidence anti-join/support QA and no-gene-projection checks.
   - reviewer: accept/reject source-native protein endpoint semantics and canonical promotion.
3. Wave C experimental pharmacology/cell-line context promotion:
   - builder: prepare promotion candidates for `cell_line_gene_essentiality`, `cell_line_responds_to_molecule`, `cell_line_expresses_protein`, optionally `cell_type_found_in_tissue` if kept in this batch.
   - tester: score/effect/evidence/endpoint QA and direct-proteomics checks.
   - reviewer: accept/reject threshold/score direction and direct measurement policy.
4. Wave E evidence-only backfill:
   - builder: evidence-only update for `molecule_synergizes_molecule` and `molecule_treats_disease` staged evidence; produce a separate source selection note for `molecule_contraindicates_disease` instead of fabricating evidence.
   - tester: verify evidence support against existing canonical edges and indication-vs-contraindication separation.
   - reviewer: accept/reject evidence-only canonical update.

Wave D is intentionally not fanned out yet unless the above waves are already staffed; it is lower priority but well-defined. Wave F should fan out first to a source/policy researcher, not a builder. Wave G should not be built without a new human policy decision.
