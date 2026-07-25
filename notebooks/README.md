# Jouvence usage notebooks

This directory is the user-facing notebook entry point. It contains only notebooks that show how to inspect, query, and use Jouvence. Database construction and historical build/audit notebooks live in [`../reproduce/`](../reproduce/).

## Sequence

1. [`01_data_model_and_use_cases.ipynb`](01_data_model_and_use_cases.ipynb) — understand nodes, biological assertions, evidence, features, and valid scientific use cases.
2. [`02_nodes_features_and_embeddings.ipynb`](02_nodes_features_and_embeddings.ipynb) — inspect entities, descriptions, sequences, fingerprints, and embeddings with bounded reads.
3. [`03_relations_evidence_and_questions.ipynb`](03_relations_evidence_and_questions.ipynb) — query relations together with their evidence and provenance.
4. [`04_lamindb_equivalent_queries.ipynb`](04_lamindb_equivalent_queries.ipynb) — perform equivalent exact-ID lookups through the `jkobject/jouvencekb` LaminDB catalog.
5. [`05_sampled_pyg_heterodata.ipynb`](05_sampled_pyg_heterodata.ipynb) — build and inspect a bounded PyG `HeteroData` sample.
6. [`06_sampled_ml_use_cases.ipynb`](06_sampled_ml_use_cases.ipynb) — run deterministic sampled retrieval, neighborhood, and link-prediction examples with leakage caveats.
7. [`07_data_inventory_explorer.ipynb`](07_data_inventory_explorer.ipynb) — a simple read-only explorer for canonical, inferred-canonical, and staged Parquets: storage roots, access, schemas, bounded samples, embeddings, and inferred links.

The numeric prefix is the canonical order. New user-facing notebooks must continue the sequence with a two-digit prefix.

## Safe execution

From the repository root:

```bash
uv sync --group dev --group notebooks --group gnn
uv run python scripts/build_public_notebooks.py
uv run python scripts/build_data_explorer_notebook.py
uv run python scripts/check_public_notebooks.py --execute
uv run python scripts/check_data_explorer_notebook.py --execute
```

Fixture mode is the default and performs no canonical write or full-KG read. Live reads are opt-in and bounded; follow the access variables documented in the repository [`README.md`](../README.md).
