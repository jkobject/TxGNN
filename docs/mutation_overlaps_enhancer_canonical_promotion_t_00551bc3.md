# `mutation_overlaps_enhancer` support-gated canonical promotion

Kanban task: `t_00551bc3`  
Source staged candidate: `t_73c67c1b`  
Reviewer for staged candidate: `t_2fb6ffeb`  
Status: `canonical promoted` / `review-accepted` by `t_d11a3bb7`; exact immutable generations reconfirmed by `t_2d1f767d`

## Bottom line

The reviewed full support-gated `mutation_overlaps_enhancer` candidate from `t_73c67c1b` was promoted to canonical KG paths after strict dry-run gates passed. This does **not** promote raw coordinate overlap alone: every promoted row is the reviewed non-context-support-gated candidate and has evidence JSON recording the non-protein-change external support gate.

Canonical graph artifacts written:

- `gs://jouvencekb/kg/v2/edges/mutation_overlaps_enhancer.parquet`
- `gs://jouvencekb/kg/v2/evidence/mutation_overlaps_enhancer.parquet`

Canonical proof/support sidecars written under `metadata/`:

- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_support_rows_t_73c67c1b.parquet`
- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_support_summary_full_t_73c67c1b.parquet`
- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_support_summary_non_context_gated_t_73c67c1b.parquet`
- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_support_gated_examples_by_class_t_73c67c1b.jsonl`
- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_stage_manifest_t_73c67c1b.json`
- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_stage_validation_summary_t_73c67c1b.json`
- `gs://jouvencekb/kg/v2/metadata/mutation_overlaps_enhancer_canonical_promotion_t_00551bc3.json`

Local reports/scripts:

- Promotion script: `artifacts/reports/t_00551bc3_promote_mutation_overlaps_enhancer.py`
- Dry-run manifest: `artifacts/reports/t_00551bc3_mutation_overlaps_enhancer_promotion_dry_run_manifest.json`
- Post-write report: `artifacts/reports/t_00551bc3_mutation_overlaps_enhancer_canonical_promotion_report.json`
- Edge/evidence audit: `artifacts/reports/t_00551bc3_audit_edge_evidence_mutation_overlaps_enhancer.json`

## Counts and hashes

| Artifact | Rows | SHA256 |
| --- | ---: | --- |
| canonical edge | 1,664,278 | `47fb582f3da4b059a15eea28cbd7271bca1a447f367315b4361f5de8040ed227` |
| canonical evidence | 1,664,278 | `94ff3beeff13906dcdccf0a4237786dd7ad6ee33faa0fb03fd5c827cd8723e8c` |
| support rows sidecar | 10,501 | `a1eaa0e4a260f74980e675d174b5de25c622e91a53325dd40dd2a18f05820691` |
| all-supported mutation support summary | 5,851 | `ce11f92dfa388e344bc17817cc4d413989aeef53511067de09c498a22556f2af` |
| non-context-gated mutation support summary | 5,814 | `6bb6fad3d8e03d58bbdbe4dc9358868c1826222b7b77388aaca96bf4fbbc3ab7` |

## Gates run

Dry-run promotion manifest passed with no blockers:

- manifest cleanliness: actual files = 8, listed files = 8, no missing/extra files;
- staged edge/evidence rows = 1,664,278 / 1,664,278;
- unique endpoints = 5,814 mutations and 114,191 enhancers;
- duplicate edge keys = 0;
- duplicate evidence keys = 0;
- edges without evidence = 0;
- evidence without edge = 0;
- live endpoint anti-joins against canonical `nodes/mutation.parquet` and `nodes/enhancer.parquet` = 0 missing mutation endpoints and 0 missing enhancer endpoints;
- all output mutations have non-context support summary rows;
- output edges not in reviewed raw overlap source = 0;
- rows supported only by protein/context evidence in output = 0;
- evidence `text_span` JSON carries `support_gate.passed_non_context_support=true` and non-context support row count > 0.

Post-write validation:

- canonical edge/evidence/support files are byte/hash-identical to the dry-run-validated staged sources;
- official targeted `manage_db.audit_edge_evidence` passed for `mutation_overlaps_enhancer` with `ok=true`, `edges_without_evidence=0`, `evidence_without_edge=0`;
- promotion report was written to local `artifacts/reports/` and canonical `metadata/`.

## Support policy preserved

This promotion is for the reviewed support-gated candidate only. Raw coordinate overlap alone remains context/support-only and is not proof of enhancer perturbation. Evidence rows use predicate `coordinate_overlap_with_non_context_external_variant_support_gate` and preserve a leakage policy in `text_span`.

Non-context support classes in the reviewed source:

| Support class | Support rows |
| --- | ---: |
| ClinVar/EVA disease support | 7,612 |
| GWAS credible-set disease support | 844 |
| GWAS/L2G gene support | 623 |
| ClinVar/EVA phenotype support | 70 |
| UniProt variant disease support | 50 |
| ClinVar/EVA somatic disease support | 2 |

## Residual risks

- The relation remains associative/indirect (`direct=False` in schema): most available support is disease/gene/phenotype association context rather than direct enhancer-activity perturbation.
- Stronger eQTL, caQTL, MPRA, or allele-specific regulatory evidence was not available in the current KG support inputs and should remain preferred for future refinement.
- The canonical write is review-accepted for this support-gated candidate only; downstream training/export must still respect the leakage warning in the evidence metadata.

## Rollback notes

If reviewer/tester rejects this promotion, remove the exact canonical edge/evidence paths and task-specific metadata sidecars listed above, then revert status docs from `canonical promoted / review-required` to the prior validated staged-only state.
