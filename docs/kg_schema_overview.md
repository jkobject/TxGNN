# TxGNN / Jouvence KG Schema Overview

This document is the readable schema/status overview for the current Jouvence KG. It was refreshed by Kanban task `t_0b1f53d9` from `manage_db/kg_schema.py`, `manage_db/kg_evidence.py`, and canonical FUSE root `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2`.

For the full per-relation next-action table, see `docs/relation_coverage_current.md`. For the exact legacy relation lineage boundary and missing replay proofs, see `docs/relation-provenance-and-gaps.md`.

## Current canonical snapshot

- Canonical KG root audited: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2`
- Node files: `15 / 15`
- Node rows: `55,523,691`
- Declared active relations: `67`
- Canonical edge files: `40 / 67`
- Canonical edge rows: `100,080,390`
- Evidence files: `18`
- Canonical relations with evidence file: `18`
- Declared relations not canonical yet: `27`

Dataset/paper policy note (`t_c07b8b57`, cleanup `t_d97c4547`): existing
`dataset`/`paper` node files and `dataset_contains_*` metadata edge files are
retained in place as metadata-only/non-training inventory after reviewer-accepted
backup gate `t_9ad833bf`. They are disconnected from default
training/inference graph exports; the canonical policy sidecar is
`metadata/dataset_paper_graph_policy_t_d97c4547.{json,md}`.

## Node Schema & GCS Coverage

| Node type | Rows | Present? |
| --- | ---: | --- |
| `paper` | 2,958,199 | yes |
| `gene` | 267,830 | yes |
| `transcript` | 507,365 | yes |
| `protein` | 233,995 | yes |
| `pathway` | 48,575 | yes |
| `molecule` | 31,007 | yes |
| `mutation` | 2,589,509 | yes |
| `disease` | 41,859 | yes |
| `cell_type` | 3,513 | yes |
| `tissue` | 16,061 | yes |
| `phenotype` | 16,449 | yes |
| `cell_line` | 1,183 | yes |
| `organism` | 1 | yes |
| `dataset` | 1 | yes |
| `enhancer` | 48,808,144 | yes |

Planned source-native node families remain non-active until schema extension: `protein_complex`, structured PTM/site/event nodes, and mature/precursor miRNA nodes where the entity is distinct from an existing ENST transcript node.

## Relation status summary

| Bucket | Count | Meaning |
| --- | ---: | --- |
| `canonical+validated` | 37 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `canonical promoted / review-accepted` | 4 | `mutation_affects_transcript`, `mutation_in_gene`, support-gated `mutation_overlaps_enhancer`, and narrowly scoped HPA/TCGA `disease_manifests_in_tissue` are independently accepted; consolidated immutable-generation readback: `t_2d1f767d`. |
| `canonical promoted / review-required` | 0 | No canonical edge relation is awaiting independent acceptance in this snapshot. |
| `canonical with evidence file` | 18 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `canonical without evidence file` | 22 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `staged-only/deferred` | 18 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `source-audit-only/deferred` | 2 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `feature-context-not-edge` | 2 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `schema-only/missing` | 5 | Derived from RELATIONS plus current FUSE/bucket inventory. |
| `intentionally retired active relations` | 0 | None in active RELATIONS; stale/non-active concepts are listed below. |

## Edge schema

All canonical edge Parquet files use at minimum:

```text
x_id, x_type, y_id, y_type, relation, display_relation,
source, credibility, [additional metadata columns...]
```

Evidence/support records live in `evidence/{relation}.parquet`, keyed by relation and edge endpoints, with source-specific fields such as `evidence_type`, `source`, `source_dataset`, `source_record_id`, `paper_id`, `dataset_id`, `study_id`, `evidence_score`, effect/statistical fields, predicate/direction fields, and provenance.

## Modeling decisions that matter for ingestion

- Relation names must match the source-native assertion and endpoint type.
- Gene-level sources stay in gene relations (`molecule_targets_gene`, `gene_interacts_gene`, `pathway_contains_gene`); split to protein/TF/transcript relations only with source-native endpoints/assertions.
- Protein relations require direct protein/isoform evidence or direct protein measurement. Do not project RNA/gene rows into protein edges.
- `tissue_expresses_protein` is direct HPA protein expression/staining and is canonical; `cell_type_expresses_protein` is still not canonical.
- `protein_interacts_protein` is now canonical from source-native IntAct direct PPI; BioGRID physical/PTM/complex subsets remain future decomposition, not a blind merge.
- ReMap `tf_binds_enhancer` edge/evidence is staged-only/deferred and should stay CRM/regulatory-region/support-specific; all-peak or motif-only ReMap is feature/context, not a canonical edge. The full CRM support-only feature/QA sidecar is canonically promoted under `features/remap_crm_tf_enhancer_support_full/` by `t_f2a2952e`, but remains non-topological support material.
- miRNA, lncRNA, RBP, Complex Portal, and PTM work need explicit endpoint/node/event policies before canonical promotion.
- Edges are deduplicated graph assertions; evidence rows carry source predicates, scores, assays, papers, studies, context, and provenance.
- `dataset` and `paper` nodes are disconnected provenance/catalog metadata, not training/inference graph nodes. Keep dataset/paper details in evidence/catalog metadata (`source_dataset`, `dataset_id`, `paper_id`, DOI/PMID/source-record fields, LaminDB artifacts); do not use dataset/paper relations as message-passing adjacency by default.
- Do not create placeholder Parquets just to satisfy schema coverage.

## Current relation coverage table

| Relation | X→Y | Kind | Direct | Status | Edge rows | Evidence rows | Staged edge/evidence rows | Next action | Notes |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| `gene_has_transcript` | `gene→transcript` | `central_dogma` | yes | `canonical+validated` | 507,365 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Transcription |
| `transcript_encodes_protein` | `transcript→protein` | `central_dogma` | yes | `canonical+validated` | 233,995 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Translation |
| `mutation_in_gene` | `mutation→gene` | `genetic` | yes | `canonical promoted / review-accepted` | 2,599,525 | 2,599,525 | -/-; proof rows 2,599,525 in `v2/proof/mutation_in_gene_containment_proof.parquet` | Accepted by `t_18a346a4` and reconfirmed by `t_2d1f767d`; rerun endpoint/evidence/proof audit when upstream source changes. | Physical/genomic containment only; canonical promotion uses OpenTargets 26.03 `target.genomicLocation` point-in-gene proof for every edge, with zero live endpoint anti-joins, duplicate/gap/containment/leakage failures. Do not use broad VEP `targetId` rows or L2G/GWAS sources for this relation. |
| `mutation_associated_gene` | `mutation→gene` | `genetic` | no | `canonical+validated` | 535,093 | 535,093 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Statistical/functional locus-to-gene prediction (for example OpenTargets L2G/GWAS); canonical promoted GWAS/L2G relation with evidence support — evidence rows: 535,093 |
| `mutation_affects_transcript` | `mutation→transcript` | `genetic` | yes | `canonical promoted` | 2,599,922 | 2,599,922 | -/- | Promotion `t_225ae18c` accepted by independent review; rerun endpoint/evidence audit when upstream source changes. | OpenTargets 26.03 VEP transcriptConsequences transcriptId rows after allowed transcript-local SO filtering and `isEnsemblCanonical == true`; canonical mutation/transcript endpoints required. Promotion report: `docs/mutation_affects_transcript_canonical_promotion_t_225ae18c.md`. |
| `mutation_causes_protein_change` | `mutation→protein` | `genetic` | yes | `canonical+validated` | 177,735 | 177,735 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Amino acid change with ENSP protein endpoint; canonical OpenTargets protein-change edge and evidence files exist — evidence rows: 177,735 |
| `mutation_overlaps_enhancer` | `mutation→enhancer` | `genetic` | no | `canonical promoted / review-accepted` | 1,664,278 | 1,664,278 | support/proof sidecars under `v2/metadata/mutation_overlaps_enhancer_*_t_73c67c1b.*` | Accepted by `t_d11a3bb7` and reconfirmed by `t_2d1f767d`; rerun endpoint/evidence/support audit when upstream support or enhancer interval sources change. | Canonical write `t_00551bc3` promoted only the reviewed non-context-support-gated candidate from `t_73c67c1b`; raw coordinate overlap alone remains context/support-only. Relation remains associative/indirect (`direct=False`), with leakage policy in evidence metadata and stronger allele-specific regulatory/enhancer-activity evidence still preferred. |
| `mutation_associated_disease` | `mutation→disease` | `genetic` | no | `canonical+validated` | 4,656,171 | 4,656,171 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | GWAS / ClinVar / OpenTargets known-variant disease association; canonical edge exists, evidence backfill remains next tranche — evidence rows: 4,656,171 |
| `mutation_associated_phenotype` | `mutation→phenotype` | `genetic` | no | `canonical+validated` | 164,406 | 169,005 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | OpenTargets EVA/ClinVar HP-only mutation→phenotype association; include all clinical-significance classes and preserve the exact assertion in edge/evidence metadata rather than restricting the relation to pathogenic/likely pathogenic. — evidence rows: 169,005 |
| `gene_associated_phenotype` | `gene→phenotype` | `phenotype_assoc` | no | `canonical+validated` | 3,330 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Non-causal HPO gene-to-phenotype association; direction is gene→phenotype |
| `mutation_affects_molecule_response` | `mutation→molecule` | `pharmacological` | no | `canonical+validated` | 4,866 | 18,595 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Pharmacogenomics — evidence rows: 18,595 |
| `gene_ortholog_gene` | `gene→gene` | `genetic` | yes | `canonical+validated` | 161,675 | 161,675 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Cross-species orthology — evidence rows: 161,675 |
| `enhancer_regulates_gene` | `enhancer→gene` | `regulatory` | no | `canonical+validated` | 48,808,144 | 48,810,390 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | ENCODE-rE2G composite enhancer-to-gene prediction; preserve biosample, assay feature scores, distance, study, and model score in edge/evidence metadata. — evidence rows: 48,810,390 |
| `enhancer_regulates_transcript` | `enhancer→transcript` | `regulatory` | yes | `source-audit-only/deferred` | - | - | -/- | Source audit exists only; require ENST/TSS-native regulatory source, not enhancer→gene expansion. | transcript-specific/TSS-specific regulation; require a source that directly names ENST/TSS endpoints and is not inferred by expanding enhancer→gene to all transcripts |
| `gene_coexpressed_gene` | `gene→gene` | `expression` | no | `feature-context-not-edge` | - | - | -/- | Keep as feature/context unless a concrete coexpression network edge policy is approved. | Co-expression network |
| `tissue_expresses_gene` | `tissue→gene` | `expression` | yes | `canonical+validated` | 5,338,736 | - | -/- | Canonical expression edge, but evidence file is absent; decide whether expression should remain edge vs feature with provenance. | GTEx / HPA bulk RNA |
| `tissue_expresses_protein` | `tissue→protein` | `expression` | yes | `canonical+validated` | 137,351 | 137,531 | -/- | Canonical direct HPA tissue protein expression; no RNA→protein projection. | Direct Human Protein Atlas tissue protein expression/staining with protein measurement metadata; do not populate from RNA projection. — evidence rows: 137,531; HPA direct protein staining/intensity only; no RNA projection |
| `cell_type_expresses_gene` | `cell_type→gene` | `expression` | yes | `canonical+validated` | 1,561,873 | - | -/- | Canonical expression edge, but evidence file is absent; decide whether expression should remain edge vs feature with provenance. | scRNA-seq (CellxGene) |
| `cell_type_expresses_protein` | `cell_type→protein` | `expression` | yes | `schema-only/missing` | - | - | -/- | Await direct HPA cell-type/staining/protein table decision; do not populate from RNA. | Direct cell-type protein abundance/staining source only; do not populate from RNA projection. — protein expression requires direct protein measurement, not mRNA projection |
| `cell_line_expresses_gene` | `cell_line→gene` | `experimental` | yes | `canonical+validated` | 20,928,056 | - | -/- | Canonical expression edge, but evidence file is absent; decide whether expression should remain edge vs feature with provenance. | RNA-seq (CCLE…) |
| `cell_line_expresses_protein` | `cell_line→protein` | `experimental` | yes | `staged-only/deferred` | - | - | 3,083/3,090 | Review staged cell-line proteomics pilot before promotion. | Direct cell-line proteomics source only; do not populate from mRNA projection. — staged edges/evidence: 3,083/3,090; protein expression requires direct protein measurement, not mRNA projection |
| `cell_line_gene_essentiality` | `cell_line→gene` | `experimental` | no | `staged-only/deferred` | - | - | 1,433,992/1,433,992 | Review staged DepMap/Project Score essentiality pilot before promotion. | DepMap/Project Score/CRISPR gene essentiality or dependency measurement; preserve score/effect/study fields in evidence or feature tables and do not model as protein expression. — staged edges/evidence: 1,433,992/1,433,992 |
| `gene_interacts_gene` | `gene→gene` | `physical` | no | `canonical+validated` | 7,424,037 | 14,336,594 | -/- | Canonical broad gene/gene-product relation remains valid with OpenTargets evidence subset and accepted TxGNN legacy no-fabricated-evidence exception; do not split into protein/TF/transcript from gene endpoints. | Keep broad for current OpenTargets interaction because canonical endpoints are gene-level; preserve source-specific evidence metadata and do not project text_span product IDs into protein/transcript/TF/enhancer relations. — evidence rows: 14,336,594 |
| `tf_regulates_gene` | `gene→gene` | `regulatory` | yes | `schema-only/missing` | - | - | -/- | Pick a concrete source and endpoint/evidence policy before any build. | Transcription-factor gene product regulates target gene expression; require source-native TF/regulator semantics, not from canonical gene_interacts_gene, and preserve direction, sign/effect, assay, source database, score, and record IDs in evidence. |
| `tf_binds_enhancer` | `gene→enhancer` | `regulatory` | yes | `staged-only/deferred`; full support sidecar `canonical promoted` feature/QA-only | - | - | 189,459,767/189,459,767 | Review ReMap CRM/regulatory-region staged bucketed output; do not promote all-peak ReMap or motif-only support as canonical TF→enhancer edges without the approved CRM/endpoint policy. The promoted full sidecar under `features/remap_crm_tf_enhancer_support_full/` is shard-aware support-only material, not edge/evidence. | Transcription-factor gene product binds enhancer/regulatory interval; require source-native enhancer endpoints, not from canonical gene_interacts_gene, and preserve assay/cell context, coordinates, source database, score, and record IDs in evidence. — staged edges/evidence: 189,459,767/189,459,767; ReMap CRM/regulatory-region bucketed staging exists; full CRM support sidecar: 48,768,788 summary rows / 1,179 TF global rows, support-only not canonical edge; all-peak/motif-only ReMap remains feature/context, not canonical edge |
| `transcript_interacts_protein` | `transcript→protein` | `physical` | yes | `staged-only/deferred` | - | - | 0/0 | RBP/RNA CLIP pilot currently has zero accepted rows; next source audit should focus POSTAR/ENCORI/NPInter/RNAInter endpoint IDs and license/access. | RNA/transcript to protein binding or interaction with transcript/protein-native source-native endpoints, not from canonical gene_interacts_gene; preserve interaction assay, source database, score, and record IDs in evidence. — staged edges/evidence: 0/0; RBP/ENCORI pilot staged with 0 accepted rows; lncRNA/RBP sources need endpoint audit |
| `transcript_interacts_gene` | `transcript→gene` | `regulatory` | no | `schema-only/missing` | - | - | -/- | No canonical/staged edge. Use only for source-native RNA/transcript→gene mechanism assertions; do not use ceRNA/expression correlation/disease association as edges. | Transcript/RNA to gene regulatory or interaction assertion when the source names transcript/RNA and gene endpoints; require source-native transcript/RNA assertion, not from canonical gene_interacts_gene, and preserve mechanism, direction, sign/effect, source database, and record IDs in evidence. |
| `protein_interacts_protein` | `protein→protein` | `physical` | yes | `canonical+validated` | 3,550 | 12,288 | -/- | Canonical IntAct direct PPI is now present; keep BioGRID physical/PTM/complex as future source decomposition, not as a blind merge. | Direct protein/isoform interaction only, with source-native protein endpoints plus source database and evidence metadata; not from canonical gene_interacts_gene gene endpoints or text_span projection. — evidence rows: 12,288; canonical source-native IntAct PPI present; BioGRID physical/PTM/complex remains future decomposition |
| `pathway_contains_gene` | `pathway→gene` | `pathway` | no | `canonical+validated` | 630,932 | 630,932 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Reactome / GO — evidence rows: 630,932 |
| `pathway_contains_protein` | `pathway→protein` | `pathway` | no | `staged-only/deferred` | - | - | 15,436/18,068 | Review Reactome UniProt2Reactome staged pilot and decide all-level pathway semantics before promotion. | Protein-native pathway or complex membership source only, with protein endpoints plus source database and evidence metadata. — staged edges/evidence: 15,436/18,068; Reactome protein-native pilot staged; Complex Portal/protein_complex nodes not active yet |
| `pathway_child_of_pathway` | `pathway→pathway` | `ontological` | yes | `canonical+validated` | 147,680 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Reactome hierarchy |
| `molecule_in_pathway` | `molecule→pathway` | `pathway` | no | `canonical+validated` | 1,680 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Metabolic pathway |
| `molecule_targets_gene` | `molecule→gene` | `pharmacological` | yes | `canonical+validated` | 41,239 | 41,239 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Drug/compound target relation for sources whose native target endpoint is a gene or OpenTargets Ensembl target ID; preserve source MoA/action metadata in evidence. — evidence rows: 41,239 |
| `molecule_targets_protein` | `molecule→protein` | `pharmacological` | yes | `staged-only/deferred` | - | - | 2,119/2,132 | Review ChEMBL protein-native staged pilot; do not project existing molecule→gene rows. | Drug/compound target relation for sources that directly identify a protein or isoform endpoint; preserve source database and evidence metadata. — staged edges/evidence: 2,119/2,132; ChEMBL protein-native pilot staged; existing molecule_targets_gene remains gene-level |
| `molecule_treats_disease` | `molecule→disease` | `pharmacological` | no | `canonical present / provenance-gap` | 14,135 | 8,285 | -/- | Retain; recover original edge lineage before replacement. Later canonical evidence is partial support, not full replay proof. | Positive indication only; see `docs/relation-provenance-and-gaps.md`. |
| `molecule_contraindicates_disease` | `molecule→disease` | `pharmacological` | no | `canonical present / provenance-gap` | 30,675 | - | -/- | Recover/select contraindication-specific source and exact mapping policy; never reuse positive indication evidence. | Contraindication. |
| `molecule_synergizes_molecule` | `molecule→molecule` | `pharmacological` | no | `canonical present / provenance-gap` | 2,672,628 | - | -/- | Recover screen release, threshold, context and pair orientation before a bounded evidence audit. | Drug-combination effect; no current immutable evidence backfill. |
| `molecule_parent_of_molecule` | `molecule→molecule` | `ontological` | yes | `canonical present / provenance-gap` | 4,140 | - | -/- | Recover exact hierarchy release, orientation, crosswalk and rejection manifest. | Chemical/drug parent-child hierarchy relation. |
| `cell_type_responds_to_molecule` | `cell_type→molecule` | `pharmacological` | no | `schema-only/missing` | - | - | -/- | Pick a concrete source and endpoint/evidence policy before any build. | Drug screen / perturbation |
| `cell_line_responds_to_molecule` | `cell_line→molecule` | `experimental` | yes | `non-canonical / deferred` | - | - | no current immutable PRISM 20Q2 candidate | Future PRISM work starts from checksum-pinned source files and a new task-local staged candidate; deleted staging is not promotable. | PR #15 historical result: 31,349 pairs / 31,952 qualifying curves; exact head `3d65b66e15df03abb8c08e08de6e127134d31bcc`. |
| `molecule_associated_phenotype` | `molecule→phenotype` | `pharmacological` | no | `canonical present / provenance-gap` | 64,784 | - | -/- | Recover exact constituent source/release, endpoint crosswalk and rejection manifest before comparison build. | Non-causal side-effect/rescue association; lineage is incomplete. |
| `disease_associated_gene` | `gene→disease` | `disease_assoc` | yes | `canonical+validated` | 83,339 | 2,928 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Gene→disease direction for causal/directed disease association; source/evidence rows preserve predicate, score, and provenance. — evidence rows: 2,928 |
| `disease_associated_protein` | `protein→disease` | `disease_assoc` | yes | `canonical promoted / documented` | 3,243 | 35,839 | -/- | Preserve PR #44 lineage and current flat-layout generations; do not infer protein disease edges from gene associations. | Only 1 edge has known mechanism and none of the 701 joined paths has known disease mechanism. |
| `disease_involves_pathway` | `pathway→disease` | `disease_assoc` | yes | `canonical+validated` | 2,296 | 2,296 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Pathway→disease direction for causal/directed pathway involvement; source/evidence rows preserve enrichment/provenance. — evidence rows: 2,296 |
| `disease_manifests_in_tissue` | `disease→tissue` | `disease_assoc` | no | `canonical promoted / review-accepted` | 19 | 29 | -/- | Accepted by `t_efac22a4` and reconfirmed by `t_2d1f767d`; rerun endpoint/evidence audit when HPA/source mappings change. | Bounded HPA Pathology Atlas / TCGA cancer-prognostics disease→native tissue context only; not a broad all-disease pathology graph. Evidence preserves HPA/TCGA predicate, source_record_id, release/license, mapping confidence, and gene-row counts. |
| `disease_subtype_of_disease` | `disease→disease` | `ontological` | yes | `canonical+validated` | 104,809 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | EFO / MONDO hierarchy |
| `disease_comorbid_disease` | `disease→disease` | `epidemiological` | no | `feature-context-not-edge` | - | - | -/- | Keep as feature/context unless a concrete EHR/co-occurrence source and privacy/provenance policy is approved. | Co-occurrence in EHR |
| `disease_has_phenotype` | `disease→phenotype` | `phenotype_assoc` | yes | `canonical+validated` | 241,797 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | HPO annotation |
| `phenotype_observed_in_tissue` | `tissue→phenotype` | `phenotype_assoc` | yes | `schema-only/missing` | - | - | -/- | Pick a concrete source and endpoint/evidence policy before any build. | Tissue→phenotype direction for directed tissue manifestation context; source/evidence rows preserve phenotype observation provenance. |
| `phenotype_subtype_of_phenotype` | `phenotype→phenotype` | `ontological` | yes | `canonical+validated` | 37,472 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | HPO hierarchy |
| `tissue_subtype_of_tissue` | `tissue→tissue` | `ontological` | yes | `canonical+validated` | 28,064 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | UBERON parent-child hierarchy |
| `cell_type_found_in_tissue` | `cell_type→tissue` | `ontological` | yes | `staged-only/deferred` | - | - | 958/958 | Review staged edge/evidence, run endpoint/evidence audits, then decide promotion; no canonical promotion in this audit card. | Cell Ontology / UBERON — staged edges/evidence: 958/958 |
| `cell_type_involved_in_disease` | `cell_type→disease` | `disease_assoc` | no | `source-audit-only/deferred` | - | - | -/- | Source audit only; select/approve a source and endpoint policy before building. | scRNA disease enrichment |
| `cell_type_subtype_of_cell_type` | `cell_type→cell_type` | `ontological` | yes | `staged-only/deferred` | - | - | 4,526/4,526 | Review staged edge/evidence, run endpoint/evidence audits, then decide promotion; no canonical promotion in this audit card. | Cell Ontology IS-A — staged edges/evidence: 4,526/4,526 |
| `cell_line_models_disease` | `cell_line→disease` | `experimental` | no | `staged-only/deferred` | - | - | 983/1,218 | Review staged edge/evidence, run endpoint/evidence audits, then decide promotion; no canonical promotion in this audit card. | Curated annotation — staged edges/evidence: 983/1,218 |
| `cell_line_derived_from_cell_type` | `cell_line→cell_type` | `experimental` | yes | `staged-only/deferred` | - | - | 65/65 | Review staged edge/evidence, run endpoint/evidence audits, then decide promotion; no canonical promotion in this audit card. | Cellosaurus — staged edges/evidence: 65/65 |
| `cell_line_derived_from_tissue` | `cell_line→tissue` | `experimental` | yes | `canonical+validated` | 1,092 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Cellosaurus origin |
| `cell_line_from_organism` | `cell_line→organism` | `metadata` | yes | `canonical+validated` | 1,183 | 1,183 | -/- | Keep canonical; rerun endpoint/evidence audit when upstream source changes. | Donor species — evidence rows: 1,183 |
| `organism_has_gene` | `organism→gene` | `genetic` | yes | `canonical+validated` | 109,325 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Ensembl species |
| `organism_has_tissue` | `organism→tissue` | `ontological` | yes | `canonical+validated` | 16,061 | - | -/- | Canonical edge exists; add/backfill evidence only if source provenance is available and useful. | Anatomy ontology |
| `paper_produced_dataset` | `paper→dataset` | `metadata` | yes | `metadata-only / graph-disconnected` | - | - | 4/4 | Do not promote as graph adjacency; preserve as dataset/paper provenance/catalog metadata. | Provenance — staged edges/evidence: 4/4; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |
| `paper_cites_paper` | `paper→paper` | `literature` | yes | `metadata-only / graph-disconnected` | - | - | 16/16 | Do not promote as graph adjacency; keep citation data outside training graph unless a separate literature-only analysis explicitly opts in. | Citation graph — staged edges/evidence: 16/16; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |
| `dataset_contains_disease` | `dataset→disease` | `metadata` | yes | `metadata-only / graph-disconnected` | - | - | 0/0 | Do not promote as graph adjacency; preserve measured-entity membership in dataset catalog/evidence metadata. | Measured entity — staged edges/evidence: 0/0; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |
| `dataset_contains_molecule` | `dataset→molecule` | `metadata` | yes | `metadata-only / graph-disconnected` | - | - | 1,000/1,000 | Do not promote as graph adjacency; preserve measured-entity membership in dataset catalog/evidence metadata. | Measured entity — staged edges/evidence: 1,000/1,000; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |
| `dataset_contains_cell_type` | `dataset→cell_type` | `metadata` | yes | `metadata-only / graph-disconnected` | - | - | 100/100 | Do not promote as graph adjacency; preserve measured-entity membership in dataset catalog/evidence metadata. | Measured entity — staged edges/evidence: 100/100; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |
| `dataset_contains_cell_line` | `dataset→cell_line` | `metadata` | yes | `canonical metadata-only / graph-disconnected` | 1,183 | - | 1,183/1,183 | Retained in place by `t_d97c4547` after backup gate; exclude from graph export/training. | Measured entity — staged edges/evidence: 1,183/1,183; canonical policy sidecar `metadata/dataset_paper_graph_policy_t_d97c4547.{json,md}`; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |
| `dataset_contains_tissue` | `dataset→tissue` | `metadata` | yes | `canonical metadata-only / graph-disconnected` | 27 | - | 27/27 | Retained in place by `t_d97c4547` after backup gate; exclude from graph export/training. | Measured entity — staged edges/evidence: 27/27; canonical policy sidecar `metadata/dataset_paper_graph_policy_t_d97c4547.{json,md}`; see `docs/dataset_paper_graph_disconnection_t_c07b8b57.md`. |

## Storage layer

- LaminDB: node registry, ontology resolution, artifact versioning
- Parquet/GCS/FUSE: canonical node, edge, feature, and evidence tables
- bionty/pertdb: ontology and perturbation/molecule management where applicable

## Graph export

Preferred target for new work is PyTorch Geometric `HeteroData`; DGL export remains fallback/backward-compatibility for older TxGNN training code. PyG/HeteroData training exports exclude `dataset` and `paper` node types, plus any relations touching them, by default even if canonical metadata files remain present. Audit/debug-only exports may opt in explicitly, but model training/inference should treat dataset/paper as metadata/evidence rather than graph adjacency.
