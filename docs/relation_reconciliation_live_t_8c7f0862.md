# Live relation reconciliation — `t_8c7f0862`

- Captured: `2026-07-22T13:47:24Z`
- Schema commit: `034e498abb54d6d98e1b2b86f4a50b2b51f893f5`
- Immutable ledger: `.omoc/reports/relation_reconciliation_live_t_8c7f0862.json`
- Ledger SHA256: `8600a4b05a699f65b9b40423a6b279c6c20edace31c17e09f3c53d0f4958517a`
- Exact GCS inventory bundle: `.omoc/reports/relation_reconciliation_live_t_8c7f0862_gcs_inventory.json`
- Inventory bundle SHA256: `450911fb3d468938226dbd98f51258f2ab332d003b748872a295730994047ecf`
- Durable PR mirrors: `artifacts/reports/t_8c7f0862/relation_reconciliation_live_t_8c7f0862.json.gz` and `artifacts/reports/t_8c7f0862/relation_reconciliation_live_t_8c7f0862_gcs_inventory.json.gz`; decompress to the exact JSON hashes above

## Executive result

The active-schema denominator reconciles exactly once: **67 relations**. Direct GCS readback has **42 canonical active edge relations**, **21 with evidence**, **21 without evidence**, and **101,747,911 canonical edge rows**. The previous 40/18/22/100,080,390 snapshot is stale.

Exactly **14** canonical no-evidence relations are explicitly accepted exceptions. Exactly **5** canonical relations are evidence-backfill candidates; two canonical dataset relations are graph-disconnected feature/context. No missing evidence object is silently counted as complete.

P0 finding: `molecule_treats_disease` has a confirmed concrete non-merge/overwrite failure. Canonical evidence is CTGov-only (7,804 assertions, 377 distinct edge keys); the live staged OpenTargets file has 481 assertions/keys, 104 keys are absent, and 377 overlaps lost source multiplicity. This is `review-required`; any repair must merge evidence identities and requires a separate write gate.

ReMap route C is complete for current scope as accepted canonical feature/context: bounded generation `1782308308670478` (2,915,130 rows), plus the exact 27-object full support-QA prefix (48,768,788 summary rows + 1,179 global TF rows). Only conversion into observed `tf_binds_enhancer` topology is `deferred-policy`; no active compute or recovery lane exists.

## Denominator and buckets

| Metric | Documented hypothesis | Fresh live result |
| --- | ---: | ---: |
| Active schema relations | 67 | 67 |
| Canonical active relations | 40 | 42 |
| Canonical with evidence | 18 | 21 |
| Canonical without evidence | 22 | 21 |
| Declared not canonical | 27 | 25 |
| Canonical edge rows | 100,080,390 | 101,747,911 |
| Review-required | 3 | 1 |

Next-state partition (sum must equal 67):

- `accepted-canonical`: **34**
- `deferred-policy`: **2**
- `evidence-backfill-candidate`: **5**
- `feature-context`: **10**
- `promote-candidate`: **9**
- `rejected`: **1**
- `review-required`: **1**
- `schema-missing`: **5**

Sum: **67**.

## One-row-per-active-relation ledger

| Relation | X→Y | Direct | Canonical edge/evidence/proof rows | Staged edge/evidence rows | Support / endpoint result | Status | Exactly one next state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gene_has_transcript` | `gene→transcript` | true | 507,365/–/– | –/– | gaps 507365/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `transcript_encodes_protein` | `transcript→protein` | true | 233,995/–/– | –/– | gaps 233995/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `mutation_in_gene` | `mutation→gene` | true | 2,599,525/2,599,525/2,599,525 | 1580388/1580388 | gaps 0/0; endpoint reported-zero-on-current-promoted-artifact | `canonical+accepted` | `accepted-canonical` |
| `mutation_associated_gene` | `mutation→gene` | false | 535,093/535,093/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `mutation_affects_transcript` | `mutation→transcript` | true | 2,599,922/2,599,922/– | 1580388/1580388 | gaps 0/0; endpoint reported-zero-on-current-promoted-artifact | `canonical+accepted` | `accepted-canonical` |
| `mutation_causes_protein_change` | `mutation→protein` | true | 177,735/177,735/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `mutation_overlaps_enhancer` | `mutation→enhancer` | false | 1,664,278/1,664,278/– | 3335215/3335215 | gaps 0/0; endpoint reported-zero-on-current-promoted-artifact | `canonical+accepted` | `accepted-canonical` |
| `mutation_associated_disease` | `mutation→disease` | false | 4,656,171/4,656,171/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `mutation_associated_phenotype` | `mutation→phenotype` | false | 164,406/169,005/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `gene_associated_phenotype` | `gene→phenotype` | false | 3,330/–/– | –/– | gaps 3330/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `mutation_affects_molecule_response` | `mutation→molecule` | false | 4,866/18,595/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `gene_ortholog_gene` | `gene→gene` | true | 161,675/161,675/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `enhancer_regulates_gene` | `enhancer→gene` | false | 48,808,144/48,810,390/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `enhancer_regulates_transcript` | `enhancer→transcript` | true | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `noncanonical+policy-deferred` | `deferred-policy` |
| `gene_coexpressed_gene` | `gene→gene` | false | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `tissue_expresses_gene` | `tissue→gene` | true | 5,338,736/–/– | –/– | gaps 5338736/0; endpoint not-live-rerun | `canonical+evidence-incomplete` | `evidence-backfill-candidate` |
| `tissue_expresses_protein` | `tissue→protein` | true | 137,351/137,531/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `cell_type_expresses_gene` | `cell_type→gene` | true | 1,561,873/–/– | –/– | gaps 1561873/0; endpoint not-live-rerun | `canonical+evidence-incomplete` | `evidence-backfill-candidate` |
| `cell_type_expresses_protein` | `cell_type→protein` | true | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `active-schema+data-absent` | `schema-missing` |
| `cell_line_expresses_gene` | `cell_line→gene` | true | 20,928,056/–/– | –/– | gaps 20928056/0; endpoint not-live-rerun | `canonical+evidence-incomplete` | `evidence-backfill-candidate` |
| `cell_line_expresses_protein` | `cell_line→protein` | true | –/–/– | 3083/3090 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `cell_line_gene_essentiality` | `cell_line→gene` | false | –/–/– | 1433992/1433992 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `gene_interacts_gene` | `gene→gene` | false | 7,424,037/14,336,594/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `tf_regulates_gene` | `gene→gene` | true | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `active-schema+data-absent` | `schema-missing` |
| `tf_binds_enhancer` | `gene→enhancer` | true | –/–/– | 189459767/189459767 | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `accepted-canonical-feature-context+topology-deferred` | `feature-context` |
| `transcript_interacts_protein` | `transcript→protein` | true | –/–/– | 0/0 | gaps 0/0; endpoint not-applicable-zero-row | `noncanonical+current-candidate-rejected` | `rejected` |
| `transcript_interacts_gene` | `transcript→gene` | false | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `active-schema+data-absent` | `schema-missing` |
| `protein_interacts_protein` | `protein→protein` | true | 3,550/12,288/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `pathway_contains_gene` | `pathway→gene` | false | 630,932/630,932/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `pathway_contains_protein` | `pathway→protein` | false | –/–/– | 15436/18068 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `pathway_child_of_pathway` | `pathway→pathway` | true | 147,680/–/– | –/– | gaps 147680/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `molecule_in_pathway` | `molecule→pathway` | false | 1,680/–/– | –/– | gaps 1680/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `molecule_targets_gene` | `molecule→gene` | true | 41,239/41,239/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `molecule_targets_protein` | `molecule→protein` | true | –/–/– | 2119/2132 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `molecule_treats_disease` | `molecule→disease` | false | 14,135/7,804/– | –/481 | gaps 13758/0; endpoint not-live-rerun | `canonical+review-required` | `review-required` |
| `molecule_contraindicates_disease` | `molecule→disease` | false | 30,675/–/– | –/– | gaps 30675/0; endpoint not-live-rerun | `canonical+evidence-incomplete` | `evidence-backfill-candidate` |
| `molecule_synergizes_molecule` | `molecule→molecule` | false | 2,672,628/–/– | –/2672628 | gaps 2672628/0; endpoint pass | `canonical+evidence-incomplete` | `evidence-backfill-candidate` |
| `molecule_parent_of_molecule` | `molecule→molecule` | true | 4,140/–/– | –/– | gaps 4140/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `cell_type_responds_to_molecule` | `cell_type→molecule` | false | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `active-schema+data-absent` | `schema-missing` |
| `cell_line_responds_to_molecule` | `cell_line→molecule` | true | –/–/– | 11040/11713 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `molecule_associated_phenotype` | `molecule→phenotype` | false | 64,784/–/– | –/– | gaps 64784/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `disease_associated_gene` | `gene→disease` | true | 83,339/2,928/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `disease_associated_protein` | `protein→disease` | true | 3,243/35,839/– | 3243/35839 | gaps 0/0; endpoint reported-zero-on-current-promoted-artifact | `canonical+accepted` | `accepted-canonical` |
| `disease_involves_pathway` | `pathway→disease` | true | 2,296/2,296/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `disease_manifests_in_tissue` | `disease→tissue` | false | 19/29/– | –/– | gaps 0/0; endpoint reported-zero-on-current-promoted-artifact | `canonical+accepted` | `accepted-canonical` |
| `disease_subtype_of_disease` | `disease→disease` | true | 104,809/–/– | –/– | gaps 104809/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `disease_comorbid_disease` | `disease→disease` | false | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `disease_has_phenotype` | `disease→phenotype` | true | 241,797/–/– | –/– | gaps 241797/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `phenotype_observed_in_tissue` | `tissue→phenotype` | true | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `active-schema+data-absent` | `schema-missing` |
| `phenotype_subtype_of_phenotype` | `phenotype→phenotype` | true | 37,472/–/– | –/– | gaps 37472/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `tissue_subtype_of_tissue` | `tissue→tissue` | true | 28,064/–/– | –/– | gaps 28064/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `cell_type_found_in_tissue` | `cell_type→tissue` | true | –/–/– | 958/958 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `cell_type_involved_in_disease` | `cell_type→disease` | false | –/–/– | –/– | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `noncanonical+policy-deferred` | `deferred-policy` |
| `cell_type_subtype_of_cell_type` | `cell_type→cell_type` | true | –/–/– | 4526/4526 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `cell_line_models_disease` | `cell_line→disease` | false | –/–/– | 983/1218 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `cell_line_derived_from_cell_type` | `cell_line→cell_type` | true | –/–/– | 65/65 | gaps 0/0; endpoint pass | `staged+validated-promote-candidate` | `promote-candidate` |
| `cell_line_derived_from_tissue` | `cell_line→tissue` | true | 1,092/–/– | –/– | gaps 1092/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `cell_line_from_organism` | `cell_line→organism` | true | 1,183/1,183/– | –/– | gaps 0/0; endpoint not-live-rerun | `canonical+accepted` | `accepted-canonical` |
| `organism_has_gene` | `organism→gene` | true | 109,325/–/– | –/– | gaps 109325/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `organism_has_tissue` | `organism→tissue` | true | 16,061/–/– | –/– | gaps 16061/0; endpoint not-live-rerun | `canonical+accepted-no-evidence-exception` | `accepted-canonical` |
| `paper_produced_dataset` | `paper→dataset` | true | –/–/– | 4/4 | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `paper_cites_paper` | `paper→paper` | true | –/–/– | 16/16 | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `dataset_contains_disease` | `dataset→disease` | true | –/–/– | 0/0 | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `dataset_contains_molecule` | `dataset→molecule` | true | –/–/– | 1000/1000 | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `dataset_contains_cell_type` | `dataset→cell_type` | true | –/–/– | 100/100 | gaps None/None; endpoint not-applicable-no-accepted-edge-candidate | `feature-context+noncanonical` | `feature-context` |
| `dataset_contains_cell_line` | `dataset→cell_line` | true | 1,183/–/– | 1183/1183 | gaps 1183/0; endpoint not-live-rerun | `canonical-metadata-only+graph-disconnected` | `feature-context` |
| `dataset_contains_tissue` | `dataset→tissue` | true | 27/–/– | 27/27 | gaps 27/0; endpoint not-live-rerun | `canonical-metadata-only+graph-disconnected` | `feature-context` |

Every table row has object generations/hashes, source-native semantics, support-gap provenance, endpoint-check provenance, staging identities/prefixes, explicit absence/deferral fields, and one `next_state` in the JSON ledger.

## Live staging routing

All 10,856 validated live objects under `v2/staging/` fall into exactly 13 prefixes. Every prefix is routed below; the durable tracked immutable inventory mirror contains every exact object name, generation, size, MD5 when available, and CRC32C.

| Prefix | Objects | Parquets | Identity digest | Relations | Route/exclusion |
| --- | ---: | ---: | --- | --- | --- |
| `gs://jouvencekb/kg/v2/staging/cell-line-assays-2026-06-22-t_c2b0803c/` | 9 | 6 | `f6ffbe6b5e821a6bd71f26bbd866d1e00b5dd5d46e91e32eddbbc65dacc4e8c2` | `cell_line_expresses_protein`, `cell_line_gene_essentiality`, `cell_line_responds_to_molecule` | route to relation-specific promote-candidate review; do not batch-promote |
| `gs://jouvencekb/kg/v2/staging/cell-type-context-relations-t_d468e2dc/` | 6 | 4 | `44385f02b852431633d1ef2818b5a30d61ef8ce5eed8c99169da4d20ba7be282` | `cell_type_found_in_tissue`, `cell_type_subtype_of_cell_type`, `cell_type_involved_in_disease` | two validated promote candidates; disease route is source-gap/deferred-policy |
| `gs://jouvencekb/kg/v2/staging/cellosaurus-cell-line-metadata-20260622-t_bb0fb082/` | 11 | 4 | `017b04df5f678da09fd102cc9c7382c10a1dba7fe673b56b2d2eb5b512cb64f8` | `cell_line_derived_from_cell_type`, `cell_line_models_disease` | route to relation-specific promote-candidate review |
| `gs://jouvencekb/kg/v2/staging/disease-associated-protein-20260622-t_7f0cccde/` | 8 | 3 | `da093217dcbe4855b358c0b6e53f051bdd4d148f8b6706e1394e68d2ec5c3c5d` | `disease_associated_protein` | historical staged source retained; superseded byte-for-byte by terminally accepted canonical edge/evidence generations from t_aa5cd96e reviewed by t_0611e6c6 |
| `gs://jouvencekb/kg/v2/staging/enhancer-regulates-transcript-audit-20260622-t_8ed77c71/` | 16 | 0 | `3e2fbb0c750322d195036cbe2c8257f121adf45727fb9fd71731a6687715b4cd` | `enhancer_regulates_transcript` | source audit only; no ENST/TSS-native assertion found; deferred-policy |
| `gs://jouvencekb/kg/v2/staging/molecule-synergizes-evidence-20260622-t_4e12f7c7/` | 3 | 1 | `af3e8122fc4ef6e45a5deb37df519d2b9f1866c36467e1c9c8cd30a6e0c2603b` | `molecule_synergizes_molecule` | complete evidence-only backfill candidate; canonical evidence remains absent |
| `gs://jouvencekb/kg/v2/staging/molecule-targets-protein-chembl-20260622-t_84bf3876/` | 9 | 3 | `1a580c5a1a418b9be8499c6bcbf6f9aaf263063280aec326e1279c3add9c07c3` | `molecule_targets_protein` | route to protein-native promote-candidate review |
| `gs://jouvencekb/kg/v2/staging/opentargets-clinical-drug-evidence-20260622-t_ceee5d53/` | 8 | 1 | `d99b11aa46249a223ab08b6c7aa8b75647829c72981b7919361b145f0477dd6d` | `molecule_treats_disease`, `molecule_contraindicates_disease` | retain: 481 OpenTargets assertions are not fully represented by current CTGov-only canonical evidence; contraindication produced zero accepted rows |
| `gs://jouvencekb/kg/v2/staging/paper-dataset-provenance-20260622-t_649cee71/` | 18 | 16 | `8ceb0950eb3c32c111158bc10baa428cd8535a743a11473847c255bcb6f0901a` | `paper_produced_dataset`, `paper_cites_paper`, `dataset_contains_disease`, `dataset_contains_molecule`, `dataset_contains_cell_type`, `dataset_contains_cell_line`, `dataset_contains_tissue` | route to graph-disconnected provenance/catalog feature-context; zero-row file is not a canonical candidate |
| `gs://jouvencekb/kg/v2/staging/rbp-rna-clip-encori-pilot-20260622T135045Z/` | 7 | 4 | `30f2f1a63130253666d4884e28f1abc346cd2c4837f50e8839d9c95499cc1ab9` | `transcript_interacts_protein` | current candidate rejected: zero accepted rows because endpoints are not source-native ENST/ENSP/UniProt |
| `gs://jouvencekb/kg/v2/staging/reactome-pathway-contains-protein-20260622-t_9d36e82e/` | 7 | 4 | `28d8ba38658a193cc5eafd87b06596fb1f6645d4930f5dfb6670757198722ee8` | `pathway_contains_protein` | route to protein-native promote-candidate review after pathway-level semantics acceptance |
| `gs://jouvencekb/kg/v2/staging/remap-tf-binds-enhancer-remote-pruned-chr1-20260623-t_3479936e-v7-100kb-b50k-tempfix/` | 10732 | 5366 | `0ad4377ebe51b5239ed1e856a92e26ca25bb2b01a09ac14bd953588371e2dae9` | `tf_binds_enhancer` | historical staged validation evidence only; route C is complete on accepted canonical feature/context surfaces, all-peak topology conversion is policy-deferred, and no scaling/recovery/resume lane is active |
| `gs://jouvencekb/kg/v2/staging/source-native-expansion/` | 22 | 14 | `1d4ac48f254c3d26a7d717e49ea8be2798f677f4f16c9ac05f89978f71d341b6` | `mutation_affects_transcript`, `mutation_in_gene`, `mutation_overlaps_enhancer` | historical broad/bounded candidates excluded: superseded by newer canonical relation-specific generations; broad mutation_in_gene and coordinate-only overlap are policy-disqualified |

The extra live edge object `edges/gene_interacts_gene.parquet.bak_20260618_ot` is excluded from the active denominator as a backup, not a relation. All 18 metadata objects, the single proof object, and the 28 accepted ReMap feature objects are captured exactly in the JSON ledger/inventory.

## Evidence completeness decisions

Accepted no-evidence exceptions (14): `cell_line_derived_from_tissue`, `disease_has_phenotype`, `disease_subtype_of_disease`, `gene_associated_phenotype`, `gene_has_transcript`, `molecule_associated_phenotype`, `molecule_in_pathway`, `molecule_parent_of_molecule`, `organism_has_gene`, `organism_has_tissue`, `pathway_child_of_pathway`, `phenotype_subtype_of_phenotype`, `tissue_subtype_of_tissue`, `transcript_encodes_protein`. These are accepted topology with provenance backfill only when source-backed/useful; no evidence may be fabricated.

Evidence-backfill candidates: `cell_line_expresses_gene`, `cell_type_expresses_gene`, `molecule_contraindicates_disease`, `molecule_synergizes_molecule`, `tissue_expresses_gene`. `molecule_synergizes_molecule` has a complete staged exact-support file but lacks score/study/context values and therefore needs review. `molecule_contraindicates_disease` has no accepted contraindication-specific staged evidence.

## Readback and fail-closed limits

- GCS direct object inventory and Parquet footer reads succeeded.
- Freeze gate PASS: fresh start/end inventories (2026-07-22T13:47:24Z to 2026-07-22T13:50:56Z) have identical names, generations, sizes, and hashes for edges, evidence, proof, staging, metadata, and accepted ReMap feature surfaces.
- `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2` existed but was empty/unmounted. GCS/FUSE parity is therefore **not established**; no FUSE result is treated as confirming GCS.
- No Mac all-relation endpoint/support scan was run. Each JSON row labels checks as fresh bounded readback, report-backed, exactly absent evidence, or not rerun. The independent reviewer must run representative/high-risk scans and use an approved worker for any full scan.
- ReMap: historical staged object identities remain routed/excluded, while route C is complete on the accepted bounded and full canonical feature/context surfaces. Scaling, VM review, recovery, and resume are closed; only topology conversion remains policy-deferred.

## Exact commands

```bash
git fetch origin --prune
git worktree add -b docs/t_8c7f0862-live-reconciliation /Users/jkobject/Documents/jouvence/.worktrees/t_8c7f0862 origin/main
for p in edges evidence proof staging metadata; do gcloud storage ls --recursive --json "gs://jouvencekb/kg/v2/$p/**" > "artifacts/cache/t_8c7f0862/live_inventory/$p.json"; done
gcloud storage ls --json gs://jouvencekb/kg/v2/features/remap_crm_tf_enhancer_support.parquet > artifacts/cache/t_8c7f0862/live_inventory/features_remap_bounded.json
gcloud storage ls --recursive --json 'gs://jouvencekb/kg/v2/features/remap_crm_tf_enhancer_support_full/**' > artifacts/cache/t_8c7f0862/live_inventory/features_remap_full.json
jq -s add artifacts/cache/t_8c7f0862/live_inventory/features_remap_{bounded,full}.json > artifacts/cache/t_8c7f0862/live_inventory/features_remap.json
# Repeat every listing as *_end.json after the capture. The generator compares exact identity digests and fails if any name/generation/size/hash changed.
# PyArrow GcsFileSystem + ParquetFile.metadata read every canonical and non-ReMap staged Parquet footer; ReMap was intentionally excluded.
uv run python scripts/build_live_relation_reconciliation.py --inventory-dir artifacts/cache/t_8c7f0862/live_inventory --captured-at 2026-07-22T13:47:24Z --schema-commit 034e498abb54d6d98e1b2b86f4a50b2b51f893f5 --json-output .omoc/reports/relation_reconciliation_live_t_8c7f0862.json --markdown-output docs/relation_reconciliation_live_t_8c7f0862.md --inventory-output .omoc/reports/relation_reconciliation_live_t_8c7f0862_gcs_inventory.json
python -m json.tool .omoc/reports/relation_reconciliation_live_t_8c7f0862.json >/dev/null
shasum -a 256 .omoc/reports/relation_reconciliation_live_t_8c7f0862*.json docs/relation_reconciliation_live_t_8c7f0862.md
```

No canonical GCS write and no VM start occurred.
