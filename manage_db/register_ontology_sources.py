"""Pin bionty ontology source versions and pertdb sources for TxGNN KG reproducibility.

Two public functions:

- :func:`register_ontology_sources` — pin bionty ontology releases (Gene, Disease, …)
- :func:`register_pertdb_sources`   — register laminlabs/pertdata as the canonical
  source for pertdb registries (Compound, Biologic, GeneticPerturbation, …)

Call both once after initialising a fresh LaminDB instance::

    from manage_db.register_ontology_sources import (
        register_ontology_sources,
        register_pertdb_sources,
    )

    results = register_ontology_sources()
    pt_results = register_pertdb_sources()
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Bionty pinned sources
# Each entry: (registry_attr, source_name, organism, version)
# registry_attr is an attribute name on the bionty module, e.g. "Gene".
# ---------------------------------------------------------------------------
_BIONTY_PINNED: list[tuple[str, str, str, str]] = [
    ("Gene",      "ensembl",     "human", "release-114"),
    ("Disease",   "mondo",       "all",   "2026-01-06"),
    ("Pathway",   "go",          "all",   "2025-10-10"),
    ("CellType",  "cl",          "all",   "2025-12-17"),
    ("Tissue",    "uberon",      "all",   "2025-12-04"),
    ("Phenotype", "hp",          "human", "2026-01-08"),
    ("CellLine",  "cellosaurus", "all",   "53.0"),
]

# ---------------------------------------------------------------------------
# pertdb sources — canonical data lives in the laminlabs/pertdata instance.
# Each entry: (registry_attr, description)
# The version we record is today's date at setup time; update when the
# laminlabs/pertdata instance itself is updated.
# ---------------------------------------------------------------------------
_PERTDB_REGISTRIES: list[tuple[str, str]] = [
    ("Compound",              "Chemical compounds / drugs (ChEMBL, DrugBank)"),
    ("Biologic",              "Biologic perturbations (antibodies, cytokines, …)"),
    ("GeneticPerturbation",   "Genetic perturbations (CRISPR, RNAi, ORF, …)"),
    ("EnvironmentalPerturbation", "Environmental perturbations (media, conditions)"),
    ("CompoundPerturbation",  "Compound perturbation events (dose, context)"),
    ("CombinationPerturbation", "Combination perturbation events"),
]

_PERTDATA_INSTANCE = "laminlabs/pertdata"
_PERTDATA_WEBSITE  = "https://lamin.ai/laminlabs/pertdata"


# ---------------------------------------------------------------------------
# Result dataclass shared by both registration functions
# ---------------------------------------------------------------------------

@dataclass
class PinResult:
    """Outcome of a single source-pinning attempt."""

    registry: str
    source_name: str
    organism: str
    version: str
    status: str   # "pinned" | "already_current" | "skipped" | "error"
    message: str = field(default="")


# ---------------------------------------------------------------------------
# Bionty source registration
# ---------------------------------------------------------------------------

def register_ontology_sources(
    dry_run: bool = False,
) -> list[PinResult]:
    """Pin bionty ontology source versions in the connected LaminDB instance.

    Syncs all public sources from ``bionty/base/sources.yaml`` into the
    instance's Source registry first, then sets ``currently_used=True`` for
    each entry in :data:`_BIONTY_PINNED`.

    Args:
        dry_run: If ``True``, report what *would* be pinned without writing.

    Returns:
        List of :class:`PinResult` — one per pinned source.

    Example::

        import lamindb as ln
        ln.connect("myorg/myinstance")  # connect first

        from manage_db.register_ontology_sources import register_ontology_sources
        results = register_ontology_sources()
        for r in results:
            print(r.status, r.registry, r.version)
    """
    try:
        import bionty as bt
        from bionty.core import sync_public_sources
    except ImportError as exc:
        raise ImportError(
            "Missing dependencies — install with: uv pip install lamindb bionty"
        ) from exc

    # Ensure all public ontology releases from sources.yaml are registered in
    # the instance's Source registry (does not touch currently_used flags).
    if not dry_run:
        sync_public_sources(update_currently_used=False)

    results: list[PinResult] = []

    for registry_attr, source_name, organism, version in _BIONTY_PINNED:
        registry = getattr(bt, registry_attr, None)
        if registry is None:
            results.append(PinResult(
                registry=registry_attr, source_name=source_name,
                organism=organism, version=version, status="error",
                message=f"bionty.{registry_attr} not found",
            ))
            continue

        # Check if this exact version is already current.
        existing = bt.Source.filter(
            entity=f"bionty.{registry_attr}",
            name=source_name,
            organism=organism,
            version=version,
            currently_used=True,
        ).one_or_none()

        if existing is not None:
            results.append(PinResult(
                registry=registry_attr, source_name=source_name,
                organism=organism, version=version,
                status="already_current", message=f"uid={existing.uid}",
            ))
            continue

        if dry_run:
            results.append(PinResult(
                registry=registry_attr, source_name=source_name,
                organism=organism, version=version,
                status="skipped", message="dry_run=True",
            ))
            continue

        try:
            kwargs: dict = {"version": version, "organism": organism}
            source = registry.add_source(source_name, **kwargs)
            source.currently_used = True
            source.save()
            results.append(PinResult(
                registry=registry_attr, source_name=source_name,
                organism=organism, version=version,
                status="pinned", message=f"uid={source.uid}",
            ))
        except Exception as exc:  # noqa: BLE001
            results.append(PinResult(
                registry=registry_attr, source_name=source_name,
                organism=organism, version=version,
                status="error", message=str(exc),
            ))

    return results


# ---------------------------------------------------------------------------
# pertdb source registration
# ---------------------------------------------------------------------------

def register_pertdb_sources(
    version: str | None = None,
    dry_run: bool = False,
) -> list[PinResult]:
    """Register laminlabs/pertdata as the canonical source for pertdb registries.

    For each pertdb registry listed in :data:`_PERTDB_REGISTRIES`, this
    creates (or retrieves) a :class:`bionty.Source` record pointing to the
    ``laminlabs/pertdata`` LaminDB instance and marks it as ``currently_used``.

    Unlike bionty registries, pertdb does not have a public ``sources.yaml``.
    The *version* here is the ISO date when you pinned the source; update it
    when pulling a fresh snapshot from ``laminlabs/pertdata``.

    Args:
        version: Version string for the pertdata snapshot, e.g. ``"2026-03-02"``.
            Defaults to today's date (``datetime.date.today().isoformat()``).
        dry_run: If ``True``, report what *would* be registered without writing.

    Returns:
        List of :class:`PinResult` — one per pertdb registry.

    Example::

        import lamindb as ln
        ln.connect("myorg/myinstance")

        from manage_db.register_ontology_sources import register_pertdb_sources
        results = register_pertdb_sources(version="2026-03-02")
        for r in results:
            print(r.status, r.registry)

    Cross-instance query (read compounds from laminlabs/pertdata)::

        import pertdb as pt
        compounds = pt.Compound.connect("laminlabs/pertdata").df()
    """
    import datetime

    try:
        import bionty as bt
        import pertdb as pt  # noqa: F401 (confirms pertdb is installed)
    except ImportError as exc:
        raise ImportError(
            "Missing dependencies — install with: uv pip install lamindb bionty pertdb"
        ) from exc

    if version is None:
        version = datetime.date.today().isoformat()

    results: list[PinResult] = []

    for registry_attr, description in _PERTDB_REGISTRIES:
        entity = f"pertdb.{registry_attr}"

        # Check if this entity/version is already registered as currently_used.
        existing = bt.Source.filter(
            entity=entity,
            name=_PERTDATA_INSTANCE,
            organism="all",
            version=version,
            currently_used=True,
        ).one_or_none()

        if existing is not None:
            results.append(PinResult(
                registry=registry_attr, source_name=_PERTDATA_INSTANCE,
                organism="all", version=version,
                status="already_current", message=f"uid={existing.uid}",
            ))
            continue

        if dry_run:
            results.append(PinResult(
                registry=registry_attr, source_name=_PERTDATA_INSTANCE,
                organism="all", version=version,
                status="skipped", message="dry_run=True",
            ))
            continue

        try:
            source, created = bt.Source.objects.get_or_create(
                entity=entity,
                name=_PERTDATA_INSTANCE,
                organism="all",
                version=version,
                defaults={
                    "description": description,
                    "source_website": _PERTDATA_WEBSITE,
                    "currently_used": True,
                },
            )
            if not created:
                # Record exists but currently_used may be False — update it.
                source.currently_used = True
                source.description = description
                source.source_website = _PERTDATA_WEBSITE
                source.save()

            results.append(PinResult(
                registry=registry_attr, source_name=_PERTDATA_INSTANCE,
                organism="all", version=version,
                status="pinned" if created else "already_current",
                message=f"uid={source.uid}",
            ))
        except Exception as exc:  # noqa: BLE001
            results.append(PinResult(
                registry=registry_attr, source_name=_PERTDATA_INSTANCE,
                organism="all", version=version,
                status="error", message=str(exc),
            ))

    return results


# ---------------------------------------------------------------------------
# Shared pretty-printer
# ---------------------------------------------------------------------------

def print_results(results: list[PinResult], title: str = "Source registration report") -> None:
    """Pretty-print a list of :class:`PinResult` records."""
    width = 70
    icons = {"pinned": "✓", "already_current": "=", "skipped": "~", "error": "✗"}
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")
    for r in results:
        icon  = icons.get(r.status, "?")
        label = f"{r.registry:<35} {r.source_name}/{r.organism}/{r.version}"
        print(f"  {icon}  {label}")
        if r.message:
            print(f"       {r.message}")
    n_ok  = sum(1 for r in results if r.status in ("pinned", "already_current"))
    n_err = sum(1 for r in results if r.status == "error")
    print(f"{'=' * width}")
    print(f"  {n_ok}/{len(results)} OK  |  {n_err} errors")
    print(f"{'=' * width}\n")
