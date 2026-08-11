# TxGNN / Jouvence KG schema overview

This page describes the current flat-layout catalogue at `gs://jouvencekb/main`.
The deterministic machine-readable relation source of truth is
[`relation-evidence-ledger.json`](relation-evidence-ledger.json); its generated
human view is [`relation_coverage_current.md`](relation_coverage_current.md).
Regenerate both with:

```bash
uv run python scripts/build_relation_evidence_ledger.py
uv run python scripts/build_relation_evidence_ledger.py --check
```

## Current canonical snapshot

Catalogue date: `2026-07-27`.

- Node tables: `15`; node rows: `55,523,691`.
- Active schema relations: `67`.
- Canonical edge tables: `43`; edge rows: `103,181,903`.
- Canonical evidence tables: `22`; evidence rows: `78,035,525`.
- Canonical edge tables without matching evidence: `21`.
- Active schema relations without canonical edge: `24`.
- Evidence tables without canonical edge: `0`.
- Candidate/non-active relations: `2` (kept outside the 67 denominator).

The catalogue was collected by bounded object listing and Parquet footer/schema
reads. It proves object identity, generation and row count; it does not by itself
prove pair uniqueness, endpoint anti-joins or biological replayability.

## Node schema and coverage

| Node type | Primary namespace | Rows |
| --- | --- | ---: |
| `cell_line` | Cellosaurus | 1,183 |
| `cell_type` | CL | 3,513 |
| `dataset` | DOI / UUID | 1 |
| `disease` | EFO | 41,859 |
| `enhancer` | ENCODE | 48,808,144 |
| `gene` | Ensembl Gene | 267,830 |
| `molecule` | ChEMBL | 31,007 |
| `mutation` | dbSNP | 2,589,509 |
| `organism` | NCBI Taxonomy | 1 |
| `paper` | PubMed | 2,958,199 |
| `pathway` | Reactome | 48,575 |
| `phenotype` | HPO | 16,449 |
| `protein` | Ensembl Protein | 233,995 |
| `tissue` | UBERON | 16,061 |
| `transcript` | Ensembl Transcript | 507,365 |

Planned source-native node families such as protein complexes, PTM/site/event
nodes and distinct mature/precursor miRNA nodes remain non-active until schema
extension and source policy are approved.

## Relation and evidence contract

Canonical edge tables use at minimum:

```text
x_id, x_type, y_id, y_type, relation, display_relation,
source, credibility, [additional edge features...]
```

Evidence rows live in `evidence/{relation}.parquet`, keyed to the same relation
and endpoint pair while preserving source-specific assertions, records, studies,
scores, assays, releases and context. Edges are deduplicated graph assertions;
evidence cardinality is not required to be 1:1 with edge cardinality.

Missing evidence is not automatically a defect. The 21 canonical edges without
evidence are exhaustively routed in the ledger as structural/ontological accepted
exceptions, source-known backfills, provenance recovery, graph-disconnected
metadata, or relation-policy decisions. Evidence must never be fabricated merely
to improve a denominator.

The five legacy molecule relations remain `provenance-gap`, including the original
edge lineage of `molecule_treats_disease` despite its later partial evidence. See
[`relation-provenance-and-gaps.md`](relation-provenance-and-gaps.md) for the exact
resolution gates.

## Modeling boundaries

- Relation names follow source-native assertion and endpoint type.
- Gene/RNA rows are not projected into protein relations.
- Assay, score, direction, sign and context stay in evidence/features rather than
  proliferating relation-name variants.
- `dataset` and `paper` are graph-disconnected provenance/catalog metadata and are
  excluded from default PyG/HeteroData message passing.
- No zero-row or placeholder Parquet is created to satisfy schema coverage.
- Candidate relations remain outside `RELATIONS` until source and endpoint policy
  are approved.

## Storage and export

- Canonical tables: `gs://jouvencekb/main/{nodes,edges,evidence,features}/`.
- Candidate artifacts: task-scoped local or GCS staging only.
- LaminDB records ontology resolution and artifact lineage.
- Preferred graph export is PyTorch Geometric `HeteroData`; metadata-only
  dataset/paper relations require explicit audit opt-in and are not training
  adjacency by default.