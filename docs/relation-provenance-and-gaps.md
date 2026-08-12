# Relation provenance and gaps

Status: **documentation contract / provenance-gap**

Snapshot: canonical flat layout after storage migration (`gs://jouvencekb/main`)

Scope: relation provenance only; no node, feature, embedding, GCS-write, rebuild, or promotion claim.

This page separates three facts that must not be conflated:

1. a canonical Parquet object exists and has an immutable object identity;
2. a historical source family or migration receipt is known;
3. the accepted source-to-object build can be replayed exactly.

A migration receipt proves byte-preserving movement, not biological replayability. The five relations below therefore remain `provenance-gap` pending full parity and independent review. Task `t_86299745` recovered the exact flattened TxGNN source boundary and added an immutable task-scoped builder, fixture replay, mapping quarantine, evidence candidates and a full-worker command; it does not yet prove that rebuilt bytes/keys match the accepted canonical generations. Their canonical objects are retained while that final proof remains open; no evidence rows may be fabricated to improve status.

## Canonical relation gaps

All edge assertions use the canonical endpoint contract `(relation, x_id, y_id)`, resolve `x_id` and `y_id` against their typed node tables, and are graph-level deduplications. The catalog collected Parquet footers and object metadata only, so it did not revalidate uniqueness or endpoint anti-joins.

| Relation | Canonical object identity | Attested historical source/bundle | Endpoint mapping and transformation | Evidence now | Replay and decision | Next bounded action |
| --- | --- | --- | --- | --- | --- | --- |
| `molecule_associated_phenotype` | `main/edges/molecule_associated_phenotype.parquet`; 64,784 rows; generation `1785155484199958`; MD5 `jDlMgFXi8mabZULz/sOQnQ==` | TxGNN v6.0 file 7144484; source predicate `side effect`; constituent family SIDER, whose upstream release is not encoded | Exact DrugBank→molecule and HPO→phenotype normalization; broad non-causal molecule→phenotype assertions; graph keys deduplicated while source multiplicity remains evidence. | No matching canonical evidence file; task builder emits a staged evidence candidate | `provenance-gap`; immutable builder and fixture pass, but full canonical-generation parity is not yet reviewed. | Run full worker replay and account for pair/evidence parity or every exception. |
| `molecule_contraindicates_disease` | `main/edges/molecule_contraindicates_disease.parquet`; 30,675 rows; generation `1785155484349742`; MD5 `ixr4zyqm6tV++hhcKn9lCA==` | TxGNN v6.0 file 7144484; source predicate `contraindication`; constituent family DrugCentral, whose upstream release is not encoded | Exact DrugBank→molecule and MONDO→disease normalization; directed negative assertion; graph-key deduplication with rejected mappings quarantined. | No matching canonical evidence file; positive indication or trial evidence is never reused | `provenance-gap`; immutable builder and fixture pass, but full canonical-generation parity is not yet reviewed. | Run full worker replay; preserve the negative predicate and account for non-overlap without deletion authority. |
| `molecule_parent_of_molecule` | `main/edges/molecule_parent_of_molecule.parquet`; 4,140 rows; generation `1785155484679611`; MD5 `OEqS3FWlGG5lPX3u0wNUow==` | TxGNN v6.0 file 7144484; source predicate `parent of`; constituent family CTD, whose upstream release is not encoded | CTD exposure IDs become typed molecule IDs with `CTD:` namespace; source parent→child orientation is preserved and graph keys are deduplicated. | No matching canonical evidence file; task builder emits source-row evidence | `provenance-gap`; immutable builder and fixture prove orientation, but full canonical-generation parity is not yet reviewed. | Run full worker replay and account for exact orientation, endpoint anti-joins and exceptions. |
| `molecule_synergizes_molecule` | `main/edges/molecule_synergizes_molecule.parquet`; 2,672,628 rows; generation `1785155484817964`; MD5 `eea/DOo7o4LqxYp0JVweFw==` | TxGNN v6.0 file 7144484; source predicate `synergizes with`; constituent family DrugBank interactions, whose upstream release is not encoded | Exact DrugBank molecule IDs; source pair order is preserved; directed graph keys deduplicated while source-row multiplicity remains evidence. | No matching canonical evidence file; task builder emits legacy DrugBank-interaction provenance | `provenance-gap`; the label is not quantified synergy, physical interaction, or a combination-screen measurement. Full parity is not yet reviewed. | Run full worker replay and retain the semantic caveat; never invent score, assay, threshold, dose or context. |
| `molecule_treats_disease` | `main/edges/molecule_treats_disease.parquet`; 14,135 rows; generation `1785155486922602`; MD5 `eaFp6AYU6VBmXjxFxfAK5Q==` | TxGNN v6.0 file 7144484; DrugCentral predicates `indication`/`off-label use` plus CTD `linked to`; upstream constituent releases are not encoded. Later support is independently sourced from OpenTargets/ClinicalTrials.gov. | Exact DrugBank/CTD molecule and MONDO disease normalization; source predicate and direction retained; graph keys deduplicated. | Canonical later evidence has 8,285 rows but 481 distinct edge keys: 481 current edges supported, 13,654 unsupported by that later evidence, and 0 later-evidence-only keys. It does not reconstruct original lineage. | `provenance-gap`; original replay builder now exists, while later support remains a separate lane and full parity is not yet reviewed. | Run full worker replay and stage exception-accounted comparison; never rewrite the original edge table from the 481-edge later subset. |

### Recovered flattened source boundary (`t_86299745`, 2026-08-12)

The common accepted source boundary is TxGNN/DeepPurpose Dataverse DOI `10.7910/DVN/CNQV69`, dataset v6.0 published `2023-06-07T04:55:16Z`, file ID `7144484` (`kg.csv`), size `981751236`, MD5 `aac8191d4fbc5bf09cdf8c3c78b4e75f`, CC0-1.0. TxGNN code commit `f378c5132e287f2e02605c47d0c8df27750b413a` pins file 7144484. PrimeKG processing source at `9330ab697ee7cbca88d7c2aa0d0e8f9ad99aace7` identifies the constituent families: SIDER side effects; DrugCentral indication/contraindication/off-label assertions; CTD exposure hierarchy and exposure-disease links; and DrugBank drug-interaction rows. Their upstream release versions are not encoded in the flattened TxGNN file and are intentionally not invented.

`manage_db/rebuild_molecule_provenance_gaps.py` selects exact source-native predicates (`side effect`, `contraindication`, `parent of`, `synergizes with`, `indication`, `off-label use`, `linked to`), normalizes typed DrugBank/CTD/HPO/MONDO endpoints, preserves directed orientation and evidence multiplicity, quarantines unsupported/malformed rows, and writes only to a new task-scoped output directory. The `synergizes with` lane is conservatively documented as a legacy DrugBank interaction label: there is no combination-screen score, assay context, or threshold in TxGNN and it must not be promoted as quantified synergy evidence.

For all five rows, the historical migration receipt points from `kg/v2/...` to `main/...`. Those old URIs are non-executable history and must not be used as current read/write instructions. Remaining proof is a full worker replay against the frozen canonical generations, pair/evidence parity or explicit exception accounting, immutable staged readback, and independent review. Until that gate passes, every row remains `provenance-gap` and canonical writes are forbidden.

## Reconciled legacy relation work

### `disease_associated_protein` — PR #44

PR #44 at exact head `443cbc91d30f6fef4f88622d9c8092f32412174a` is recoverable documentation for a reviewed UniProtKB/UniProtKB-humsavar protein-native causal-operand build and create-only promotion. The current flat canonical objects are:

| Object | Rows | Current generation |
| --- | ---: | ---: |
| `gs://jouvencekb/main/edges/disease_associated_protein.parquet` | 3,243 | `1785155482165594` |
| `gs://jouvencekb/main/evidence/disease_associated_protein.parquet` | 35,839 | `1785155491357899` |

The PR records 0 duplicate edge keys, 0 evidence/edge key mismatches or support gaps, 0 protein/disease endpoint anti-joins, and exact staged/canonical hashes at the historical promotion. Its old `kg/v2` object URIs, generations, writer-lock/preflight receipt, and release marker are historical and were not copied into the flat public layout. The flat-layout object map is the migration receipt; it is not a new biological build receipt. Historical reviewer: `t_0611e6c6`.

Scientific limitation remains explicit: only 1 of 3,243 edges has both a known mechanism and known disease direction, and that edge appears in none of the 701 joined causal paths. The relation is canonical and source-backed, but signed disease-mechanism coverage is not solved.

### PRISM 20Q2 `cell_line_responds_to_molecule` — PR #15

PR #15 is documentation/backlog only. The relation is not canonical and no current immutable staged artifact exists. The old `kg/staging` prefixes were deleted; they are historical references, not replay targets.

Source identity:

- Figshare article `20564034`, DOI `10.6084/m9.figshare.20564034.v1`, license CC BY 4.0;
- file `36794595`, dose-response curve parameters, MD5 `eb0c7ee3ccb9e480148c71fcdc97312e`;
- file `36794610`, pooling metadata, MD5 `8a484f5f4b704abd06cd3201e1d7692b`;
- file `36794613`, README, MD5 `47419770d1edfcc36e0b11465f7d1fd0`;
- file `36794616`, replicate-collapsed logfold change, MD5 `d89c92f6d66366729c54389a4f3876b4`;
- file `36794619`, replicate-collapsed treatment info, MD5 `162da467eb97a67abdbdbee7af101091`.

Historical builder reference only: `manage_db/build_staged_prism_20q2.py` at exact PR head `3d65b66e15df03abb8c08e08de6e127134d31bcc`. The file is no longer active code. It mapped cell lines by exact canonical `ACH-*` identity and compounds by RDKit-derived exact/unique InChIKey; names were prohibited as mapping keys. Of 1,552 Broad IDs, 1,054 mapped uniquely and 498 were quarantined (447 unmatched structures, 39 conflicting source structures, 12 missing structures).

The corrected historical semantics are 31,349 deduplicated canonical cell-line/molecule candidate pairs supported by 31,952 qualifying source curves. One evidence row was retained per qualifying curve, so edge and evidence cardinality were intentionally not 1:1. Eligibility required preferred-screen policy, passed STR profiling, AUC ≤ 0.70, and R² ≥ 0.80. This remains an old staged candidate policy, not accepted canonical biology.

A future reprise is bounded to a fresh task-scoped fetch of these five exact files, checksum verification, resurrection/review of the historical builder in an isolated branch, a small fixture replay, and a newly versioned staged candidate with endpoint, pooling-context, evidence-multiplicity, and deterministic-readback gates. It does not authorize recovery of deleted staging, canonical writes, or coupling to CRISPR dependency.

Live recovery boundary (2026-08-12): bucket soft delete is 31 days
(`2678400s`) but became effective only at `2026-08-12T09:27:50.492Z`;
object versioning and lifecycle are absent. Bounded `--soft-deleted` probes under
both `gs://jouvencekb/kg/staging/**` and `gs://jouvencekb/staging/**` matched no
objects. Soft delete is not retroactive, so PRISM #15 staging is not GCS-restorable:
recovery is the exact Figshare refetch/checksum path plus the historical builder.

### Formal inferred-edge lane — PR #41 result retained

The accepted formal v2 registry had 24 templates and materialized 701 joined paths. Among them, 377 had known pharmacological action and 596 had known disease direction, but 0 had known disease mechanism. Consequently it emitted 0 inferred edge rows and 0 inferred evidence rows, and no placeholder Parquet was created. This is a valid fail-closed result, not a missing-artifact failure and not permission to relax the operand contract.

## Status and promotion guard

A relation listed in the first table may leave `provenance-gap` only when all of the following are committed and reviewed together:

1. release-pinned native input identifiers and checksums;
2. exact source assertion and endpoint mapping policy, including quarantines;
3. exact producer file plus immutable commit;
4. verified task-scoped rebuild command;
5. deterministic output and pair/evidence parity or an explicit exception manifest;
6. comparison against the current canonical generation;
7. independent review.

A migration copy, catalog footer, notebook that only checks artifact identity, source-family URL, or later partial evidence backfill is insufficient on its own.

The subsequent relation-expansion source freeze is
[`relation-expansion-source-contract.md`](relation-expansion-source-contract.md)
with a deterministic JSON partner. It now pins the recovered TxGNN file and builder,
but it does not close any gap before full parity and independent review.
