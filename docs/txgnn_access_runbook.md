# Jouvence KG access runbook

This runbook is the default access path for workers using the Jouvence KG at `gs://jouvencekb/main`. Small bounded inspection may happen from the macOS worker environment, but heavy Jouvence work is VM-only. The filename and `txgnn-worker` VM name are retained compatibility identifiers.

Emergency guardrail (`t_d682b7ad`): heavy LaminDB/PyG/ReMap/embedding/full-KG jobs must run on `txgnn-worker` or another explicitly approved in-region worker. Use `gs://jouvencekb/main` as the source for those jobs and `gs://jouvencekb/staging` for temporary outputs. Do **not** run heavy reads/writes through `/Users/jkobject/mnt/gcs/...` / macOS GCS-FUSE. Future heavy cards must state `must_run_on=txgnn-worker`, preflight `hostname`, use `gcloud compute ssh` for worker launch/inspection, check for an existing related writer/process, and fail immediately if any heavy input/output path starts with `/Users/jkobject/mnt/gcs`.

Current access contract, verified after the flat-layout migration:

- canonical Parquet root: `gs://jouvencekb/main`;
- native source snapshots: `gs://jouvencekb/raw`;
- bounded local copies: `artifacts/cache/<task-id>/`;
- no GCS-FUSE access path is current or supported;
- LaminDB instance `jkobject/jouvencekb` stores runtime state under `gs://jouvencekb/.lamin`.

Do not print tokens, DB URLs, or raw Lamin/GCloud credential files in logs.

## 1. GCS access: primary verified path

Check the active Google account without printing the email in shared logs:

```bash
gcloud auth list --filter=status:ACTIVE --format='value(account)' | sed 's/.*/<configured-account>/'
```

Verify the bucket root and canonical layers:

```bash
gcloud storage ls gs://jouvencekb/
gcloud storage ls gs://jouvencekb/main/edges/
gcloud storage ls gs://jouvencekb/raw/
```

Expected root prefixes:

```text
gs://jouvencekb/.lamin/
gs://jouvencekb/main/
gs://jouvencekb/raw/
gs://jouvencekb/staging/  # present only while candidates exist
gs://jouvencekb/pyg/      # present only while the derived build exists
```

Use `gcloud storage` for current scripts.

## 2. Local scratch/cache policy

Small bounded inspection should use a direct GCS-capable reader or copy only the
needed objects into a task-scoped local cache:

```text
artifacts/cache/<task-id>/
```

Example:

```bash
mkdir -p artifacts/cache/<task-id>/{edges,evidence,nodes,features,raw}

gcloud storage cp \
  gs://jouvencekb/main/edges/gene_interacts_gene.parquet \
  artifacts/cache/<task-id>/edges/gene_interacts_gene.parquet
```

Do not create `.omoc/gcs-cache/...` or mount the bucket. For native inputs, copy
from `gs://jouvencekb/raw/...` into `artifacts/cache/<task-id>/raw/...` and retain
the source URI in reports.

### DuckDB verification from a task-scoped cache

```bash
uv run --with duckdb python - <<'PY'
import duckdb
p = 'artifacts/cache/<task-id>/nodes/organism.parquet'
con = duckdb.connect()
print('count', con.sql(f"select count(*) from read_parquet('{p}')").fetchone()[0])
PY
```

For relation/evidence audits, copy the specific Parquet first, then use bounded
DuckDB summaries before making schema decisions:

```bash
uv run --with duckdb python - <<'PY'
import duckdb
relation = 'gene_interacts_gene'
p = f'artifacts/cache/<task-id>/evidence/{relation}.parquet'
con = duckdb.connect()
print(con.sql(f"""
    select source, source_dataset, evidence_type, predicate, direction, count(*) as n
    from read_parquet('{p}')
    group by 1,2,3,4,5
    order by n desc
""").df().to_string(index=False))
PY
```


## 3. Filesystem access policy

GCS-FUSE is retired. Use direct `gs://jouvencekb/main/...` reads where the
library supports them, or targeted `gcloud storage cp` into
`artifacts/cache/<task-id>/`. PyG is copied from `gs://jouvencekb/pyg/*` to a
local directory, verified, and memory-mapped; it is never sampled through a
bucket mount.

## 4. LaminDB connection

Active instance slug for this project:

```text
jkobject/jouvencekb
```

The repo currently pins `lamindb==2.2.1` in `pyproject.toml`; an older executed notebook notes that the remote DB may be ahead of that package version and suggests `pip install lamindb>=2.4`. In this repo, use `uv run` so the workspace schema package is available.

### CLI checks

Workers on this Mac should load the local Lamin API key before Lamin commands. Do not echo the key:

```bash
export LAMIN_API_KEY="$(cat ~/.laminkey)"
```

Then run:

```bash
uv run lamin info
uv run lamin connect jkobject/jouvencekb
uv run lamin info
```

If `uv run lamin info` reports `User: anonymous`, first check whether `~/.laminkey` exists and was exported as above. If credentials are absent or expired, run:

```bash
uv run lamin login
uv run lamin connect jkobject/jouvencekb
```

Do not print `~/.lamin/*.env`, `~/.laminkey`, or raw credential contents; they may contain secrets.

Observed sanitized output on 2026-06-21 after auth/cache repair:

```text
Instance: jkobject/jouvencekb
 - branch: main
 - space: all
Details:
 - storage: gs://jouvencekb (None)
 - db: sqlite:////Users/jkobject/Library/Caches/lamindb/jouvencekb/.lamindb/lamin.db
 - modules: bionty, pertdb
Cache & settings:
 - cache: /Users/jkobject/Library/Caches/lamindb
 - user settings: /Users/jkobject/.lamin
 - system settings: /Library/Application Support/lamindb
User: jkobject

uv run lamin connect jkobject/jouvencekb
! The original path gs://jouvencekb/.lamindb/lamin.db does not exist anymore.
However, the local path /Users/jkobject/Library/Caches/lamindb/jouvencekb/.lamindb/lamin.db still exists, you might want to reupload the object back.
! SQLite file does not exist in the cloud, but exists locally: /Users/jkobject/Library/Caches/lamindb/jouvencekb/.lamindb/lamin.db
To push the file to the cloud, call: lamin disconnect
→ connected lamindb: jkobject/jouvencekb
exit_code 0
```

The output above is retained as a historical 2026-06 transcript. The remote
storage-root mismatch was resolved on 2026-07-27 under
`gs://jouvencekb/.lamin`; do not use the old root paths in new commands.

### Python checks

Default repo environment:

```bash
export LAMIN_API_KEY="$(cat ~/.laminkey)"
uv run python - <<'PY'
import lamindb as ln
print('lamindb', getattr(ln, '__version__', 'unknown'))
db = ln.DB('jkobject/jouvencekb')
print('db_instantiated', type(db).__name__)
print('artifact_count', ln.Artifact.filter().count())
print('collection_count', ln.Collection.filter().count())
PY
```

One-off newer package probe, useful if the repo pin becomes too old for the remote DB:

```bash
export LAMIN_API_KEY="$(cat ~/.laminkey)"
uv run \
  --with 'lamindb>=2.4' \
  --with 'lnschema-txgnn @ ./manage_db/lnschema_txgnn' \
  python - <<'PY'
import lamindb as ln
print('lamindb', getattr(ln, '__version__', 'unknown'))
db = ln.DB('jkobject/jouvencekb')
print('db_instantiated', type(db).__name__)
PY
```

Observed on 2026-06-21 after auth/cache repair:

```text
lamindb 2.2.1
→ connected lamindb: jkobject/jouvencekb
db_instantiated DB
Artifact count 0
Collection count 0
```

Interpretation: this was the historical pre-migration probe. The missing-DB
warning is no longer expected: current instance configuration and remote DB use
`gs://jouvencekb/.lamin`.

### Local Lamin SQLite cache

A working local Lamin cache exists at Lamin's default cache path:

```text
/Users/jkobject/Library/Caches/lamindb/jouvencekb/.lamindb/lamin.db
```

The historical repair source has been superseded. The current remote catalog is:

```text
gs://jouvencekb/.lamin/.lamindb/lamin.db
```

A historical repo-local copy was once used for direct SQLite inspection under `.omoc/gcs-cache/lamin/lamin.db`; this is retired and should not be recreated. If direct SQLite inspection is needed, use Lamin's default cache path above or copy into a task-scoped `artifacts/cache/<task-id>/lamin/` directory.

Treat direct SQLite access as a local inspection fallback. For normal KG relation audits, prefer direct canonical GCS Parquets or task-scoped cached copies unless the task explicitly needs Lamin registries.

## 5. Worker decision tree

1. Need canonical KG Parquets?
   - If the task is heavy (LaminDB full/bulk sync, production/full PyG/GNN, ReMap scaling, embedding/full-KG scan, all-relation read, or bulk canonical KG read/write), run on `txgnn-worker`/an approved in-region worker with `gs://jouvencekb/main`.
   - For small bounded/local inspection, use a direct GCS-capable reader or `gcloud storage cp` for the exact object needed.
   - If a local copy is unavoidable, copy only needed Parquets into `artifacts/cache/<task-id>/{edges,evidence,nodes,features,raw}`.
   - Query direct GCS-capable readers or task-scoped cache files with DuckDB/PyArrow.
2. Need full tree filesystem semantics?
   - Copy the exact bounded objects needed; do not mount the bucket.
3. Need LaminDB registries?
   - Run `uv run lamin info`.
   - If anonymous, export `LAMIN_API_KEY` from `~/.laminkey` using the CLI-check command above; if that file is missing/expired, run `uv run lamin login` or ask the operator for LaminHub auth/permissions.
   - Then run `uv run lamin connect jkobject/jouvencekb` and the Python `ln.DB(...)` probe.
4. Need to update canonical KG?
   - Build and validate locally first.
   - Use explicit GCS write/copy commands only after validation gates and human review where relevant.

## 6. Common pitfalls

- Do not use `/home/ubuntu/data` on this macOS worker.
- Do not introduce a bucket mount into current commands or scripts.
- Do not convert RNA/gene-level source rows into protein relations just because a gene-to-protein mapping exists.
- Do not copy whole bucket directories unless the task explicitly requires it; most audits need a handful of Parquets.
- Do not print Lamin/GCloud credential file contents.
- Do not treat historical repo-local Lamin DB copies as equivalent to a verified LaminDB connection; verify with `uv run lamin connect jkobject/jouvencekb` and a Python registry probe.
- Do not run the `lamin disconnect` cloud-push suggestion from Lamin's warning unless explicitly approved; it is a remote write to the bucket.
