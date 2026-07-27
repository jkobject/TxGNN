#!/usr/bin/env python3
"""Build the simple, read-only Jouvence Parquet data explorer notebook."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks" / "07_data_inventory_explorer.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip() + "\n")


def code(text: str):
    return nbf.v4.new_code_cell(text.strip() + "\n")


def build(output: Path = OUTPUT) -> None:
    cells = [
        md("""
# 07 — Explore the Jouvence data that exist today

This notebook is a **read-only map and inspector**, not a build pipeline. It answers five practical questions:

1. Where are the Parquet files stored?
2. Which location means canonical, inferred-canonical, staged, or archived?
3. How do I authenticate and read them without downloading a whole table?
4. What are the schema, row groups, columns, nulls, and example rows of one selected object?
5. Where are embeddings and inferred links, and how do I inspect them without confusing them with observations?

This notebook always reads the **real live Jouvence data plane**. It has no fixture/fake-data mode. Reads and object listings remain bounded and read-only.
"""),
        md("""
## 1. The storage map

Jouvence uses **location as part of the data contract**:

| Surface | Typical root | Meaning |
|---|---|---|
| Canonical observations | `gs://jouvencekb/main/{nodes,edges,evidence,features,embeddings}` | Reviewed, promoted objects in the canonical data plane |
| Canonical inferred outputs | `gs://jouvencekb/main/{edges_inferred,evidence_inferred}` | Reviewed derived links, kept separate from observations |
| Non-canonical candidates | `gs://jouvencekb/staging` | Temporary candidate, partial, deferred, or pre-promotion artifacts |
| LaminDB internals | `gs://jouvencekb/.lamin` | Runtime/catalog state; never a public Parquet surface |

**Canonical does not mean biologically true.** It means the object passed the project's promotion/review contract. An inferred edge is still an inference even when stored canonically.
"""),
        md("""
## 2. Access: authentication, authorization, and billing are separate

Live GCS reads use Application Default Credentials (ADC) and a caller-owned requester-pays project:

```bash
gcloud auth application-default login
# Optional if ADC cannot infer your caller-owned project:
export JOUVENCE_BILLING_PROJECT='<your-billing-project>'
uv run jupyter lab
```

The identity also needs bucket read permission. ADC alone does not grant authorization. The billing project pays request/egress charges but does not grant access. This notebook never embeds credentials or a maintainer billing project.

The roots are deliberately fixed to the real GCS data plane in this notebook. Do not replace them with fixture or cache paths. Full inventories and embedding scans remain worker jobs; this notebook only performs bounded inspection.
"""),
        code("""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from fsspec.core import url_to_fs
from google.auth import default as google_auth_default
from IPython.display import display

REPO_ROOT = Path.cwd()
if REPO_ROOT.name == "notebooks":
    REPO_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from manage_db.data_explorer import list_parquet_uris
from manage_db.public_notebooks import (
    PUBLIC_KG_ROOT,
    _storage_options,
    read_bounded_parquet,
)

try:
    SAMPLE_ROWS = int(os.environ.get("JOUVENCE_EXPLORER_SAMPLE_ROWS", "8"))
    MAX_LISTED = int(os.environ.get("JOUVENCE_EXPLORER_MAX_FILES", "250"))
except ValueError as exc:
    raise ValueError("explorer row/file limits must be integers") from exc
if not 1 <= SAMPLE_ROWS <= 100:
    raise ValueError("JOUVENCE_EXPLORER_SAMPLE_ROWS must be between 1 and 100")
if not 1 <= MAX_LISTED <= 2000:
    raise ValueError("JOUVENCE_EXPLORER_MAX_FILES must be between 1 and 2000")
_, ADC_PROJECT = google_auth_default()
BILLING_PROJECT = os.environ.get("JOUVENCE_BILLING_PROJECT") or ADC_PROJECT
"""),
        md("""
### Configuration cell

The roots below are the real GCS locations. Normally you change nothing: ADC supplies your identity and usually your project. If ADC cannot infer the requester-pays project, set `JOUVENCE_BILLING_PROJECT` before starting Jupyter.
"""),
        code("""
canonical_root = PUBLIC_KG_ROOT
staging_root = "gs://jouvencekb/staging"
if not BILLING_PROJECT:
    raise RuntimeError(
        "Could not infer a requester-pays project from ADC. Set "
        "JOUVENCE_BILLING_PROJECT to your own project, restart the kernel, and rerun."
    )

print({
    "mode": "live-gcs-only",
    "canonical_root": str(canonical_root),
    "staging_root": str(staging_root),
    "sample_rows": SAMPLE_ROWS,
    "read_only": True,
})
"""),
        md("""
## 3. A small, editable source registry

Update this table when a new storage surface is introduced. Status is assigned from the **root and layer**, never guessed from a filename such as `final` or `accepted`.
"""),
        code("""
def join_uri(root, suffix: str) -> str:
    return f"{str(root).rstrip('/')}/{suffix.strip('/')}"

SURFACES = pd.DataFrame([
    {"surface": "canonical nodes", "uri": join_uri(canonical_root, "nodes"), "status": "canonical-observed"},
    {"surface": "canonical edges", "uri": join_uri(canonical_root, "edges"), "status": "canonical-observed"},
    {"surface": "canonical evidence", "uri": join_uri(canonical_root, "evidence"), "status": "canonical-observed"},
    {"surface": "canonical features", "uri": join_uri(canonical_root, "features"), "status": "canonical-feature"},
    {"surface": "canonical embeddings", "uri": join_uri(canonical_root, "embeddings"), "status": "canonical-feature"},
    {"surface": "canonical inferred edges", "uri": join_uri(canonical_root, "edges_inferred"), "status": "canonical-inferred"},
    {"surface": "canonical inferred evidence", "uri": join_uri(canonical_root, "evidence_inferred"), "status": "canonical-inferred"},
    {"surface": "external staging", "uri": str(staging_root), "status": "non-canonical"},
])
display(SURFACES)
"""),
        md("""
## 4. List Parquet objects without reading their row payloads

Object listing is cheaper than scanning rows, but it is still a real request. Each surface uses a **server-side GCS cap of `MAX_LISTED + 1`** (or an early-stopping local walk), so the notebook never materializes an exhaustive cloud listing merely to truncate it afterward. Access/network errors propagate visibly; they are not converted into an empty inventory. Each configured surface requires at most one bounded listing request.
"""),
        code("""
def list_parquets(uri: str, status: str, surface: str, max_files: int = MAX_LISTED) -> pd.DataFrame:
    listing = list_parquet_uris(
        uri,
        limit=max_files,
        billing_project=BILLING_PROJECT,
    )
    rows = [{
        "status": status,
        "surface": surface,
        "uri": item,
        "name": Path(item).name,
    } for item in listing.uris]
    result = pd.DataFrame(rows, columns=["status", "surface", "uri", "name"])
    result.attrs["truncated"] = listing.truncated
    return result

inventories = []
for row in SURFACES.itertuples(index=False):
    frame = list_parquets(row.uri, row.status, row.surface)
    inventories.append(frame)
    suffix = " (TRUNCATED: at least one additional object)" if frame.attrs["truncated"] else ""
    print(f"{row.surface:28s} {len(frame):4d} displayed{suffix}")
inventory = pd.concat(inventories, ignore_index=True)
display(inventory.head(30))
"""),
        md("""
### Status summary

This count describes discovered **objects**, not biological rows or completion. A staging object may have been promoted elsewhere and retained for provenance. Read its manifest/review before calling it pending work.
"""),
        code("""
status_summary = (
    inventory.groupby(["status", "surface"], dropna=False)
    .size().rename("parquet_objects").reset_index()
    .sort_values(["status", "surface"])
)
display(status_summary)
"""),
        md("""
## 5. Select one Parquet and inspect its physical format

Choose any URI from `inventory`. Footer inspection reads schema and row-group metadata without materializing the full table. The default selects a small canonical node table.
"""),
        code("""
preferred = inventory[inventory["surface"].eq("canonical nodes")]
SELECTED_URI = (
    preferred.iloc[0]["uri"] if not preferred.empty
    else inventory.iloc[0]["uri"]
)
# To inspect another object, replace the line above, for example:
# SELECTED_URI = "gs://jouvencekb/main/edges/disease_associated_gene.parquet"
print("Selected:", SELECTED_URI)
"""),
        code("""
def parquet_footer(uri: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    options = _storage_options(uri, BILLING_PROJECT) if uri.startswith("gs://") else {}
    fs, path = url_to_fs(uri, **options)
    parquet = pq.ParquetFile(path, filesystem=fs)
    schema = pd.DataFrame([
        {"column": field.name, "arrow_type": str(field.type), "nullable": field.nullable}
        for field in parquet.schema_arrow
    ])
    row_groups = pd.DataFrame([
        {
            "row_group": i,
            "rows": parquet.metadata.row_group(i).num_rows,
            "bytes_uncompressed": parquet.metadata.row_group(i).total_byte_size,
        }
        for i in range(parquet.metadata.num_row_groups)
    ])
    summary = {
        "uri": uri,
        "format": "Apache Parquet",
        "rows": parquet.metadata.num_rows,
        "row_groups": parquet.metadata.num_row_groups,
        "columns": len(parquet.schema_arrow),
        "created_by": parquet.metadata.created_by,
        "serialized_footer_bytes": parquet.metadata.serialized_size,
    }
    return schema, row_groups, summary

selected_schema, selected_row_groups, selected_summary = parquet_footer(SELECTED_URI)
print(json.dumps(selected_summary, indent=2, default=str))
display(selected_schema)
display(selected_row_groups.head(20))
"""),
        md("""
## 6. Read a bounded sample

`read_bounded_parquet` seeks over row groups and stops at the requested limit. This is materially safer than `pandas.read_parquet(...).head()`, which can load the entire object before truncating.
"""),
        code("""
sample = read_bounded_parquet(
    SELECTED_URI,
    limit=SAMPLE_ROWS,
    billing_project=BILLING_PROJECT,
)
print(f"Loaded {len(sample)} rows out of footer count {selected_summary['rows']:,}")
display(sample)
"""),
        code("""
def sample_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "dtype": frame.dtypes.astype(str),
        "nulls_in_sample": frame.isna().sum(),
        "distinct_in_sample": frame.nunique(dropna=True),
        "example": [next((str(v)[:100] for v in frame[c] if pd.notna(v)), "") for c in frame.columns],
    }).rename_axis("column").reset_index()

display(sample_diagnostics(sample))
print("These are sample diagnostics, not full-table quality statistics.")
"""),
        md("""
## 7. Explore an observed edge together with its evidence

Observed assertions and their source records are separate Parquets. They join on stable edge identity: `relation, x_id, x_type, y_id, y_type`. Never join by row number.
"""),
        code("""
edge_rows = inventory[inventory["surface"].eq("canonical edges")]
evidence_rows = inventory[inventory["surface"].eq("canonical evidence")]
common_relations = sorted(set(edge_rows["name"]) & set(evidence_rows["name"]))
print("Relations with both discovered edge and evidence objects:", len(common_relations))

if common_relations:
    relation_file = common_relations[0]
    edge_uri = edge_rows.loc[edge_rows["name"].eq(relation_file), "uri"].iloc[0]
    evidence_uri = evidence_rows.loc[evidence_rows["name"].eq(relation_file), "uri"].iloc[0]
    edge_sample = read_bounded_parquet(edge_uri, limit=SAMPLE_ROWS, billing_project=BILLING_PROJECT)
    evidence_sample = read_bounded_parquet(evidence_uri, limit=min(100, SAMPLE_ROWS * 5), billing_project=BILLING_PROJECT)
    keys = ["relation", "x_id", "x_type", "y_id", "y_type"]
    available_keys = [key for key in keys if key in edge_sample and key in evidence_sample]
    display(edge_sample)
    display(evidence_sample)
    if len(available_keys) == len(keys):
        display(edge_sample.merge(evidence_sample, on=keys, how="left", suffixes=("_edge", "_evidence")).head(20))
else:
    print("No edge/evidence pair exists in this bounded inventory.")
"""),
        md("""
## 8. Find embeddings and inspect vector format

Canonical embeddings are one flat Parquet object per entity/modality/model under `main/embeddings`. A candidate under staging is not canonical merely because its manifest says `accepted`; promotion and readback are separate gates.
"""),
        code("""
embedding_mask = inventory["uri"].str.contains("embedding", case=False, na=False)
embedding_objects = inventory.loc[embedding_mask].copy()
display(embedding_objects.head(50))
print("Embedding Parquets discovered:", len(embedding_objects))
"""),
        code("""
if not embedding_objects.empty:
    EMBEDDING_URI = embedding_objects.iloc[0]["uri"]
    embedding_schema, embedding_row_groups, embedding_summary = parquet_footer(EMBEDDING_URI)
    embedding_sample = read_bounded_parquet(
        EMBEDDING_URI, limit=SAMPLE_ROWS, billing_project=BILLING_PROJECT
    )
    print(json.dumps(embedding_summary, indent=2, default=str))
    display(embedding_schema)
    display(embedding_sample)

    vector_columns = [
        c for c in embedding_sample.columns
        if c.lower() in {"embedding", "vector", "features", "x"}
    ]
    if vector_columns:
        column = vector_columns[0]
        vectors = [np.asarray(v, dtype=np.float32) for v in embedding_sample[column] if v is not None]
        vector_stats = pd.DataFrame({
            "dimension": [len(v) for v in vectors],
            "l2_norm": [float(np.linalg.norm(v)) for v in vectors],
            "finite": [bool(np.isfinite(v).all()) for v in vectors],
        })
        display(vector_stats)
    else:
        print("No standard vector column found; inspect the schema/manifest for this embedding format.")
else:
    print("No embedding Parquet was discovered in the selected roots.")
"""),
        md("""
Embedding geometry is model- and modality-specific. Similarity is not functional equivalence, causality, or therapeutic evidence. Coverage/missingness must remain explicit; do not replace absent source vectors with unlabeled zero or random vectors.
"""),
        md("""
## 9. Inspect inferred links without mixing them with observations

The two inferred layers intentionally mirror the edge/evidence split. A canonical inferred file is accepted **as an inference product**; it is never silently moved into observed `edges/`.
"""),
        code("""
inferred_edges = inventory[inventory["surface"].eq("canonical inferred edges")]
inferred_evidence = inventory[inventory["surface"].eq("canonical inferred evidence")]
display(inferred_edges)
display(inferred_evidence)

for label, frame in [("inferred edge", inferred_edges), ("inferred evidence", inferred_evidence)]:
    if not frame.empty:
        uri = frame.iloc[0]["uri"]
        print()
        print(f"{label}: {uri}")
        display(read_bounded_parquet(uri, limit=SAMPLE_ROWS, billing_project=BILLING_PROJECT))
"""),
        md("""
## 10. What is canonical, what is not, and what is unknown?

- **Canonical observed:** under the accepted `v2/nodes`, `edges`, `evidence`, or `features` surface.
- **Canonical inferred:** under `v2/edges_inferred` or `v2/evidence_inferred`; still derived rather than observed.
- **Non-canonical:** under staging surfaces. This includes candidates, deferred products, superseded attempts, and retained promotion inputs.
- **Unknown from location alone:** whether a staged artifact is pending, rejected, superseded, or retained after successful promotion. Read its immutable manifest and reviewer decision.
- **Not current:** archive, backup, removal, and rollback prefixes.

This notebook shows **what exists and how it is encoded**. It does not replace the Kanban/review ledger for why an object obtained its status.
"""),
        md("""
## 11. Updating this notebook

1. Add a row to `SURFACES` only when a new storage contract is introduced.
2. Change `SELECTED_URI` to inspect another object; do not duplicate cells.
3. Rerun from the top after changing access credentials or bounded limits.
4. Regenerate the committed notebook with:

```bash
uv run python scripts/build_data_explorer_notebook.py
```

5. Verify the clean source notebook against live GCS with:

```bash
JOUVENCE_BILLING_PROJECT='<your-billing-project>' \
  uv run python scripts/check_data_explorer_notebook.py --execute
```

For a live exhaustive inventory or full embedding analysis, create a reviewed worker task rather than increasing notebook limits on a laptop.
"""),
    ]

    for index, cell in enumerate(cells):
        cell["id"] = hashlib.sha256(f"data-explorer:{index}:{cell.cell_type}".encode()).hexdigest()[:12]
        if cell.cell_type == "code":
            cell.execution_count = None
            cell.outputs = []

    notebook = nbf.v4.new_notebook(cells=cells)
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "jouvence": {
            "data_mode": "live-gcs-only",
            "bounded": True,
            "read_only": True,
            "purpose": "data-inventory-explorer",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, output)
    print(f"wrote {output} ({len(cells)} meaningful cells)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
