"""Pin bionty ontology source versions for TxGNN KG reproducibility.

Run this script once after initialising a fresh LaminDB instance to lock the
exact ontology releases used when building the TxGNN knowledge graph.

Usage::

    uv run python reproduce/register_ontology_sources.py
    uv run python reproduce/register_ontology_sources.py --lamin-instance myorg/myinstance
    uv run python reproduce/register_ontology_sources.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Pinned source specification
# Each tuple: (registry_attr, source_name, organism, version)
# registry_attr must be an attribute on the bionty module, e.g. "Gene".
# ---------------------------------------------------------------------------
_PINNED_SOURCES: list[tuple[str, str, str, str]] = [
    # Gene: Ensembl human release-114
    ("Gene", "ensembl", "human", "release-114"),
    # Disease: Mondo 2026-01-06
    ("Disease", "mondo", "all", "2026-01-06"),
    # Pathway: Gene Ontology 2025-10-10
    ("Pathway", "go", "all", "2025-10-10"),
    # CellType: Cell Ontology 2025-12-17
    ("CellType", "cl", "all", "2025-12-17"),
    # Tissue: UBERON 2025-12-04
    ("Tissue", "uberon", "all", "2025-12-04"),
    # Phenotype: Human Phenotype Ontology 2026-01-08
    ("Phenotype", "hp", "human", "2026-01-08"),
    # CellLine: Cellosaurus 53.0
    ("CellLine", "cellosaurus", "all", "53.0"),
]


@dataclass
class _PinResult:
    registry: str
    source_name: str
    organism: str
    version: str
    status: str  # "pinned" | "already_current" | "skipped" | "error"
    message: str = ""


def register_ontology_sources(
    lamin_instance: str | None = None,
    dry_run: bool = False,
) -> list[_PinResult]:
    """Pin bionty ontology source versions in the connected LaminDB instance.

    Args:
        lamin_instance: Optional LaminDB instance slug (e.g. ``"myorg/kg"``).
            If provided, connects to this instance before running.
        dry_run: If ``True``, report what *would* be pinned without writing.

    Returns:
        List of :class:`_PinResult` with one entry per source.
    """
    try:
        import lamindb as ln  # noqa: F401
        import bionty as bt
        from bionty.core import sync_public_sources
    except ImportError as exc:
        raise ImportError(
            "Missing lamindb dependencies. "
            "Install with: uv pip install lamindb bionty"
        ) from exc

    if lamin_instance:
        ln.connect(lamin_instance)

    # First, make sure all public sources from sources.yaml are registered in
    # the instance's Source registry (does not change currently_used flags).
    if not dry_run:
        sync_public_sources(update_currently_used=False)

    results: list[_PinResult] = []

    for registry_attr, source_name, organism, version in _PINNED_SOURCES:
        registry = getattr(bt, registry_attr, None)
        if registry is None:
            results.append(
                _PinResult(
                    registry=registry_attr,
                    source_name=source_name,
                    organism=organism,
                    version=version,
                    status="error",
                    message=f"bionty.{registry_attr} not found",
                )
            )
            continue

        # Check if a source record already exists with currently_used=True at
        # this exact version.
        existing = bt.Source.filter(
            entity=f"bionty.{registry_attr}",
            name=source_name,
            organism=organism,
            version=version,
            currently_used=True,
        ).one_or_none()

        if existing is not None:
            results.append(
                _PinResult(
                    registry=registry_attr,
                    source_name=source_name,
                    organism=organism,
                    version=version,
                    status="already_current",
                    message=f"uid={existing.uid}",
                )
            )
            continue

        if dry_run:
            results.append(
                _PinResult(
                    registry=registry_attr,
                    source_name=source_name,
                    organism=organism,
                    version=version,
                    status="skipped",
                    message="dry_run=True",
                )
            )
            continue

        # add_source retrieves or creates the Source record; then we mark it
        # as currently_used (save() enforces uniqueness — clears other flags).
        try:
            kwargs: dict = {"version": version}
            # Only pass organism for registries that need it or accept "all".
            if organism != "all":
                kwargs["organism"] = organism
            else:
                kwargs["organism"] = "all"
            source = registry.add_source(source_name, **kwargs)
            source.currently_used = True
            source.save()
            results.append(
                _PinResult(
                    registry=registry_attr,
                    source_name=source_name,
                    organism=organism,
                    version=version,
                    status="pinned",
                    message=f"uid={source.uid}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                _PinResult(
                    registry=registry_attr,
                    source_name=source_name,
                    organism=organism,
                    version=version,
                    status="error",
                    message=str(exc),
                )
            )

    return results


def _report(results: list[_PinResult]) -> None:
    width = 60
    print("\n" + "=" * width)
    print("  TxGNN ontology source pinning report")
    print("=" * width)
    col = {"pinned": "✓", "already_current": "=", "skipped": "~", "error": "✗"}
    for r in results:
        icon = col.get(r.status, "?")
        label = f"bionty.{r.registry} / {r.source_name} / {r.organism} / {r.version}"
        print(f"  {icon}  {label:<50}  [{r.status}]")
        if r.message:
            print(f"       {r.message}")
    print("=" * width)
    n_err = sum(1 for r in results if r.status == "error")
    n_ok = sum(1 for r in results if r.status in ("pinned", "already_current"))
    print(f"  {n_ok}/{len(results)} sources OK, {n_err} errors")
    print("=" * width + "\n")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--lamin-instance",
        metavar="SLUG",
        default=None,
        help="LaminDB instance slug, e.g. 'myorg/myinstance'. "
        "Uses the currently connected instance if omitted.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be pinned without writing any records.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    results = register_ontology_sources(
        lamin_instance=args.lamin_instance,
        dry_run=args.dry_run,
    )
    _report(results)
    if any(r.status == "error" for r in results):
        sys.exit(1)
