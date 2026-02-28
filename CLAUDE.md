# TxGNN — Claude Project Context

## What This Is
TxGNN is a Python ML research library for **zero-shot drug repurposing** via graph neural networks. It trains on a biomedical knowledge graph (17,080 diseases × 7,957 drug candidates) to predict drug indications and contraindications.

Paper: [MedRxiv 2023.03.19.23287458](https://www.medrxiv.org/content/10.1101/2023.03.19.23287458v2)

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

## Data
- Knowledge graph CSVs: `data/kg.csv`, `node.csv`, `edges.csv` (Harvard Dataverse)
- Download: `txdata_download.py` — EBI FTP HTTP mirror for OpenTargets, stdlib for Harvard
- OpenTargets: parallel download via threads, `.ot_complete` marker, alias resolution
- LaminDB integration exists (`reproduce/sync_nodes_to_lamindb.py`)
- Disease area files: `data/disease_files/*.csv`

## Splits
| Split | Description |
|---|---|
| `complex_disease` | Systematic: all treatments for sampled diseases → test only |
| `cell_proliferation`, `mental_health`, `cardiovascular`, … | 9 disease-area splits |
| `random` | Random shuffle across drug-disease pairs |
| `full_graph` | No masking; 95% train / 5% val |
| `disease_eval` | Single disease masking for deployment |

## No Dev Servers
No web framework, no API server, no frontend. Use notebooks directly via `jupyter notebook` (must be installed separately).

---

## Expanded KG Vision

### Goal
Build a **large-scale heterogeneous biomedical knowledge graph** combining TxGNN's existing KG with OpenTargets and other sources. Nodes are registered in **LaminDB** and identified exclusively via **ontology IDs**. Edges and node feature tables are stored as **Parquet files**. A loader function converts everything into a GNN-ready graph object.

### Node Types & Ontology Namespaces
| Node type | Primary ontology / ID namespace |
|---|---|
| `paper` | PubMed ID / DOI |
| `gene` | Ensembl Gene ID (ENSG…) |
| `transcript` | Ensembl Transcript ID (ENST…) |
| `protein` | UniProt accession |
| `pathway` | Reactome / GO term |
| `molecule` | ChEMBL ID / InChIKey |
| `mutation` | dbSNP rsID / HGVS |
| `disease` | MONDO / EFO / HP |
| `cell_type` | Cell Ontology (CL:…) |
| `tissue` | UBERON |
| `phenotype` | Human Phenotype Ontology (HP:…) |
| `cell_line` | Cellosaurus (CVCL_…) |
| `organism` | NCBI Taxonomy ID |
| `dataset` | Internal UUID / DOI |
| `enhancer` | ENCODE / Ensembl Regulatory Build ID |

### Edge Schema
All edges stored as Parquet with at minimum:
```
x_id, x_type, y_id, y_type, relation, display_relation,
source, credibility, [additional metadata columns…]
```

### Credibility Score
| Score | Meaning |
|---|---|
| `3` | Established fact (curated DB, no ambiguity) |
| `2` | Multiple independent evidence (papers from distinct author groups) |
| `0` | Single evidence (one paper, possibly same authors) |

### Storage Layer
- **LaminDB**: node registry, ontology resolution, artifact versioning
- **Parquet**: one file (or directory) per edge type; node feature tables
- **bionty**: ontology resolution for Gene, Disease, Pathway, CellType, etc.

### Graph Export
Target: **PyTorch Geometric `HeteroData`** (preferred over DGL for new work — more actively maintained, better heterogeneous graph API, richer ecosystem). DGL `DGLHeteroGraph` kept as fallback for backward compatibility with existing TxGNN training code.

```python
# Desired API
from txgnn import KGLoader
kg = KGLoader(data_dir='./data')
hetero_data = kg.to_pyg()   # PyG HeteroData
hetero_dgl  = kg.to_dgl()   # DGL HeteroGraph (legacy)
```
