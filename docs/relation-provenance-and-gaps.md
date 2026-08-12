# Relation provenance and gaps

Status: **documentation contract / provenance-gap**

Snapshot: canonical flat layout after storage migration (`gs://jouvencekb/main`)

Scope: relation provenance only; no node, feature, embedding, GCS-write, rebuild, or promotion claim.

This page separates three facts that must not be conflated:

1. a canonical Parquet object exists and has an immutable object identity;
2. a historical source family or migration receipt is known;
3. the accepted source-to-object build can be replayed exactly.

A migration receipt proves byte-preserving movement, not biological replayability. The five relations below therefore remain `provenance-gap`: none has a retained exact accepted acquisition manifest, original source-to-edge builder identity, and verified rebuild command as one closed lineage. Their canonical objects are retained while those gaps are documented; no evidence rows may be fabricated to improve status.

## Canonical relation gaps

All edge assertions use the canonical endpoint contract `(relation, x_id, y_id)`, resolve `x_id` and `y_id` against their typed node tables, and are graph-level deduplications. The catalog collected Parquet footers and object metadata only, so it did not revalidate uniqueness or endpoint anti-joins.

| Relation | Canonical object identity | Attested historical source/bundle | Endpoint mapping and transformation | Evidence now | Replay and decision | Next bounded action |
| --- | --- | --- | --- | --- | --- | --- |
| `molecule_associated_phenotype` | `main/edges/molecule_associated_phenotype.parquet`; 64,784 rows; generation `1785155484199958`; MD5 `jDlMgFXi8mabZULz/sOQnQ==` | TxData/TxGNN Dataverse bundle, DOI `10.7910/DVN/CNQV69`; the constituent side-effect/rescue source release accepted for this object is not retained | Legacy molecule IDs were normalized to canonical molecule endpoints and phenotype IDs to canonical phenotype endpoints; rows were exported as broad non-causal molecule→phenotype assertions and deduplicated by relation/endpoints. The exact crosswalk version, filters, rejection manifest, and accepted source table are missing. | No matching canonical evidence file | `provenance-gap`; retain. `manage_db/export_kg.py` and the TxGNN legacy reproduction notebook are contextual exporters/documentation, not proof that they produced this accepted object. No verified exact command or producer commit exists. | Identify the exact Dataverse constituent file/version and historical crosswalk receipt; only then build a task-local comparison candidate and require pair-level parity/exception accounting. |
| `molecule_contraindicates_disease` | `main/edges/molecule_contraindicates_disease.parquet`; 30,675 rows; generation `1785155484349742`; MD5 `ixr4zyqm6tV++hhcKn9lCA==` | TxData/TxGNN Dataverse bundle, DOI `10.7910/DVN/CNQV69`; contraindication-specific constituent source is not identified | Legacy molecule and disease identifiers were normalized to canonical typed endpoints and pair assertions deduplicated. The source predicate, crosswalk version, filters, rejection manifest, and accepted source table are missing. | No matching canonical evidence file; positive indication or trial evidence must not be reused | `provenance-gap`; retain but fail closed for signed inference. No current/original builder, accepted producer commit, or verified rebuild command is evidenced. | Select or recover a contraindication-specific source and explicit predicate/direction policy; stage evidence first and compare against the 30,675 legacy pairs without treating non-overlap as deletion authority. |
| `molecule_parent_of_molecule` | `main/edges/molecule_parent_of_molecule.parquet`; 4,140 rows; generation `1785155484679611`; MD5 `OEqS3FWlGG5lPX3u0wNUow==` | TxData/TxGNN Dataverse bundle, DOI `10.7910/DVN/CNQV69`; exact chemical hierarchy source/release is not retained | Legacy molecule identifiers were normalized to canonical molecule endpoints and directed parent→child assertions deduplicated. Parent orientation, salt/mixture policy, crosswalk version, and rejected mappings are not recoverable from the edge table. | No matching canonical evidence file | `provenance-gap`; retain. No exact source table, original builder/commit, or verified command is evidenced. | Recover a release-pinned chemical hierarchy and prove orientation plus exact endpoint mapping in a bounded staged diff before deciding whether to rebuild or accept a documented no-evidence ontology exception. |
| `molecule_synergizes_molecule` | `main/edges/molecule_synergizes_molecule.parquet`; 2,672,628 rows; generation `1785155484817964`; MD5 `eea/DOo7o4LqxYp0JVweFw==` | TxData/TxGNN Dataverse bundle, DOI `10.7910/DVN/CNQV69`; exact combination-screen constituent releases and score policy are not retained | Both molecule endpoints were normalized to canonical molecule IDs; graph assertions were deduplicated by relation/endpoints. Pair ordering/symmetry, assay/score threshold, context, and rejected mappings are not evidenced by the current table. | No matching canonical evidence file; an older staged evidence-backfill claim is not a current immutable artifact | `provenance-gap`; retain, but do not interpret as physical interaction or replayable synergy measurements. No original producer commit or verified command is evidenced. | Recover exact screen files and pair-orientation/threshold policy; create a bounded evidence audit against existing edges before any full rebuild or evidence-only proposal. |
| `molecule_treats_disease` | `main/edges/molecule_treats_disease.parquet`; 14,135 rows; generation `1785155486922602`; MD5 `eaFp6AYU6VBmXjxFxfAK5Q==` | Original edge lineage: TxData/TxGNN Dataverse bundle, DOI `10.7910/DVN/CNQV69`; exact indication constituent source is not retained. Later support is independently sourced from OpenTargets/ClinicalTrials.gov. | Original molecule/disease IDs were normalized and positive indication pairs deduplicated. The accepted original crosswalk, filters, clinical-phase rule, and rejection manifest are missing. | Canonical `main/evidence/molecule_treats_disease.parquet`: 8,285 later support rows, generation `1785155492750134`. These rows support matching treatment edges but do not reconstruct the original 14,135-edge lineage or contraindications. | Edge remains `provenance-gap`; retain. The later evidence is `historical-builder-only`, not proof of full edge replay. No verified exact original edge command/producer commit exists. | Partition current edges into supported/unsupported by the canonical evidence key, recover the original indication source, and stage an exception-accounted comparison; do not rewrite the edge table from the later subset. |

For all five rows, the historical migration receipt points from `kg/v2/...` to `main/...`. Those old URIs are non-executable history and must not be used as current read/write instructions. The exact missing proof is not merely “more documentation”: it is a release-pinned native input manifest, the accepted endpoint crosswalk/rejection manifest, the exact original producer identity, and a verified command whose output is compared with the canonical object.

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
with a deterministic JSON partner. It does not close any of these five gaps; it
turns recovered sources/builders and explicit missing artifacts into independently
executable downstream contracts.
