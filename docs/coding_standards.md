---
name: coding-standards
description:
  Non-negotiable standards for writing, testing, and documenting Python code.
  Covers project planning with CLAUDE.md, memory estimation, testing,
  documentation, notebook hygiene, function design, and environment management.
globs: "**/*.py"
---

## 1. Project Planning with CLAUDE.md

### The CLAUDE.md file is the source of truth

Every project should have a `CLAUDE.md` file at the root containing:

1. **Project overview** — what it does, key entry points, important context
2. **Phased roadmap** — multi-phase plan with tasks and subtasks, using
   checkboxes (`- [ ]` / `- [x]`) to track progress
3. **Coding conventions** — project-specific patterns, dependencies, tooling
4. **Learnings and discoveries** — things that were hard to figure out and
   should not be forgotten

### When starting a session

1. **Read CLAUDE.md first** to understand the project and current state
2. If the user gives a specific task, do that
3. If no specific task is given, **look at the roadmap in CLAUDE.md** and pick
   up the next incomplete item (`- [ ]`)
4. Mark tasks as in-progress or completed as you work

### Recording learnings

When you discover something non-obvious after significant effort, **add it to
CLAUDE.md** so it's not forgotten:

- Tricky API behaviors or gotchas
- Environment setup quirks (paths, configs, auth)
- Performance characteristics or memory constraints
- Decisions made and their rationale
- External dependencies or data sources

Example learnings section:

```markdown
## Learnings

- OpenTargets `variant/` files use nested JSON in columns — must use
  `pd.json_normalize()` after `explode()`, not before
- uv is installed at `~/.cargo/bin/uv`, not in PATH by default
- LaminDB `artifact.features.get_values()` returns a dict, not a list
- Finalize step in chunked processing loads ALL chunks — that's where memory
  peaks, not the per-file loop
```

### Updating the roadmap

When completing work:

- Mark completed tasks: `- [ ]` → `- [x]`
- Add new discovered tasks under the appropriate phase
- If a phase is complete, note it in the phase header

When a phase gets complex, break it into subphases:

```markdown
### Phase 3 — Data ingestion

#### 3.1 Core datasets (complete)

- [x] Dataset A
- [x] Dataset B

#### 3.2 Extended datasets (in progress)

- [x] Dataset C
- [ ] Dataset D ← next
- [ ] Dataset E
```

---

## 2. Memory Assessment — How to Estimate Correctly

### The Common Mistake

When estimating memory for processing N files, **do not multiply** per-file peak
by file count:

```
peak per file (800 MB) × number of files (25) = 20 GB  ❌
```

This is wrong when files are processed **sequentially**. Memory from file N is
freed (garbage collected) before file N+1 starts. The correct model:

```
peak RAM = max(
    peak during file loop,     # constant per iteration, released each time
    peak during finalize,      # reads ALL accumulated results at once
)
```

The real risk is often the finalize/aggregation step:

```python
# This loads ALL chunks into memory simultaneously
combined = pd.concat([pd.read_parquet(f) for f in chunk_files], ignore_index=True)
```

### How to Properly Assess Memory Usage

**Before writing a data-processing function:**

1. **Measure one representative input:**

   ```python
   import tracemalloc
   tracemalloc.start()
   df = pd.read_parquet("data/sample.parquet")
   current, peak = tracemalloc.get_traced_memory()
   print(f"peak: {peak / 1e6:.1f} MB, rows: {len(df)}")
   tracemalloc.stop()
   ```

2. **Identify every place where data accumulates** across iterations:
   - Growing lists: `results.append(...)` in a loop → O(N) memory
   - Concat at finalize: `pd.concat(all_chunks)` → O(total rows)
   - Explode/join operations that expand N→M rows

3. **Model the peak correctly:**
   - Sequential loops: peak = max over iterations, **not sum**
   - Finalize / concat step: peak = sum of all written chunks (uncompressed)
   - Parallel subprocesses: peaks **do** add

4. **Always run a smoke test on 1 file first**, measure RSS, then extrapolate:

   ```
   finalize peak ≈ (rows_per_file × n_files) × bytes_per_row_in_pandas
   ```

5. **For very large datasets**, use streaming aggregation instead of loading all
   chunks at once — read one chunk at a time and write incrementally.

---

## 3. Testing Standards

### Every piece of logic must be a testable function

- No logic in `__main__` blocks, notebooks, or scripts that isn't also exposed
  as a named function in a module.
- Functions are the unit of reuse, testing, and documentation.

### Smoke tests before full runs

For any function that processes large files or datasets:

1. Run on **1 representative file** in a temp directory.
2. Assert on shape, dtypes, and key values — not just "no exception".
3. Only run full-scale after the smoke test passes.

### pytest for all tests

All tests live in `tests/` and are runnable with `pytest`. Test naming
convention: `test_<function_name>_<scenario>`.

Example:

```python
def test_process_data_smoke(tmp_path, sample_input_file):
    """Smoke test: process a single small file and verify output structure."""
    result = process_data(sample_input_file, tmp_path)
    assert result["rows_processed"] > 0

    output = pd.read_parquet(tmp_path / "output.parquet")
    assert set(output.columns) >= {"id", "value", "timestamp"}
    assert output["id"].notna().all()
```

Use `pytest.fixture` for shared setup (temp dirs, sample files, synthetic
DataFrames).

---

## 4. Documentation Standards

### Google-style docstrings on every function

Every public function must have a docstring with at minimum `Args`, `Returns`,
and `Raises`. Use the Google Python Style Guide format:

```python
def process_dataset(input_dir: Path, output_dir: Path) -> dict[str, int]:
    """Process raw data files and write cleaned output.

    Reads all parquet files from ``input_dir``, applies transformations,
    and writes results to ``output_dir``. Uses chunked processing to keep
    memory usage bounded.

    Args:
        input_dir: Directory containing input ``.parquet`` files.
        output_dir: Output directory. Will create subdirectories as needed.

    Returns:
        Dictionary mapping output name → row count, e.g.::

            {"processed": 1_000_000, "errors": 150}

    Raises:
        FileNotFoundError: If ``input_dir`` does not exist or contains no
            parquet files.
        ValueError: If input schema is invalid.
    """
```

Private helpers (`_write_chunk`, `_validate_row`, etc.) need at minimum a
one-line summary and a note on any non-obvious side effects.

---

## 5. Notebook Standards

### One notebook per logical phase

Each phase of the pipeline gets its own notebook in `notebooks/`. Name them
clearly by purpose (e.g., `01_data_exploration.ipynb`, `02_preprocessing.ipynb`,
`03_model_training.ipynb`).

### Notebooks showcase functions, they do not contain logic

Notebooks import from modules and call functions. They do not contain inline
processing code that duplicates module logic:

```python
# ✅ correct — import and call
from myproject.processing import load_data, transform, save_output
data = load_data(input_path)
result = transform(data)
save_output(result, output_path)

# ❌ wrong — logic belongs in a module
data = []
for f in input_path.glob("*.parquet"):
    df = pd.read_parquet(f)
    # ... 50 lines of processing ...
```

### End-to-end pipeline notebook

A dedicated notebook shows how to run the full pipeline in order, with estimated
runtimes and memory notes:

```python
# Cell 1 — Data loading (~2 min, <2 GB)
from myproject.io import load_raw_data
raw = load_raw_data(data_dir)

# Cell 2 — Preprocessing (~10 min, ~4 GB peak)
from myproject.preprocessing import clean, normalize
cleaned = clean(raw)
normalized = normalize(cleaned)

# Cell 3 — Heavy processing (⚠️ ~4 h, ~8 GB peak — run on a server)
from myproject.processing import expensive_transform
result = expensive_transform(normalized, output_dir)
```

---

## 6. Function Design — Simplicity and Minimality

### One function, one responsibility

A function should do exactly one thing. If it does two things, split it.

```python
# ❌ too broad
def process_everything(input_dir, output_dir): ...

# ✅ focused
def load_data(input_dir) -> pd.DataFrame: ...
def transform_data(df: pd.DataFrame) -> pd.DataFrame: ...
def save_results(df: pd.DataFrame, output_dir: Path) -> None: ...
```

### No hidden global state

Functions take all inputs as arguments and return outputs explicitly. No reading
from module-level mutable state, no undocumented side effects.

### Keep helpers private and small

Internal helpers (`_write_chunk`, `_validate_row`, `_format_output`) should be
under ~20 lines. If a helper grows, it is doing too much — split it.

### Avoid premature abstraction

Three similar functions with shared boilerplate are better than one generic
`process(dataset_name, config)` function that is hard to read and test. Dedup
code only when there are ≥4 identical call sites.

---

## 7. Environment Management

### Finding and using uv

**uv** is the preferred environment manager (fast, deterministic). However, it
may not be in `$PATH` in non-interactive shells. Use this one-liner to find it:

```bash
# Find uv binary — check common locations in order
UV=$(command -v uv || echo ~/.cargo/bin/uv ~/.local/bin/uv /opt/homebrew/bin/uv | xargs -n1 sh -c 'test -x "$0" && echo "$0"' 2>/dev/null | head -1)
```

**Common uv installation paths (check in this order):**

1. `~/.cargo/bin/uv` — installed via `cargo install uv` or `curl ... | sh`
2. `~/.local/bin/uv` — installed via pipx or standalone installer
3. `/opt/homebrew/bin/uv` — installed via Homebrew on macOS ARM
4. `/usr/local/bin/uv` — installed via Homebrew on macOS Intel or Linux

**IMPORTANT:** Do NOT attempt multiple fallback strategies. This is wrong:

```bash
# ❌ WRONG — do not do this cascade of attempts
source .venv/bin/activate && pytest ...        # fails
uv run pytest ...                               # fails (uv not in PATH)
/Users/.../.local/bin/uv run pytest ...         # fails (wrong path)
which uv || find / -name uv ...                 # slow, wasteful
.venv/bin/pip install ...                       # fails (no pip in uv venv)
```

Instead:

1. Run the one-liner above **once** at session start to locate uv
2. Store the path and reuse it for all subsequent commands
3. If uv is not found after checking common paths, ask the user

### Using uv once found

```bash
# Store uv path for the session (run once at start)
UV=$(command -v uv || ls ~/.cargo/bin/uv 2>/dev/null || ls ~/.local/bin/uv 2>/dev/null)

# Then use $UV for all operations:
$UV sync                           # Install / sync deps
$UV add pandas                     # Add a package
$UV add --dev pytest               # Add a dev-only package
$UV run python scripts/process.py  # Run a script in the project env
$UV run pytest tests/              # Run tests
```

### If pip/venv is used instead

- Always use `pip install -e .` for editable installs
- Pin versions in `requirements.txt` or use `pip-tools`
- Document the Python version required

Keep lock files (`uv.lock`, `poetry.lock`, `requirements.txt`) committed and in
sync with `pyproject.toml`.

---

## Summary Checklist

Before marking any task as done, verify:

- [ ] Logic lives in a named module function (not inline in a script/notebook)
- [ ] Function has a Google-style docstring with Args / Returns / Raises
- [ ] A `pytest` test covers the happy path and at least one edge case
- [ ] A smoke test on small input passes before running at full scale
- [ ] Memory peak was estimated correctly (sequential loops do NOT sum; finalize
      steps DO)
- [ ] Dependencies are properly managed and lock files are up to date
