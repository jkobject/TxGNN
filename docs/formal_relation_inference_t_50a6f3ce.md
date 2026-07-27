# Post-operand formal relation inference — `t_50a6f3ce`

Status: **staged-only / review-required**

No canonical, observed-edge, cloud, VM, GCS/FUSE, or LaminDB write occurred. This run used the formal engine merged by PR #36 and the independently accepted disease-operand artifacts at PR #39 head `042472c9bbe06153a9712e919af5a9b27372a9ce`. It does not rerun or replace the historical pre-operand producer `t_e8aebc97`.

## Frozen exact-hash inputs

The run started from reviewed `origin/main` revision `1615f6a55f608974758396b4f2cf3cf73c2b331c`. The formal engine is the merged descendant `4e604c80be407ac918f49d0905dbaa371c62045f` of accepted PR #36 head `d5a2302b5b947f6bfb30ecfffd3b7e7004e5be02` and enforces policy revision `5dc88d4b5372eb2cf99039d455c556314564450c`.

Only these four accepted Parquets were copied byte-for-byte into the task-local read-only input snapshot `artifacts/cache/t_50a6f3ce/input_snapshot/`:

| Input | Rows | SHA-256 |
| --- | ---: | --- |
| `edges/molecule_targets_protein.parquet` | 2,119 | `08b5b4f2abdd4f92c4512f889fb18abe1dedc6a024147b99df09b7da447ced91` |
| `evidence/molecule_targets_protein.parquet` | 2,132 | `afe5ed235e9c109940a9009d47a88d66d829d7067992aba8b7fa300ef4aa5a88` |
| `edges/disease_associated_protein.parquet` | 3,243 | `98c1b444efa2e3a0fcaecabed948c9752b52100d8cc8b9ec012c478a3f453dc2` |
| `evidence/disease_associated_protein.parquet` | 35,839 | `0e125397708f8f8678984eeeeb99b803669e3838357b9025a2d1af5a4c8b9d12` |

The disease hashes exactly match the accepted PR #39 candidate. The molecule-target hashes exactly match its accepted causal-feature parent. The engine input-manifest semantic digest is `3c053cb8cfdb7af16f53d879031acb337d215428aa6df1696b1d328fddc591e2`.

## Formal rule and signed dimensions

The accepted algebra is `p = action × disease_mechanism × disease_direction`: `p=-1` routes to treatment and `p=+1` routes to contraindication. Missing, unknown, or conflicting operands abstain.

The exact post-operand snapshot contains 701 molecule→protein→disease paths:

| Dimension | Count |
| --- | ---: |
| joined paths | 701 |
| engine-resolved action sign known | 377 |
| action sign `-1` | 330 |
| action sign `+1` | 47 |
| action sign unknown | 324 |
| disease direction sign known | 596 |
| disease direction sign `+1` | 596 |
| disease direction sign unknown | 105 |
| disease mechanism sign known | 0 |
| disease mechanism sign unknown | 701 |
| fully signed products | 0 |

The accepted disease operand artifact does contain one disease edge with both operands known, but that protein is absent from the 701 joined molecule-target paths. The new disease-direction coverage therefore reaches 596 joined paths, while all 701 still lack a disease mechanism sign. No treatment or contraindication can be emitted. This is a source-coverage result, not a biological or novelty claim.

## All-template result

All 24 approved registry templates were evaluated: 20 inferred-edge templates and four coherence-only derived-view templates. Candidate means a generated path before observed/staged anti-join; new means a retained output row. Because no candidate reached anti-join, canonical overlap and staged overlap are both zero for every template. No derived product was materialized.

| Template | Class | Candidate | Rejected | Canonical overlap | Staged overlap | New |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `allelic_triangulation_treatment_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `cell_line_protein_to_gene_expression_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `cell_type_protein_to_gene_expression_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `cell_type_tissue_gene_existential_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `disease_phenotype_tissue_localization_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `disease_phenotype_tissue_triangle_v2` | derived | 0 | 0 | 0 | 0 | 0 |
| `gene_disease_to_protein_disease_strict_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `mutation_disease_phenotype_candidate_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `mutation_disease_phenotype_triangle_v2` | derived | 0 | 0 | 0 | 0 | 0 |
| `mutation_protein_disease_candidate_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `mutation_protein_gene_attribution_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `mutation_protein_gene_disease_candidate_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `mutation_protein_gene_phenotype_candidate_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `mutation_transcript_gene_attribution_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `pathway_associated_member_feature_v2` | derived | 0 | 0 | 0 | 0 | 0 |
| `pathway_associated_protein_member_feature_v2` | derived | 0 | 0 | 0 | 0 | 0 |
| `pathway_disease_candidate_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `pharmacogenomic_efficacy_treatment_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `protein_disease_to_gene_disease_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `signed_gene_target_contraindication_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `signed_gene_target_treatment_v2` | inferred | 0 | 0 | 0 | 0 | 0 |
| `signed_protein_target_contraindication_v2` | inferred | 0 | 701 | 0 | 0 | 0 |
| `signed_protein_target_treatment_v2` | inferred | 0 | 701 | 0 | 0 | 0 |
| `tissue_protein_to_gene_expression_v2` | inferred | 0 | 0 | 0 | 0 | 0 |

Both sets of 701 signed-protein paths were rejected as `missing_sign_or_causal_support`. The report preserves ten bounded, fully typed rejected-path samples per signed endpoint, including premise edge/evidence identifiers, source releases, sign computation, and exact input snapshot provenance. The other 22 templates have no complete local premise inventory.

## Immutable staged artifact and determinism

Two clean builds used the same snapshot ID, all 24 templates, `max_rows_per_file=50,000`, `max_paths_per_template=5,000`, and `sample_limit=10`:

- parity root: `artifacts/staged/t_50a6f3ce_run1/`
- final root: `artifacts/staged/t_50a6f3ce/`

Their complete file inventories and bytes are identical:

| Final artifact file | SHA-256 |
| --- | --- |
| `manifest/input_manifest.json` | `c71eddb953d069a914ecf1ded11844d39e8237fab718dcafaafd4796cc4cdcde` |
| `manifest/pilot_report.json` | `9392e83bc8c94143031d73a3bb78acb6211129643936f9e707ac70e44c0405b2` |
| `manifest/template_registry_v2.json` | `e23e34dfe51e3a568b2ee9e928ed6ddce4c8395bcac540c2b03dfcf03bb45e1a` |

The honest zero result produces zero `edges_inferred` Parquets, zero `evidence_inferred` Parquets, and zero derived-view Parquets. No placeholder, observed, canonical, or novelty artifact was fabricated.

## Validation

`uv run --no-sync pytest -q tests/test_relation_composition_allowlist.py` passes all 54 focused tests. This includes:

- the complete 2×2×2 action × GoF/LoF × risk/protective truth table;
- six missing, unknown, aggregate-conflict, and value-conflict fail-closed probes;
- signed treatment/contraindication routing and provenance;
- absent, empty, unrelated, partial, stale, malformed, source-mismatched, self-hash-mismatched, accepted-hash-mismatched, and evidence-hash-mismatched canonical contraindication receipts;
- one exact complete accepted receipt;
- deterministic stale-output removal and rejected-motif cleanup;
- direct/evidence conflict, circularity, context, mapping, pathogenicity, and duplicate-inflation gates.

Ruff, compileall, Git diff checks, generated-file guards, and final artifact readback are recorded in the Kanban handoff. Residual scientific risk is missing source-backed disease mechanism coverage on every currently joined protein path; relaxing that gate is not authorized.
