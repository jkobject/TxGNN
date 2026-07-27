# `mutation_in_gene` canonical promotion — t_1cfcd48f

Date: 2026-06-24  
Producer/staged source: `t_2bb8e7de`, accepted by reviewer `t_8b4de179` as a full staged candidate only.  
Status: `canonical promoted` / `review-accepted` by `t_18a346a4`; exact immutable generations reconfirmed by `t_2d1f767d`.

## Scope

Promoted only `mutation_in_gene` from `artifacts/staged/t_2bb8e7de/mutation-in-gene-full-contained-20260624` to canonical KG root `gs://jouvencekb/kg/v2` / `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2` after live endpoint revalidation against the canonical FUSE node roots.

No blanket genomic-direct relation was promoted. No `mutation_overlaps_enhancer` artifact was promoted.

## Canonical objects

- `gs://jouvencekb/kg/v2/edges/mutation_in_gene.parquet`
  - FUSE: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2/edges/mutation_in_gene.parquet`
  - rows: 2,599,525
  - size: 19,913,850 bytes
  - sha256: `ffc1c6b0dd202713ce84409985ed3d3b3fc4c62726b8987d42c5bc6ebaa10bdd`
  - GCS generation: `1782322585154580`
  - GCS CRC32C: `fs0JZg==`
  - GCS MD5: `rdOXaLA95h9W3Kg6yN+qYg==`
- `gs://jouvencekb/kg/v2/evidence/mutation_in_gene.parquet`
  - FUSE: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2/evidence/mutation_in_gene.parquet`
  - rows: 2,599,525
  - size: 231,527,887 bytes
  - sha256: `92707d52a55ba411c4bdc0fc74feee0953784b5970bdbb64946f73ba0941bd48`
  - GCS generation: `1782322590641106`
  - GCS CRC32C: `HqjMHw==`
  - GCS note: uploaded as a 5-component composite object; use CRC32C/GCS-aware clients for integrity checks.
- `gs://jouvencekb/kg/v2/proof/mutation_in_gene_containment_proof.parquet`
  - FUSE: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2/proof/mutation_in_gene_containment_proof.parquet`
  - rows: 2,599,525
  - size: 55,232,567 bytes
  - sha256: `37e8174d717738d43008dcf973b4a71cb0b0dc3a2e3eac3c3dee886e045788b7`
  - GCS generation: `1782322593820102`
  - GCS CRC32C: `7R6SlA==`
  - GCS MD5: `XSyKoIZe0YxlRhb4/ni/Kw==`

## Validated counts

Preflight live validation report: `artifacts/reports/t_1cfcd48f_preflight_live_validation.json`.  
Post-write canonical validation report: `artifacts/reports/t_1cfcd48f_postwrite_validation.json`.  
Canonical edge/evidence audit: `artifacts/reports/t_1cfcd48f_postwrite_canonical_edge_evidence_audit.json`.

- edge rows: 2,599,525
- evidence rows: 2,599,525
- containment proof rows: 2,599,525
- distinct mutation x IDs: 2,312,718
- distinct gene y IDs: 40,905
- live canonical mutation node rows read: 2,589,509
- live canonical gene node rows read: 267,830
- duplicate edge keys: 0
- duplicate evidence edge keys: 0
- duplicate evidence source-record keys: 0
- duplicate proof edge keys: 0
- live mutation endpoint anti-joins: 0
- live gene endpoint anti-joins: 0
- edge/evidence/proof support gaps: 0 / 0 / 0 / 0
- containment failures: 0
- unexpected relation/type rows: 0
- unexpected evidence predicate/source dataset rows: 0
- unexpected proof source dataset rows: 0
- L2G/GWAS/credible-set/study-locus/association leakage rows: 0
- staged/canonical size mismatches: 0
- staged/canonical sha256 mismatches: 0

Distributions:

- edge source: `OpenTargets/variant transcriptConsequences policy-filtered target-contained`: 2,599,525
- evidence source dataset: `variant+target`: 2,599,525
- evidence predicate: `policy_filtered_variant_transcript_consequence_target_gene_with_target_genomic_location_containment`: 2,599,525
- proof source dataset: `OpenTargets/target.genomicLocation`: 2,599,525

## Commands run

```bash
uv run python -m py_compile artifacts/reports/t_1cfcd48f_validate_promote_mutation_in_gene.py
uv run python artifacts/reports/t_1cfcd48f_validate_promote_mutation_in_gene.py \
  --mode preflight \
  --output artifacts/reports/t_1cfcd48f_preflight_live_validation.json \
  > artifacts/reports/t_1cfcd48f_preflight_live_validation.stdout.json
uv run python artifacts/reports/t_1cfcd48f_validate_promote_mutation_in_gene.py \
  --mode promote \
  --output artifacts/reports/t_1cfcd48f_postwrite_validation.json \
  > artifacts/reports/t_1cfcd48f_postwrite_validation.stdout.json
uv run python -m manage_db.audit_edge_evidence \
  /Users/jkobject/mnt/gcs/jouvencekb-kg/v2 \
  --relations mutation_in_gene \
  --json \
  --fail-on-missing \
  > artifacts/reports/t_1cfcd48f_postwrite_canonical_edge_evidence_audit.json
gcloud storage ls -L \
  gs://jouvencekb/kg/v2/edges/mutation_in_gene.parquet \
  gs://jouvencekb/kg/v2/evidence/mutation_in_gene.parquet \
  gs://jouvencekb/kg/v2/proof/mutation_in_gene_containment_proof.parquet \
  > artifacts/reports/t_1cfcd48f_gcs_ls_L.txt
```

Promotion copies executed by the promotion script:

```bash
gcloud storage cp artifacts/staged/t_2bb8e7de/mutation-in-gene-full-contained-20260624/edges/mutation_in_gene.parquet gs://jouvencekb/kg/v2/edges/mutation_in_gene.parquet
gcloud storage cp artifacts/staged/t_2bb8e7de/mutation-in-gene-full-contained-20260624/evidence/mutation_in_gene.parquet gs://jouvencekb/kg/v2/evidence/mutation_in_gene.parquet
gcloud storage cp artifacts/staged/t_2bb8e7de/mutation-in-gene-full-contained-20260624/proof/mutation_in_gene_containment_proof.parquet gs://jouvencekb/kg/v2/proof/mutation_in_gene_containment_proof.parquet
```

## Residual risks / review notes

- Independent review accepted this exact canonical revision; consolidated reviewer `t_2d1f767d` reconfirmed unchanged generations, hashes, counts, endpoint registries, containment, support, and leakage gates.
- The canonical evidence object was uploaded by `gcloud storage cp` with parallel composite upload enabled; GCS metadata lacks an MD5 for that object and reports `Component-Count: 5`, but staged and FUSE canonical sha256 values match exactly.
- The proof sidecar is stored under a new canonical `proof/` prefix because this relation's source policy requires preserving the independent OpenTargets `target.genomicLocation` containment proof for every edge.
- This promotion wrote no `mutation_overlaps_enhancer` object. That relation was later promoted separately from the support-gated `t_73c67c1b` candidate by `t_00551bc3`; raw coordinate-overlap-only rows remain context/support-only.
