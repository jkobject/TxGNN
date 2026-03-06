# TxGNN — Claude Project Context

## What This Is

TxGNN is a Python ML research library for **zero-shot drug repurposing** via
graph neural networks. It trains on a biomedical knowledge graph (17,080
diseases × 7,957 drug candidates) to predict drug indications and
contraindications.

Paper:
[MedRxiv 2023.03.19.23287458](https://www.medrxiv.org/content/10.1101/2023.03.19.23287458v2)

## Package Structure

```
txgnn/
  TxData.py      # Data loading, splits, knowledge graph prep
  TxGNN.py       # Main model class (pretrain, finetune, eval, XAI)
  TxEval.py      # Disease-centric evaluation
  model.py       # GNN architecture
  utils.py       # Shared utilities
  graphmask/     # GraphMask XAI module
  data_splits/   # Pre-defined train/val/test splits
txdata_download.py  # Data download helpers (EBI FTP + Harvard Dataverse)
notebooks/
  txdata_explore.ipynb
reproduce/
  sync_nodes_to_lamindb.py
```

## Core API

```python
from txgnn import TxData, TxGNN, TxEval

TxData = TxData(data_folder_path='./data')
TxData.prepare_split(split='complex_disease', seed=42)

TxGNN = TxGNN(data=TxData, device='cuda:0')
TxGNN.model_initialize(n_hid=100, n_inp=100, n_out=100, proto=True, proto_num=3)
TxGNN.pretrain(...)
TxGNN.finetune(...)

TxEval = TxEval(model=TxGNN)
TxEval.eval_disease_centric(disease_idxs='test_set', ...)
```

## Environment

- Python >= 3.12, managed with **uv** (`uv.lock` present)
- Run: `uv run python ...`
- Key deps: PyTorch, DGL, pandas, numpy, scikit-learn, goatools
- No JupyterLab installed (only nbconvert/nbformat in venv)
- No web server — this is a pure research library

## lamindb

the lamin instance for this is jkobject/jouvencekb and requires authentication
from jkobject and a gsutil command access setup with the jkobject project id
jkobject-1549353370965

## Data

- Knowledge graph CSVs: `data/kg.csv`, `node.csv`, `edges.csv` (Harvard
  Dataverse)
- Download: `txdata_download.py` — EBI FTP HTTP mirror for OpenTargets, stdlib
  for Harvard
- OpenTargets: parallel download via threads, `.ot_complete` marker, alias
  resolution
- LaminDB integration exists (`reproduce/sync_nodes_to_lamindb.py`)
- Disease area files: `data/disease_files/*.csv`

## Splits

| Split                                                      | Description                                                 |
| ---------------------------------------------------------- | ----------------------------------------------------------- |
| `complex_disease`                                          | Systematic: all treatments for sampled diseases → test only |
| `cell_proliferation`, `mental_health`, `cardiovascular`, … | 9 disease-area splits                                       |
| `random`                                                   | Random shuffle across drug-disease pairs                    |
| `full_graph`                                               | No masking; 95% train / 5% val                              |
| `disease_eval`                                             | Single disease masking for deployment                       |

## No Dev Servers

No web framework, no API server, no frontend. Use notebooks directly via
`jupyter notebook` (must be installed separately).

---

## Expanded KG Vision

### Goal

Build a **large-scale heterogeneous biomedical knowledge graph** combining
TxGNN's existing KG with OpenTargets and other sources. Nodes are registered in
**LaminDB** and identified exclusively via **ontology IDs**. Edges and node
feature tables are stored as **Parquet files**. A loader function converts
everything into a GNN-ready graph object.

### Node Types & Ontology Namespaces

| Node type    | Primary ontology / ID namespace      |
| ------------ | ------------------------------------ |
| `paper`      | PubMed ID / DOI                      |
| `gene`       | Ensembl Gene ID (ENSG…)              |
| `transcript` | Ensembl Transcript ID (ENST…)        |
| `protein`    | UniProt accession                    |
| `pathway`    | Reactome / GO term                   |
| `molecule`   | ChEMBL ID / InChIKey                 |
| `mutation`   | dbSNP rsID / HGVS                    |
| `disease`    | MONDO / EFO / HP                     |
| `cell_type`  | Cell Ontology (CL:…)                 |
| `tissue`     | UBERON                               |
| `phenotype`  | Human Phenotype Ontology (HP:…)      |
| `cell_line`  | Cellosaurus (CVCL\_…)                |
| `organism`   | NCBI Taxonomy ID                     |
| `dataset`    | Internal UUID / DOI                  |
| `enhancer`   | ENCODE / Ensembl Regulatory Build ID |

### Edge Schema

All edges stored as Parquet with at minimum:

```
x_id, x_type, y_id, y_type, relation, display_relation,
source, credibility, [additional metadata columns…]
```

### Credibility Score

| Score | Meaning                                                            |
| ----- | ------------------------------------------------------------------ |
| `3`   | Established fact (curated DB, no ambiguity)                        |
| `2`   | Multiple independent evidence (papers from distinct author groups) |
| `1`   | Single evidence (one paper, possibly same authors)                 |

### Relation Types

**Kind legend:**

- `central_dogma` — molecular biology sequence/expression flow
- `regulatory` — transcriptional / epigenetic control
- `physical` — direct molecular binding or complex membership
- `genetic` — genomic position or variant association
- `pathway` — functional pathway membership
- `pharmacological` — drug action on target or disease
- `expression` — quantitative abundance in context
- `disease_assoc` — statistical or causal disease link
- `phenotype_assoc` — phenotypic consequence
- `ontological` — IS-A / part-of hierarchy
- `experimental` — derived from cell line / in-vitro assay
- `epidemiological` — population-level co-occurrence
- `literature` — NLP / co-mention in text
- `metadata` — dataset provenance

**Direct flag:**

- ✓ = direct biological interaction (physical, mechanistic, sequence-derived)
- ~ = sometimes direct depending on source
- ✗ = associative / statistical / indirect

| Relation                             | Source     | Target     | Kind            | Direct? | Notes                      |
| ------------------------------------ | ---------- | ---------- | --------------- | ------- | -------------------------- |
| `gene_has_transcript`                | gene       | transcript | central_dogma   | ✓       | Transcription              |
| `transcript_encodes_protein`         | transcript | protein    | central_dogma   | ✓       | Translation                |
| `gene_encodes_protein`               | gene       | protein    | central_dogma   | ✗       | Shortcut edge              |
| `mutation_in_gene`                   | mutation   | gene       | genetic         | ✓       | Genomic position           |
| `mutation_affects_transcript`        | mutation   | transcript | genetic         | ✓       | Splicing / UTR variant     |
| `mutation_causes_protein_change`     | mutation   | protein    | genetic         | ✓       | Amino acid change          |
| `mutation_overlaps_enhancer`         | mutation   | enhancer   | genetic         | ✓       | Regulatory variant         |
| `mutation_associated_disease`        | mutation   | disease    | genetic         | ~       | GWAS / ClinVar             |
| `mutation_causes_phenotype`          | mutation   | phenotype  | genetic         | ~       | Mendelian / GWAS           |
| `mutation_affects_molecule_response` | mutation   | molecule   | pharmacological | ~       | Pharmacogenomics           |
| `mutation_associated_cell_type`      | mutation   | cell_type  | genetic         | ✗       | eQTL cell-type enrichment  |
| `enhancer_regulates_gene`            | enhancer   | gene       | regulatory      | ✓       | ChIP-seq / Hi-C            |
| `enhancer_regulates_transcript`      | enhancer   | transcript | regulatory      | ✓       | TSS-specific regulation    |
| `enhancer_active_in_cell_type`       | enhancer   | cell_type  | regulatory      | ✓       | ATAC-seq / ChIP-seq        |
| `enhancer_active_in_tissue`          | enhancer   | tissue     | regulatory      | ✓       | Bulk ATAC / DNase-seq      |
| `enhancer_associated_disease`        | enhancer   | disease    | disease_assoc   | ~       | GWAS overlap               |
| `gene_coexpressed_gene`              | gene       | gene       | expression      | ✗       | Co-expression network      |
| `gene_ortholog_gene`                 | gene       | gene       | genetic         | ✓       | Cross-species orthology    |
| `transcript_alternative_transcript`  | transcript | transcript | central_dogma   | ✓       | Alternative splicing       |
| `protein_interacts_protein`          | protein    | protein    | physical        | ✓       | PPI (STRING, IntAct…)      |
| `pathway_contains_gene`              | pathway    | gene       | pathway         | ~       | Reactome / GO              |
| `pathway_contains_protein`           | pathway    | protein    | pathway         | ~       | Reactome / KEGG            |
| `pathway_child_of_pathway`           | pathway    | pathway    | ontological     | ✓       | Reactome hierarchy         |
| `molecule_in_pathway`                | molecule   | pathway    | pathway         | ~       | Metabolic pathway          |
| `molecule_targets_protein`           | molecule   | protein    | pharmacological | ✓       | Drug-target binding        |
| `molecule_treats_disease`            | molecule   | disease    | pharmacological | ✗       | Indication (clinical)      |
| `molecule_contraindicates_disease`   | molecule   | disease    | pharmacological | ✗       | Contraindication           |
| `molecule_interacts_molecule`        | molecule   | molecule   | pharmacological | ~       | Drug-drug interaction      |
| `disease_associated_gene`            | disease    | gene       | disease_assoc   | ~       | GWAS / rare variant        |
| `disease_associated_protein`         | disease    | protein    | disease_assoc   | ~       | Proteomics / genetics      |
| `disease_involves_pathway`           | disease    | pathway    | disease_assoc   | ✗       | Pathway enrichment         |
| `disease_associated_mutation`        | disease    | mutation   | genetic         | ~       | ClinVar / GWAS             |
| `disease_subtype_of_disease`         | disease    | disease    | ontological     | ✓       | MONDO / EFO hierarchy      |
| `disease_comorbid_disease`           | disease    | disease    | epidemiological | ✗       | Co-occurrence in EHR       |
| `disease_manifests_in_tissue`        | disease    | tissue     | disease_assoc   | ~       | Pathology annotation       |
| `disease_has_phenotype`              | disease    | phenotype  | phenotype_assoc | ✓       | HPO annotation             |
| `phenotype_observed_in_tissue`       | phenotype  | tissue     | phenotype_assoc | ~       | Anatomical manifestation   |
| `phenotype_caused_by_mutation`       | phenotype  | mutation   | genetic         | ~       | Mendelian causal           |
| `phenotype_associated_gene`          | phenotype  | gene       | phenotype_assoc | ~       | HPO-gene annotation        |
| `phenotype_associated_protein`       | phenotype  | protein    | phenotype_assoc | ✗       | Inferred via gene          |
| `phenotype_associated_molecule`      | phenotype  | molecule   | pharmacological | ✗       | Side effect / rescue       |
| `phenotype_associated_cell_type`     | phenotype  | cell_type  | phenotype_assoc | ✗       | Cell type enrichment       |
| `phenotype_subtype_of_phenotype`     | phenotype  | phenotype  | ontological     | ✓       | HPO hierarchy              |
| `tissue_expresses_gene`              | tissue     | gene       | expression      | ✓       | GTEx / HPA bulk RNA        |
| `tissue_expresses_protein`           | tissue     | protein    | expression      | ✓       | HPA / proteomics           |
| `cell_type_expresses_gene`           | cell_type  | gene       | expression      | ✓       | scRNA-seq (CellxGene)      |
| `cell_type_expresses_protein`        | cell_type  | protein    | expression      | ✓       | CyTOF / sc-proteomics      |
| `cell_type_found_in_tissue`          | cell_type  | tissue     | ontological     | ✓       | Cell Ontology / UBERON     |
| `cell_type_involved_in_disease`      | cell_type  | disease    | disease_assoc   | ✗       | scRNA disease enrichment   |
| `cell_type_responds_to_molecule`     | cell_type  | molecule   | pharmacological | ~       | Drug screen / perturbation |
| `cell_type_subtype_of_cell_type`     | cell_type  | cell_type  | ontological     | ✓       | Cell Ontology IS-A         |
| `cell_line_expresses_gene`           | cell_line  | gene       | experimental    | ✓       | RNA-seq (CCLE…)            |
| `cell_line_expresses_protein`        | cell_line  | protein    | experimental    | ✓       | Proteomics (CCLE…)         |
| `cell_line_responds_to_molecule`     | cell_line  | molecule   | experimental    | ✓       | GDSC / PRISM viability     |
| `cell_line_models_disease`           | cell_line  | disease    | experimental    | ~       | Curated annotation         |
| `cell_line_derived_from_cell_type`   | cell_line  | cell_type  | experimental    | ✓       | Cellosaurus                |
| `cell_line_derived_from_tissue`      | cell_line  | tissue     | experimental    | ✓       | Cellosaurus origin         |
| `cell_line_from_organism`            | cell_line  | organism   | metadata        | ✓       | Donor species              |
| `cell_line_associated_disease`       | cell_line  | disease    | experimental    | ~       | Added by user              |
| `organism_has_gene`                  | organism   | gene       | genetic         | ✓       | Ensembl species            |
| `organism_models_disease`            | organism   | disease    | experimental    | ~       | MGI / Alliance             |
| `organism_has_tissue`                | organism   | tissue     | ontological     | ✓       | Anatomy ontology           |
| `paper_mentions_gene`                | paper      | gene       | literature      | ✗       | NLP / Europe PMC           |
| `paper_mentions_disease`             | paper      | disease    | literature      | ✗       | NLP / Europe PMC           |
| `paper_mentions_protein`             | paper      | protein    | literature      | ✗       | NLP / Europe PMC           |
| `paper_mentions_molecule`            | paper      | molecule   | literature      | ✗       | NLP / Europe PMC           |
| `paper_mentions_mutation`            | paper      | mutation   | literature      | ✗       | NLP / Europe PMC           |
| `paper_mentions_pathway`             | paper      | pathway    | literature      | ✗       | NLP / Europe PMC           |
| `paper_produced_dataset`             | paper      | dataset    | metadata        | ✓       | Provenance                 |
| `paper_cites_paper`                  | paper      | paper      | literature      | ✓       | Citation graph             |
| `dataset_contains_gene`              | dataset    | gene       | metadata        | ✓       | Measured entity            |
| `dataset_contains_disease`           | dataset    | disease    | metadata        | ✓       | Measured entity            |
| `dataset_contains_molecule`          | dataset    | molecule   | metadata        | ✓       | Measured entity            |
| `dataset_contains_cell_type`         | dataset    | cell_type  | metadata        | ✓       | Measured entity            |
| `dataset_contains_cell_line`         | dataset    | cell_line  | metadata        | ✓       | Measured entity            |
| `dataset_contains_tissue`            | dataset    | tissue     | metadata        | ✓       | Measured entity            |

### Storage Layer

- **LaminDB**: node registry, ontology resolution, artifact versioning
- **Parquet**: one file (or directory) per edge type; node feature tables
- **bionty**: ontology resolution for Gene, Disease, Pathway, CellType, etc.
- **pertdb**: management of perturbations, and molecules

### Graph Export

Target: **PyTorch Geometric `HeteroData`** (preferred over DGL for new work —
more actively maintained, better heterogeneous graph API, richer ecosystem). DGL
`DGLHeteroGraph` kept as fallback for backward compatibility with existing TxGNN
training code.

```python
# Desired API
from txgnn import KGLoader
kg = KGLoader(data_dir='./data')
hetero_data = kg.to_pyg()   # PyG HeteroData
hetero_dgl  = kg.to_dgl()   # DGL HeteroGraph (legacy)
```

---

## Build Plan

### Phase 1 — Schema & ontology design ✅ (complete)

- [x] Node types + ontology namespaces defined
- [x] Full relation taxonomy with kind + direct flags
- [x] Cross-reference / alias tables (EFO↔MONDO↔HP, Ensembl↔UniProt…)
- [x] `txgnn/kg_schema.py` — Python schema as single source of truth

### Phase 2 — LaminDB schema

- [x] Set up `bionty` registries (Gene, Disease, Pathway, CellType, Tissue,
      Phenotype, Organism)
- [x] Define custom `Record` types for Paper, Transcript, Enhancer, Dataset,
      Mutation (`lnschema_txgnn`; CellLine already covered by `bionty`)
- [x] Register ontology source versions for reproducibility
      (`reproduce/register_ontology_sources.py`)

### Phase 3 — TxGNN KG migration ✅ (complete)

- [x] Map existing `node.csv` types → new ontology-based IDs
      (`manage_db/kg_migrate.py` — 129,375 nodes × 6 types,
      NCBI/HP/MONDO/GO/UBERON/CTD/Reactome/DrugBank)
- [x] Convert `kg.csv` edges → new edge Parquet schema (existing curated KG =
      credibility 3) (`manage_db/kg_migrate.py` — 8,100,498 edges × 17 relation
      files; zero unmapped relations)
- [x] Validate every node ID resolves to a bionty/LaminDB record (schema
      validation helper in `notebooks/kg_schema_overview.ipynb` §7; all IDs
      normalised to valid ontology formats)

### Phase 4 — OpenTargets ingestion ✅ (complete)

All functions in `manage_db/ingest_opentargets.py`, tested end-to-end:

- [x] `ingest_targets` → 78,725 gene nodes
- [x] `ingest_diseases` → 46,960 disease nodes + 63,886 hierarchy edges
- [x] `ingest_drugs` → 18,475 molecule nodes
- [x] `ingest_interactions` → ~12.7M protein–protein edges (per-chunk flush)
- [x] `ingest_evidence` → disease*associated_gene, molecule_treats_disease,
      disease_involves_pathway edges (per-chunk flush, all evidence*\* dirs)
- [x] `ingest_go` → 17,891 GO pathway nodes + 755,796 gene-GO edges
- [x] `ingest_reactome` → 2,825 Reactome pathway nodes + 2,841 hierarchy edges
- [x] `ingest_indication` → 76,520 approved indication edges
- [x] `ingest_mechanism_of_action` → 15,363 drug-target edges
- [x] `ingest_literature` → paper nodes + paper_mentions_gene/disease edges
      (per-chunk flush over 23.3M europepmc rows)

### Phase 5 — Additional sources (from OpenTargets local data) ✅ (complete)

All data already downloaded to `data/opentargets/` — no external sources needed.
Functions in `manage_db/ingest_opentargets.py`:

- [x] `ingest_disease_phenotype`: 137,411 `disease_has_phenotype` edges
- [x] `ingest_expression`: 3,311,510 `tissue_expresses_gene` + 1,353,553
      `cell_type_expresses_gene` edges
- [x] `ingest_biosample`: 3,499 cell_type + 16,054 tissue nodes
- [x] `ingest_pharmacogenomics`: 4,837 `mutation_affects_molecule_response`
      edges
- [x] `ingest_variants`: mutation nodes + `mutation_in_gene`,
      `mutation_affects_transcript`, `mutation_causes_protein_change` edges
      (vectorized `explode`+`json_normalize`); smoke-tested (1/25 files: 293,918
      mutations, 10,868,328 gene edges); ⚠️ full run requires ~20GB RAM, ~4
      hours — run on a server with sufficient memory
- [x] `ingest_enhancers`: enhancer nodes + `enhancer_regulates_gene`,
      `enhancer_active_in_tissue`, `enhancer_active_in_cell_type` edges
      (vectorized, `pd.cut` credibility); smoke-tested (1/83 files: 597,831
      enhancers, 597,831 gene edges)
- [x] Papers: done via OpenTargets europepmc in Phase 4 literature

### Phase 6 — Edge credibility pipeline ⚠️ (partial — NOT complete)

- [~] `_credibility_from_score(score, dtype) -> int` defined in
  `ingest_opentargets.py` but **never tested end-to-end**
- [ ] Needs handling of **composed edges** (A→C→B path vs A→B direct) where
      evidence through an intermediary node should count differently than a
      direct edge with multiple independent sources
- [ ] Multi-source author-independence check: credibility 2 requires ≥2
      independent author groups (different labs/institutions), not just 2 papers
      from the same group
- [ ] Deduplication across sources: if the same evidence is present in multiple
      datasets (e.g. a drug-target interaction from both OpenTargets and
      DrugBank), it should only count once toward credibility scoring
- [ ] Full `score_credibility(source, evidence_list) -> int` pipeline with
      edge-composition logic and proper deduplication across composed paths

### Phase 7 — Parquet storage layout

```
data/kg/
  nodes/{gene,disease,protein,…}.parquet
  edges/{relation_name}.parquet
```

### Phase 8 — KGLoader + graph export

- `KGLoader(data_dir)` scans node/edge parquets, builds index maps
- `to_pyg()` → `torch_geometric.data.HeteroData`
- `to_dgl()` → `dgl.heterograph` (backward compat)
- Integrate with `TxData.prepare_split()`

### Phase 9 — Validation

- Node ontology coverage stats
- Dangling edge checks
- Smoke-test: load full graph into PyG
