"""Lightweight dataset download helpers for TxGNN."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import urllib.request


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
