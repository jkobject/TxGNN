"""Lightweight dataset download helpers for TxGNN."""

from __future__ import annotations

import re
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import urllib.request
import pandas as pd


# ---------------------------------------------------------------------------
# OpenTargets Platform bulk download helpers
# ---------------------------------------------------------------------------

_OT_FTP_BASE = "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform"

# Some user-facing dataset names differ from the on-disk folder name.
_OT_DATASET_ALIASES: dict[str, str] = {
    "literaturel2g_prediction": "l2g_prediction",
}

_OT_USER_AGENT = "Mozilla/5.0"


_CHUNK_SIZE = 1 << 20  # 1 MiB streaming chunks


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _OT_USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def _stream_to_file(url: str, dest: Path) -> None:
    """Download *url* to *dest* using chunked streaming (no full-buffer in RAM)."""
    import shutil
    req = urllib.request.Request(url, headers={"User-Agent": _OT_USER_AGENT})
    with urllib.request.urlopen(req) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh, _CHUNK_SIZE)


def _list_ftp_dir(url: str) -> list[str]:
    """Parse an Apache-style directory listing and return all href targets."""
    html = _http_get(url).decode()
    return re.findall(r'<a href="([^"?#]+)"', html)


def get_opentargets_releases() -> list[str]:
    """Return all available OpenTargets Platform release tags (sorted ascending).

    Queries the public EBI FTP HTTP mirror — no credentials required.

    Returns:
        List of release strings, e.g. ``["23.09", "24.06", "24.09", ...]``.
    """
    items = _list_ftp_dir(f"{_OT_FTP_BASE}/")
    versions = [
        item.rstrip("/")
        for item in items
        if re.fullmatch(r"\d+\.\d+/?", item)
    ]
    return sorted(versions, key=lambda v: [int(x) for x in v.split(".")])


def get_latest_opentargets_release() -> str:
    """Return the latest available OpenTargets Platform release tag."""
    releases = get_opentargets_releases()
    if not releases:
        raise RuntimeError("Could not discover any OpenTargets releases from EBI FTP.")
    return releases[-1]


def list_opentargets_datasets(release: str = "latest") -> list[str]:
    """Return all dataset names available for a given release.

    Args:
        release: Release tag or ``"latest"`` (default).

    Returns:
        Sorted list of dataset folder names, e.g. ``["disease", "target", ...]``.
    """
    if release == "latest":
        release = get_latest_opentargets_release()
    url = f"{_OT_FTP_BASE}/{release}/output/"
    items = _list_ftp_dir(url)
    return sorted(
        item.rstrip("/")
        for item in items
        if item.endswith("/") and not item.startswith("/")
    )


_SUCCESS_MARKER = ".ot_complete"


def _is_downloaded(dest: Path) -> bool:
    """Return True if the dataset was fully downloaded (marker file present)."""
    return (dest / _SUCCESS_MARKER).exists()


def _download_single_file(url: str, dest: Path) -> None:
    """Stream one file from *url* to *dest*, skipping if already complete."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        _stream_to_file(url, tmp)
        tmp.rename(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def download_opentargets_dataset(
    dataset_name: str,
    dest_dir: str | Path,
    release: str = "latest",
    workers: int = 8,
) -> Path:
    """Download a single OpenTargets Platform dataset from the EBI FTP mirror.

    The dataset is a directory of Parquet files.  If a local copy already
    exists (contains ``*.parquet`` files or ``_SUCCESS``), the download is
    skipped without re-fetching.

    Args:
        dataset_name: Folder name of the dataset (e.g. ``"target"``,
            ``"evidence_chembl"``).  The alias ``"literaturel2g_prediction"``
            is automatically resolved to ``"l2g_prediction"``.
        dest_dir: Root directory; the dataset lands in ``{dest_dir}/{dataset_name}/``.
        release: Release tag such as ``"25.12"`` or ``"latest"`` (default).
        workers: Number of parallel download threads (default 8).

    Returns:
        Local path to the downloaded dataset directory.

    Raises:
        ValueError: If the dataset is not found in the given release.
    """
    resolved_name = _OT_DATASET_ALIASES.get(dataset_name, dataset_name)

    if release == "latest":
        release = get_latest_opentargets_release()

    dest = Path(dest_dir) / dataset_name
    if _is_downloaded(dest):
        print(f"[skip] {dataset_name} already present at {dest}")
        return dest

    dest.mkdir(parents=True, exist_ok=True)

    base_url = f"{_OT_FTP_BASE}/{release}/output/{resolved_name}/"
    try:
        items = _list_ftp_dir(base_url)
    except Exception as exc:
        raise ValueError(
            f"Dataset '{resolved_name}' not found in release {release}: {exc}"
        ) from exc

    # Collect only parquet files (skip _SUCCESS; we write our own marker)
    to_download: list[tuple[str, Path]] = []
    for item in items:
        if item.startswith("/") or item == "../":
            continue
        filename = item.lstrip("/").split("/")[-1]
        if filename.endswith(".parquet"):
            to_download.append((base_url + filename, dest / filename))

    if not to_download:
        raise ValueError(
            f"No parquet files found for '{resolved_name}' at {base_url}"
        )

    # Determine how many are already complete (resume support)
    already = sum(1 for _, p in to_download if p.exists() and p.stat().st_size > 0)
    total = len(to_download)
    print(f"[download] {dataset_name}  ({total} files, {already} cached, release={release})")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_download_single_file, url, path): path.name
            for url, path in to_download
        }
        done = already
        for future in concurrent.futures.as_completed(futures):
            future.result()  # re-raises on error
            done += 1
            print(f"  {dataset_name}: {done}/{total}", end="\r", flush=True)
    print()

    # Write atomic completion marker
    (dest / _SUCCESS_MARKER).write_text("ok")
    return dest


def download_opentargets_datasets(
    datasets: Sequence[str],
    dest_dir: str | Path,
    release: str = "latest",
    workers: int = 8,
) -> dict[str, Path]:
    """Download multiple OpenTargets Platform datasets sequentially.

    Resolves the release tag once and iterates over all dataset names.
    Failed individual downloads are logged but do not abort the rest.

    Args:
        datasets: Iterable of dataset names to download.
        dest_dir: Root directory; each dataset lands in ``{dest_dir}/{name}/``.
        release: Release tag or ``"latest"`` (default).
        workers: Parallel download threads per dataset (default 8).

    Returns:
        Mapping of ``dataset_name -> local_path`` for successful downloads.
    """
    if release == "latest":
        release = get_latest_opentargets_release()
        print(f"Using OpenTargets release: {release}")

    dest_dir = Path(dest_dir)
    results: dict[str, Path] = {}
    failed: list[str] = []

    for i, name in enumerate(datasets, 1):
        print(f"\n[{i}/{len(list(datasets))}] {name}")
        try:
            path = download_opentargets_dataset(name, dest_dir, release=release, workers=workers)
            results[name] = path
        except Exception as exc:
            print(f"[error] {name}: {exc}")
            failed.append(name)

    print(f"\n--- Summary ---")
    print(f"Downloaded : {len(results)}/{len(list(datasets))}")
    if failed:
        print(f"Failed     : {failed}")
    return results


@dataclass(frozen=True)
class TxDataFile:
    """Descriptor for a TxData CSV file.

    Attributes:
        name: Target filename on disk.
        url: Source URL to download from.
    """

    name: str
    url: str


TXDATA_CSVS: tuple[TxDataFile, ...] = (
    TxDataFile(name="kg.csv", url="https://dataverse.harvard.edu/api/access/datafile/7144484"),
    TxDataFile(name="node.csv", url="https://dataverse.harvard.edu/api/access/datafile/7144482"),
    TxDataFile(name="edges.csv", url="https://dataverse.harvard.edu/api/access/datafile/7144483"),
)


def download_txdata_csvs(data_folder_path: str | Path) -> list[Path]:
    """Download the TxData CSV files into a target folder.

    This is a small, dependency-free helper that mirrors the dataset URLs
    used in ``TxData`` but avoids importing heavy libraries.

    Args:
        data_folder_path: Target directory where the CSV files are stored.

    Returns:
        A list of local paths for the downloaded (or already existing) files.
    """

    target_dir = Path(data_folder_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    local_paths: list[Path] = []
    for file_info in TXDATA_CSVS:
        dest = target_dir / file_info.name
        if dest.exists():
            print(f"Found local copy: {dest}")
        else:
            print(f"Downloading {file_info.name}...")
            _download_file(file_info.url, dest)
            print(f"Saved to {dest}")
        local_paths.append(dest)

    return local_paths


def _download_file(url: str, dest: Path) -> None:
    """Download a URL to a local destination using the standard library."""

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request) as response, dest.open("wb") as handle:
        handle.write(response.read())


def add_disease_anatomy_relationships(
    nodes_path: str | Path,
    edges_path: str | Path,
    disease_files_dir: str | Path,
    output_nodes_path: str | Path,
    output_edges_path: str | Path,
    relation: str = "disease_anatomy",
    display_relation: str = "associated with",
) -> tuple[int, int, int]:
    """Add missing disease/anatomy nodes and edges from `data/disease_files`.

    The anatomy name is derived from each CSV filename (e.g. `adrenal_gland.csv`).
    The function appends only missing records and leaves existing rows unchanged.

    Args:
        nodes_path: Path to node table (`.tab` or `.csv`).
        edges_path: Path to edge table (`.csv`).
        disease_files_dir: Directory with disease area CSV files.
        output_nodes_path: Output path for updated nodes.
        output_edges_path: Output path for updated edges.
        relation: Relation value for new edges.
        display_relation: Display relation value for new edges.

    Returns:
        `(new_nodes_count, new_edges_count, processed_files_count)`.
    """

    nodes_path = Path(nodes_path)
    edges_path = Path(edges_path)
    disease_files_dir = Path(disease_files_dir)
    output_nodes_path = Path(output_nodes_path)
    output_edges_path = Path(output_edges_path)

    node_sep = "\t" if nodes_path.suffix == ".tab" else ","
    output_node_sep = "\t" if output_nodes_path.suffix == ".tab" else ","

    nodes = pd.read_csv(nodes_path, sep=node_sep).copy()
    edges = pd.read_csv(edges_path).copy()

    required_node_cols = {"node_index", "node_id", "node_type", "node_name", "node_source"}
    required_edge_cols = {"relation", "display_relation", "x_index", "y_index"}
    if not required_node_cols.issubset(nodes.columns):
        missing = required_node_cols - set(nodes.columns)
        raise ValueError(f"nodes file missing columns: {missing}")
    if not required_edge_cols.issubset(edges.columns):
        missing = required_edge_cols - set(edges.columns)
        raise ValueError(f"edges file missing columns: {missing}")

    nodes["node_id"] = nodes["node_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    nodes["node_name_lc"] = nodes["node_name"].astype(str).str.strip().str.lower()

    node_ids = set(nodes["node_id"])
    next_node_index = int(nodes["node_index"].max()) + 1
    existing_edges = set(
        zip(
            edges["relation"].astype(str),
            edges["x_index"].astype(int),
            edges["y_index"].astype(int),
        )
    )

    disease_index_by_id = {
        row.node_id: int(row.node_index)
        for row in nodes.loc[nodes["node_type"] == "disease", ["node_id", "node_index"]].itertuples(index=False)
    }
    anatomy_index_by_name = {
        row.node_name_lc: int(row.node_index)
        for row in nodes.loc[nodes["node_type"] == "anatomy", ["node_name_lc", "node_index"]].itertuples(index=False)
    }

    new_nodes = 0
    new_edges = 0
    processed_files = 0

    for disease_file in sorted(disease_files_dir.glob("*.csv")):
        processed_files += 1
        area_name = disease_file.stem.replace("_", " ").strip()
        area_name_lc = area_name.lower()

        if area_name_lc in anatomy_index_by_name:
            anatomy_index = anatomy_index_by_name[area_name_lc]
        else:
            anatomy_id = f"ANATOMY_{disease_file.stem.upper()}"
            while anatomy_id in node_ids:
                anatomy_id = f"{anatomy_id}_X"

            nodes.loc[len(nodes)] = {
                "node_index": next_node_index,
                "node_id": anatomy_id,
                "node_type": "anatomy",
                "node_name": area_name,
                "node_source": "DISEASE_FILES",
                "node_name_lc": area_name_lc,
            }
            anatomy_index = next_node_index
            anatomy_index_by_name[area_name_lc] = anatomy_index
            node_ids.add(anatomy_id)
            next_node_index += 1
            new_nodes += 1

        area_df = pd.read_csv(disease_file)
        if "node_id" not in area_df.columns:
            raise ValueError(f"{disease_file} missing required column: node_id")

        for row in area_df.itertuples(index=False):
            disease_id = str(getattr(row, "node_id"))
            if disease_id.endswith(".0"):
                disease_id = disease_id[:-2]

            if disease_id not in disease_index_by_id:
                disease_name = getattr(row, "node_name", disease_id)
                disease_source = getattr(row, "node_source", "MONDO")
                nodes.loc[len(nodes)] = {
                    "node_index": next_node_index,
                    "node_id": disease_id,
                    "node_type": "disease",
                    "node_name": disease_name,
                    "node_source": disease_source,
                    "node_name_lc": str(disease_name).strip().lower(),
                }
                disease_index_by_id[disease_id] = next_node_index
                node_ids.add(disease_id)
                next_node_index += 1
                new_nodes += 1

            x_index = disease_index_by_id[disease_id]
            edge_key = (relation, x_index, anatomy_index)
            if edge_key not in existing_edges:
                edges.loc[len(edges)] = {
                    "relation": relation,
                    "display_relation": display_relation,
                    "x_index": x_index,
                    "y_index": anatomy_index,
                }
                existing_edges.add(edge_key)
                new_edges += 1

    nodes = nodes.drop(columns=["node_name_lc"])
    nodes.to_csv(output_nodes_path, sep=output_node_sep, index=False)
    edges.to_csv(output_edges_path, index=False)
    return new_nodes, new_edges, processed_files
