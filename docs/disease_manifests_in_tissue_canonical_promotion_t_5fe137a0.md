# disease_manifests_in_tissue canonical promotion — t_5fe137a0

Date: 2026-06-24  
Producer/staged source: `t_badd3e1e`, semantic approval from `t_7e5953c2`.  
Status: `canonical promoted` / `review-accepted` by `t_efac22a4`; exact immutable generations reconfirmed by `t_2d1f767d`.

## Scope

Promoted only the bounded Human Protein Atlas Pathology Atlas / TCGA cancer-prognostics `disease_manifests_in_tissue` candidate from:

```text
artifacts/staged/t_badd3e1e/disease-tissue-phenotype-context/
```

to canonical KG root `gs://jouvencekb/kg/v2` / `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2`.

No broader `t_badd3e1e` relation-gap batch was promoted. No `phenotype_observed_in_tissue`, `disease_comorbid_disease`, `cell_type_*`, or rejected HPA candidate rows were promoted.

## Canonical objects

- `gs://jouvencekb/kg/v2/edges/disease_manifests_in_tissue.parquet`
  - FUSE: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2/edges/disease_manifests_in_tissue.parquet`
  - rows: 19
  - size: 5,416 bytes
  - sha256: `648185b0b614852f5b3d7637dfada519935b895452934c630bd0c279656b4dca`
  - GCS generation: `1782325469191009`
  - GCS CRC32C: `u8X16w==`
  - GCS MD5: `InWrVFw5VmnbbQJ1DGbeSQ==`
- `gs://jouvencekb/kg/v2/evidence/disease_manifests_in_tissue.parquet`
  - FUSE: `/Users/jkobject/mnt/gcs/jouvencekb-kg/v2/evidence/disease_manifests_in_tissue.parquet`
  - rows: 29
  - size: 22,231 bytes
  - sha256: `d157afa05a9952c6e439de1744d0d53bc191552c2a2377003c3297dbe7486941`
  - GCS generation: `1782325470549824`
  - GCS CRC32C: `IIwEJw==`
  - GCS MD5: `lNf56ZhTdB/0T2CaaCNvZw==`

## Validated counts and semantics

Post-write validation report: `artifacts/reports/t_5fe137a0_postwrite_validation.json`.

- edge rows: 19
- evidence rows: 29
- distinct evidence-supported edge keys: 19
- duplicate `relation|x_id|y_id` edge keys: 0
- disease endpoint anti-joins: 0
- tissue endpoint anti-joins: 0
- edge/evidence support gaps: 0 / 0
- source audit rows re-read: 25
- rejected candidate rows re-read: 2
- staged/canonical sha256 mismatches: 0

Evidence preserves the bounded source semantics:

- `source`: `Human Protein Atlas`
- `source_dataset`: `proteinatlas.tsv Cancer prognostics columns`
- predicate: `Cancer prognostics column denotes TCGA/validation cancer type context`
- release: `HPA 25.1`
- license: `HPA downloadable data; see https://www.proteinatlas.org/about/download`
- non-empty `source_record_id`
- `text_span` JSON with HPA cancer type/column, disease+tissue mapping confidences, and non-empty/prognostic gene-row counts.

The rejected HPA labels remain excluded from canonical edge/evidence rows:

- `Cervical Squamous Cell Carcinoma and Endocervical Adenocarcinoma`
- `Head and Neck Squamous Cell Carcinoma`

## Commands run

```bash
uv run python artifacts/reports/t_5fe137a0_validate_disease_manifests_in_tissue.py
uv run python -m manage_db.audit_edge_evidence artifacts/staged/t_badd3e1e/disease-tissue-phenotype-context --relations disease_manifests_in_tissue --json --fail-on-missing > artifacts/reports/t_5fe137a0_preflight_stage_edge_evidence_audit.json
uv run python -m py_compile manage_db/build_staged_disease_tissue_context.py artifacts/reports/t_5fe137a0_validate_disease_manifests_in_tissue.py
uv run --group dev pytest tests/test_build_staged_disease_tissue_context.py -q

gcloud storage cp artifacts/staged/t_badd3e1e/disease-tissue-phenotype-context/edges/disease_manifests_in_tissue.parquet gs://jouvencekb/kg/v2/edges/disease_manifests_in_tissue.parquet
gcloud storage cp artifacts/staged/t_badd3e1e/disease-tissue-phenotype-context/evidence/disease_manifests_in_tissue.parquet gs://jouvencekb/kg/v2/evidence/disease_manifests_in_tissue.parquet

uv run python artifacts/reports/t_5fe137a0_postwrite_validate_disease_manifests_in_tissue.py
uv run python -m manage_db.audit_edge_evidence /Users/jkobject/mnt/gcs/jouvencekb-kg/v2 --relations disease_manifests_in_tissue --json --fail-on-missing > artifacts/reports/t_5fe137a0_postwrite_canonical_edge_evidence_audit.json
uv run python -m py_compile manage_db/build_staged_disease_tissue_context.py artifacts/reports/t_5fe137a0_validate_disease_manifests_in_tissue.py artifacts/reports/t_5fe137a0_postwrite_validate_disease_manifests_in_tissue.py
```

Observed outputs:

- staged preflight validation: `ok: true`, 19 edges / 29 evidence, 0 endpoint anti-joins, 0 duplicate edges, 0 support gaps.
- staged `manage_db.audit_edge_evidence`: `ok: true`, 19 edges / 29 evidence, 0 edges without evidence, 0 evidence without edge.
- `tests/test_build_staged_disease_tissue_context.py`: 3 passed in 0.19s.
- canonical post-write validation: `ok: true`, staged/canonical sha256 matched for both files.
- canonical `manage_db.audit_edge_evidence`: `ok: true`, 19 edges / 29 evidence, 0 edges without evidence, 0 evidence without edge.

## Residual risks / review notes

Independent review accepted this exact narrow cancer-context-specific HPA/TCGA promotion, and `t_2d1f767d` reconfirmed the unchanged object generations and relation gates. It is not a broad all-disease pathology tissue-manifestation graph.
