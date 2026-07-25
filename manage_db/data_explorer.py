"""Small, bounded object-discovery helpers for the Jouvence data explorer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from google.cloud.storage import Client


@dataclass(frozen=True)
class ParquetListing:
    """A bounded Parquet URI listing and whether at least one result was omitted."""

    uris: tuple[str, ...]
    truncated: bool


def _split_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"not a GCS URI: {uri}")
    value = uri[5:]
    bucket, separator, prefix = value.partition("/")
    if not bucket:
        raise ValueError(f"GCS URI has no bucket: {uri}")
    return bucket, prefix.rstrip("/") if separator else ""


def _bounded(iterable: Iterable[str], limit: int) -> ParquetListing:
    found: list[str] = []
    for value in iterable:
        found.append(value)
        if len(found) > limit:
            return ParquetListing(tuple(found[:limit]), truncated=True)
    return ParquetListing(tuple(found), truncated=False)


def _raise_walk_error(error: OSError) -> None:
    raise error


def _local_parquets(root: Path) -> Iterable[str]:
    """Yield local Parquets deterministically without materializing a full tree."""

    if not root.exists():
        return
    for current, directories, filenames in os.walk(root, onerror=_raise_walk_error):
        directories.sort()
        for filename in sorted(filenames):
            if filename.endswith(".parquet"):
                yield str(Path(current) / filename)


def list_parquet_uris(
    uri: str | Path,
    *,
    limit: int,
    billing_project: str | None = None,
) -> ParquetListing:
    """List at most ``limit`` Parquet URIs with a server-side GCS cap.

    GCS uses ``match_glob`` plus ``max_results=limit+1``. Therefore the client
    never recursively materializes an unbounded object list merely to truncate
    it locally. Authentication, authorization, requester-pays, and network
    errors propagate to the caller instead of being presented as an empty root.
    """

    limit = int(limit)
    if not 1 <= limit <= 2_000:
        raise ValueError("limit must be between 1 and 2000")

    text = str(uri).rstrip("/")
    if text.startswith("gs://"):
        if not billing_project:
            raise ValueError("GCS listing requires a caller-owned billing_project")
        bucket_name, prefix = _split_gcs_uri(text)
        object_glob = f"{prefix}/**/*.parquet" if prefix else "**/*.parquet"
        client = Client()
        bucket = client.bucket(bucket_name, user_project=billing_project)
        blobs = client.list_blobs(
            bucket,
            prefix=f"{prefix}/" if prefix else None,
            match_glob=object_glob,
            max_results=limit + 1,
            page_size=min(limit + 1, 1_000),
        )
        return _bounded((f"gs://{bucket_name}/{blob.name}" for blob in blobs), limit)

    if "://" in text:
        raise ValueError(f"unsupported explorer URI scheme: {text}")
    return _bounded(_local_parquets(Path(text)), limit)
