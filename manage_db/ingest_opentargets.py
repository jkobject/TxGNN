"""Phase 4 — OpenTargets Platform ingestion.

Downloads and processes OpenTargets Platform datasets into the Parquet edge/node
schema defined in ``kg_schema.py``.

Datasets handled
----------------
target       → nodes/gene.parquet             (Ensembl IDs + xrefs)
disease      → nodes/disease.parquet          (EFO IDs + xrefs)
drug         → nodes/molecule.parquet         (ChEMBL IDs + xrefs)
interaction  → edges/protein_interacts_protein.parquet
evidence     → edges/disease_associated_gene.parquet
             → edges/molecule_treats_disease.parquet
             → edges/molecule_contraindicates_disease.parquet
             → edges/disease_involves_pathway.parquet
go           → nodes/pathway.parquet          (GO terms merged with Reactome)
             → edges/pathway_contains_gene.parquet
reactome     → nodes/pathway.parquet          (Reactome pathways)
             → edges/pathway_child_of_pathway.parquet
literature   → nodes/paper.parquet            (PubMed IDs)
             → edges/paper_mentions_gene.parquet
             → edges/paper_mentions_disease.parquet
             → edges/paper_mentions_molecule.parquet
indication   → edges/molecule_treats_disease.parquet
             → edges/molecule_contraindicates_disease.parquet

Usage
-----
    uv run python -m manage_db.ingest_opentargets \\
        --data-dir ./data \\
        --release latest \\
        [--datasets target disease drug interaction evidence go reactome literature indication]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

try:
    from .kg_schema import Credibility, NodeType
except ImportError:
    from kg_schema import Credibility, NodeType  # type: ignore[no-redef]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME = "OpenTargets"

# OpenTargets datatypeId → credibility score
DATATYPE_CREDIBILITY: dict[str, int] = {
    # Established / curated
    "known_drug":            Credibility.ESTABLISHED_FACT,
    "chembl":                Credibility.ESTABLISHED_FACT,
    "expression_atlas":      Credibility.ESTABLISHED_FACT,
    "eva":                   Credibility.ESTABLISHED_FACT,   # ClinVar via EVA
    "clingen":               Credibility.ESTABLISHED_FACT,
    "cancer_gene_census":    Credibility.ESTABLISHED_FACT,
    "orphanet":              Credibility.ESTABLISHED_FACT,
    "gene2phenotype":        Credibility.ESTABLISHED_FACT,
    "uniprot_variants":      Credibility.ESTABLISHED_FACT,
    "reactome":              Credibility.ESTABLISHED_FACT,
    # Multi-evidence / moderately supported
    "genetic_association":   Credibility.MULTI_EVIDENCE,
    "somatic_mutation":      Credibility.MULTI_EVIDENCE,
    "ot_genetics_portal":    Credibility.MULTI_EVIDENCE,
    "intogen":               Credibility.MULTI_EVIDENCE,
    "crispr_screen":         Credibility.MULTI_EVIDENCE,
    "l2g":                   Credibility.MULTI_EVIDENCE,
    "eva_somatic":           Credibility.MULTI_EVIDENCE,
    # Single / predicted evidence
    "europepmc":             Credibility.SINGLE_EVIDENCE,
    "phenodigm":             Credibility.SINGLE_EVIDENCE,
    "progeny":               Credibility.SINGLE_EVIDENCE,
    "slapenrich":            Credibility.SINGLE_EVIDENCE,
    "sysbio":                Credibility.SINGLE_EVIDENCE,
    "literature":            Credibility.SINGLE_EVIDENCE,
}

# Evidence datatypeId → canonical edge relation (gene-disease direction)
EVIDENCE_GENE_DISEASE_RELATIONS: set[str] = {
    "genetic_association",
    "somatic_mutation",
    "ot_genetics_portal",
    "intogen",
    "crispr_screen",
    "l2g",
    "eva",
    "eva_somatic",
    "clingen",
    "cancer_gene_census",
    "gene2phenotype",
    "orphanet",
    "uniprot_variants",
    "phenodigm",
    "literature",
    "europepmc",
    "sysbio",
    "expression_atlas",
}
EVIDENCE_DRUG_DISEASE_TYPES: set[str] = {"known_drug", "chembl", "cancer_biomarkers"}
EVIDENCE_PATHWAY_DISEASE_TYPES: set[str] = {"reactome", "progeny", "slapenrich", "affected_pathway"}

# Additional datatypeId credibility entries (discovered from real OT data)
DATATYPE_CREDIBILITY.update({
    "genetic_literature":  Credibility.SINGLE_EVIDENCE,
    "affected_pathway":    Credibility.MULTI_EVIDENCE,
    "animal_model":        Credibility.MULTI_EVIDENCE,
    "rna_expression":      Credibility.ESTABLISHED_FACT,
    "gene_burden":         Credibility.MULTI_EVIDENCE,
    "gwas_credible_sets":  Credibility.MULTI_EVIDENCE,
    "crispr":              Credibility.MULTI_EVIDENCE,
    "cancer_biomarkers":   Credibility.ESTABLISHED_FACT,
})

EVIDENCE_GENE_DISEASE_RELATIONS.update({
    "genetic_literature",
    "animal_model",
    "rna_expression",
    "gene_burden",
    "gwas_credible_sets",
    "crispr",
})


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _to_list(val) -> list:
    """Coerce a pandas/numpy array or None to a plain Python list."""
    if val is None:
        return []
    try:
        # numpy / pandas arrays: len() works but bool() raises on multi-element
        return list(val)
    except TypeError:
        return [val] if val else []


# ---------------------------------------------------------------------------
# Parquet I/O helpers
# ---------------------------------------------------------------------------

def _read_parquet_dir(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    """Read all .parquet files in *path* into one DataFrame."""
    files = sorted(path.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {path}")
    frames: list[pd.DataFrame] = []
    for f in files:
        try:
            df = pd.read_parquet(f, columns=columns)
            frames.append(df)
        except Exception as exc:
            log.warning("Could not read %s: %s", f, exc)
    if not frames:
        raise RuntimeError(f"All parquet files in {path} failed to load")
    return pd.concat(frames, ignore_index=True)


def _read_parquet_dir_chunked(
    path: Path,
    columns: list[str] | None = None,
    chunksize: int = 500_000,
) -> Iterator[pd.DataFrame]:
    """Yield chunks from all .parquet files in *path*."""
    import pyarrow.parquet as pq

    files = sorted(path.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {path}")
    for f in files:
        try:
            pf = pq.ParquetFile(f)
            for batch in pf.iter_batches(batch_size=chunksize, columns=columns):
                yield batch.to_pandas()
        except Exception as exc:
            log.warning("Could not read %s: %s", f, exc)


def _merge_parquet(new_df: pd.DataFrame, out_path: Path, dedup_cols: list[str]) -> None:
    """Append *new_df* to *out_path* (create if absent), deduplicating on *dedup_cols*."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df.copy()
    combined = combined.drop_duplicates(subset=dedup_cols, keep="first")
    combined.reset_index(drop=True).to_parquet(out_path, index=False)
    log.info("  saved %s  (%d rows)", out_path.name, len(combined))


def _save_edge_df(df: pd.DataFrame, out_dir: Path, relation: str) -> None:
    """Merge edge DataFrame into the appropriate Parquet file."""
    if df.empty:
        return
    out_path = out_dir / "edges" / f"{relation}.parquet"
    _merge_parquet(df, out_path, dedup_cols=["x_id", "y_id", "relation", "source"])


def _save_node_df(df: pd.DataFrame, out_dir: Path, node_type: str) -> None:
    """Merge node DataFrame into the appropriate Parquet file."""
    if df.empty:
        return
    out_path = out_dir / "nodes" / f"{node_type}.parquet"
    _merge_parquet(df, out_path, dedup_cols=["id"])


def _write_chunk(df: pd.DataFrame, chunk_dir: Path) -> None:
    """Append *df* as a new numbered parquet file in *chunk_dir* (no read-back)."""
    if df.empty:
        return
    chunk_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(chunk_dir.glob("*.parquet")))
    df.to_parquet(chunk_dir / f"{n:06d}.parquet", index=False)


def _finalize_chunks(
    chunk_dir: Path,
    out_path: Path,
    dedup_cols: list[str],
) -> int:
    """Concat all chunk files, dedup, write to *out_path*, remove chunk_dir.

    Returns the number of rows written, or 0 if no chunks exist.
    """
    import shutil

    files = sorted(chunk_dir.glob("*.parquet"))
    if not files:
        return 0
    combined = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    combined = combined.drop_duplicates(subset=dedup_cols, keep="first")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.reset_index(drop=True).to_parquet(out_path, index=False)
    shutil.rmtree(chunk_dir)
    log.info("  saved %s  (%d rows)", out_path.name, len(combined))
    return len(combined)


# ---------------------------------------------------------------------------
# Edge construction helpers
# ---------------------------------------------------------------------------

def _make_edge(
    x_id: str,
    x_type: str,
    y_id: str,
    y_type: str,
    relation: str,
    display_relation: str,
    source: str,
    credibility: int,
    **extra,
) -> dict:
    row = {
        "x_id": x_id,
        "x_type": x_type,
        "y_id": y_id,
        "y_type": y_type,
        "relation": relation,
        "display_relation": display_relation,
        "source": source,
        "credibility": credibility,
    }
    row.update(extra)
    return row


def _credibility_from_score(score: float, datatype: str) -> int:
    """Combine OT score with datatype-based credibility."""
    base = DATATYPE_CREDIBILITY.get(datatype, Credibility.SINGLE_EVIDENCE)
    # Bump up if score is very high and base allows it
    if base < Credibility.ESTABLISHED_FACT and score >= 0.75:
        return min(base + 1, Credibility.ESTABLISHED_FACT)
    return base


# ---------------------------------------------------------------------------
# 1. Target ingestion → gene nodes
# ---------------------------------------------------------------------------

def ingest_targets(ot_dir: Path, out_dir: Path) -> int:
    """Ingest OT target dataset → gene nodes.

    Returns number of gene nodes written.
    """
    target_path = ot_dir / "target"
    log.info("Loading target dataset from %s", target_path)

    df = _read_parquet_dir(
        target_path,
        columns=["id", "approvedSymbol", "approvedName", "biotype",
                 "proteinIds", "dbXrefs"],
    )
    log.info("  %d target rows", len(df))

    rows = []
    for _, row in df.iterrows():
        gene_id = str(row["id"]).strip()
        if not gene_id.startswith("ENSG"):
            continue

        # Extract UniProt (prefer Swiss-Prot / reviewed; OT source = 'uniprot_swissprot')
        uniprot_id = None
        protein_ids = _to_list(row.get("proteinIds"))
        for p in protein_ids:
            if isinstance(p, dict):
                src = p.get("source", "")
                pid = p.get("id", "")
                if src == "uniprot_swissprot" and pid:
                    uniprot_id = pid
                    break
        if uniprot_id is None:
            for p in protein_ids:
                if isinstance(p, dict) and p.get("source", "").startswith("uniprot") and p.get("id"):
                    uniprot_id = p["id"]
                    break

        # Extract HGNC and NCBI gene IDs from dbXrefs list-of-structs
        hgnc_id = ncbi_gene_id = None
        db_xrefs = _to_list(row.get("dbXrefs"))
        for xref in db_xrefs:
                if not isinstance(xref, dict):
                    continue
                src = xref.get("source", "")
                xid = str(xref.get("id", "")).strip()
                if src == "HGNC" and not hgnc_id:
                    hgnc_id = xid
                elif src in ("NCBIGene", "EntrezGene") and not ncbi_gene_id:
                    ncbi_gene_id = xid

        rows.append({
            "id":            gene_id,
            "name":          str(row.get("approvedSymbol") or "").strip(),
            "description":   str(row.get("approvedName") or "").strip(),
            "biotype":       str(row.get("biotype") or "").strip(),
            "ncbi_gene_id":  ncbi_gene_id,
            "hgnc_id":       hgnc_id,
            "uniprot_id":    uniprot_id,
            "gene_name":     str(row.get("approvedSymbol") or "").strip(),
            "source":        SOURCE_NAME,
        })

    gene_df = pd.DataFrame(rows)
    _save_node_df(gene_df, out_dir, NodeType.GENE.value)
    log.info("  %d gene nodes saved", len(gene_df))
    return len(gene_df)


# ---------------------------------------------------------------------------
# 2. Disease ingestion → disease nodes
# ---------------------------------------------------------------------------

def ingest_diseases(ot_dir: Path, out_dir: Path) -> int:
    """Ingest OT disease dataset → disease nodes.

    Returns number of disease nodes written.
    """
    disease_path = ot_dir / "disease"
    log.info("Loading disease dataset from %s", disease_path)

    df = _read_parquet_dir(
        disease_path,
        columns=["id", "name", "description", "dbXRefs", "parents",
                 "therapeuticAreas"],
    )
    log.info("  %d disease rows", len(df))

    rows = []
    for _, row in df.iterrows():
        efo_id = str(row["id"]).strip()

        # Cross-references (dbXRefs is a list of plain strings like 'MONDO:0000510')
        mondo_id = omim_id = doid_id = icd10_code = mesh_id = None
        db_xrefs = _to_list(row.get("dbXRefs"))
        for xref in db_xrefs:
                xref_str = str(xref).strip()
                if xref_str.startswith("MONDO:"):
                    mondo_id = mondo_id or xref_str
                elif xref_str.startswith("OMIM:"):
                    omim_id = omim_id or xref_str.replace("OMIM:", "")
                elif xref_str.startswith("DOID:"):
                    doid_id = doid_id or xref_str
                elif xref_str.startswith("ICD10:"):
                    icd10_code = icd10_code or xref_str.replace("ICD10:", "")
                elif xref_str.startswith("MeSH:") or xref_str.startswith("MESH:"):
                    mesh_id = mesh_id or xref_str

        rows.append({
            "id":           efo_id,
            "name":         str(row.get("name") or "").strip(),
            "description":  str(row.get("description") or "").strip(),
            "mondo_id":     mondo_id,
            "omim_id":      omim_id,
            "doid_id":      doid_id,
            "icd10_code":   icd10_code,
            "mesh_id":      mesh_id,
            "source":       SOURCE_NAME,
        })

    disease_df = pd.DataFrame(rows)
    _save_node_df(disease_df, out_dir, NodeType.DISEASE.value)

    # Also save disease hierarchy edges (parents)
    hier_rows = []
    for _, row in df.iterrows():
        child_id = str(row["id"]).strip()
        for parent_id in _to_list(row.get("parents")):
                parent_id = str(parent_id).strip()
                if parent_id and parent_id != child_id:
                    hier_rows.append(_make_edge(
                        x_id=child_id, x_type=NodeType.DISEASE.value,
                        y_id=parent_id, y_type=NodeType.DISEASE.value,
                        relation="disease_subtype_of_disease",
                        display_relation="subtype of",
                        source=SOURCE_NAME,
                        credibility=Credibility.ESTABLISHED_FACT,
                    ))

    if hier_rows:
        _save_edge_df(pd.DataFrame(hier_rows), out_dir, "disease_subtype_of_disease")

    log.info("  %d disease nodes, %d hierarchy edges saved", len(disease_df), len(hier_rows))
    return len(disease_df)


# ---------------------------------------------------------------------------
# 3. Drug / molecule ingestion → molecule nodes
# ---------------------------------------------------------------------------

def ingest_drugs(ot_dir: Path, out_dir: Path) -> int:
    """Ingest OT drug/molecule dataset → molecule nodes.

    Returns number of molecule nodes written.
    """
    # OT 24.x+ uses 'drug_molecule'; older releases used 'molecule' or 'drug'
    for _candidate in ("drug_molecule", "molecule", "drug"):
        drug_path = ot_dir / _candidate
        if drug_path.exists():
            break
    else:
        log.warning("No molecule/drug dataset found in %s", ot_dir)
        return 0

    log.info("Loading drug dataset from %s", drug_path)

    df = _read_parquet_dir(
        drug_path,
        columns=["id", "name", "inchiKey", "drugType", "isApproved",
                 "maximumClinicalTrialPhase",
                 "hasBeenWithdrawn", "blackBoxWarning",
                 "crossReferences"],
    )
    log.info("  %d molecule rows", len(df))

    rows = []
    for _, row in df.iterrows():
        chembl_id = str(row["id"]).strip()
        if not chembl_id.startswith("CHEMBL"):
            continue

        # crossReferences is a list of {source, ids} structs (not a dict)
        drugbank_id = pubchem_cid = cas_rn = None
        for xref in _to_list(row.get("crossReferences")):
            if not isinstance(xref, dict):
                continue
            src = str(xref.get("source") or "").lower()
            ids = _to_list(xref.get("ids"))
            first_id = str(ids[0]) if ids else None
            if src == "drugbank" and not drugbank_id:
                drugbank_id = first_id
            elif src in ("pubchem", "pubchemcid", "pubchem_cid") and not pubchem_cid:
                pubchem_cid = first_id
            elif src in ("cas", "cas_rn") and not cas_rn:
                cas_rn = first_id

        rows.append({
            "id":                          chembl_id,
            "name":                        str(row.get("name") or "").strip(),
            "description":                 "",   # not present in OT drug_molecule
            "drug_type":                   str(row.get("drugType") or "").strip(),
            "is_approved":                 bool(row.get("isApproved") or False),
            "max_clinical_trial_phase":    row.get("maximumClinicalTrialPhase"),
            "has_been_withdrawn":          bool(row.get("hasBeenWithdrawn") or False),
            "black_box_warning":           bool(row.get("blackBoxWarning") or False),
            "inchikey":                    str(row.get("inchiKey") or "").strip() or None,
            "drugbank_id":                 drugbank_id,
            "pubchem_cid":                 pubchem_cid,
            "cas_rn":                      cas_rn,
            "source":                      SOURCE_NAME,
        })

    mol_df = pd.DataFrame(rows)
    _save_node_df(mol_df, out_dir, NodeType.MOLECULE.value)
    log.info("  %d molecule nodes saved", len(mol_df))
    return len(mol_df)


# ---------------------------------------------------------------------------
# 4. Interaction ingestion → protein_interacts_protein edges
# ---------------------------------------------------------------------------

def ingest_interactions(ot_dir: Path, out_dir: Path) -> int:
    """Ingest OT interaction dataset → protein_interacts_protein edges.

    Returns number of edges written.
    """
    int_path = ot_dir / "interaction"
    if not int_path.exists():
        log.warning("'interaction' dataset not found in %s", ot_dir)
        return 0

    log.info("Loading interaction dataset from %s", int_path)

    chunk_dir = out_dir / ".chunks" / "protein_interacts_protein"
    n_chunks = 0

    for chunk in _read_parquet_dir_chunked(
        int_path,
        columns=["targetA", "targetB", "intA", "intB", "scoring", "sourceDatabase"],
        chunksize=500_000,
    ):
        rows = []
        for _, row in chunk.iterrows():
            # intA/intB are UniProt accessions; targetA/B are Ensembl IDs
            prot_a = str(row.get("intA") or "").strip()
            prot_b = str(row.get("intB") or "").strip()
            if not prot_a or not prot_b:
                continue
            # Skip self-loops
            if prot_a == prot_b:
                continue
            # Canonical ordering to deduplicate A-B vs B-A
            if prot_a > prot_b:
                prot_a, prot_b = prot_b, prot_a

            # 'scoring' is the field name in OT interaction dataset (not 'score')
            score = float(row.get("scoring") or 0.0)
            source_db = str(row.get("sourceDatabase") or SOURCE_NAME).strip()
            cred = _credibility_from_score(score, "genetic_association")

            rows.append(_make_edge(
                x_id=prot_a, x_type=NodeType.PROTEIN.value,
                y_id=prot_b, y_type=NodeType.PROTEIN.value,
                relation="protein_interacts_protein",
                display_relation="interacts with",
                source=f"OpenTargets/{source_db}",
                credibility=cred,
                score=round(score, 4),
            ))
        if rows:
            _write_chunk(pd.DataFrame(rows), chunk_dir)
            n_chunks += len(rows)

    out_path = out_dir / "edges" / "protein_interacts_protein.parquet"
    n_written = _finalize_chunks(
        chunk_dir, out_path,
        dedup_cols=["x_id", "y_id", "relation", "source"],
    )
    log.info("  %d PPI edges saved", n_written)
    return n_written


# ---------------------------------------------------------------------------
# 5. Evidence ingestion → disease_associated_gene + drug edges
# ---------------------------------------------------------------------------

def ingest_evidence(ot_dir: Path, out_dir: Path) -> dict[str, int]:
    """Ingest OT evidence datasets (evidence_*) into multiple edge Parquets.

    OT splits evidence into ~20 separate directories named evidence_<source>.
    Returns dict of {relation: count}.
    """
    import pyarrow.parquet as _pq

    ev_dirs = sorted(ot_dir.glob("evidence_*"))
    if not ev_dirs:
        log.warning("No 'evidence_*' datasets found in %s", ot_dir)
        return {}

    log.info("Found %d evidence directories", len(ev_dirs))

    chunks_base = out_dir / ".chunks"
    gd_chunks  = chunks_base / "disease_associated_gene"
    dd_chunks  = chunks_base / "molecule_treats_disease"
    pd_chunks  = chunks_base / "disease_involves_pathway"

    BASE_COLS = ["targetId", "diseaseId", "datatypeId", "datasourceId", "score"]

    for ev_path in ev_dirs:
        # Determine if this directory has a drugId column
        parquet_files = list(ev_path.glob("*.parquet"))
        if not parquet_files:
            continue
        try:
            schema_fields = {f.name for f in _pq.read_schema(parquet_files[0])}
        except Exception:
            schema_fields = set()

        cols = BASE_COLS + (["drugId"] if "drugId" in schema_fields else [])

        log.info("  Processing %s (%d files)", ev_path.name, len(parquet_files))
        for chunk in _read_parquet_dir_chunked(ev_path, columns=cols, chunksize=500_000):
            gene_disease_rows: list[dict] = []
            drug_disease_rows: list[dict] = []
            pathway_disease_rows: list[dict] = []

            for _, row in chunk.iterrows():
                target_id  = str(row.get("targetId") or "").strip()
                disease_id = str(row.get("diseaseId") or "").strip()
                dtype      = str(row.get("datatypeId") or "").strip()
                dsource    = str(row.get("datasourceId") or dtype).strip()
                score      = float(row.get("score") or 0.0)
                cred       = _credibility_from_score(score, dtype)

                if not target_id or not disease_id:
                    continue

                # ── Drug-disease evidence ────────────────────────────────────
                if dtype in EVIDENCE_DRUG_DISEASE_TYPES:
                    # OT uses top-level drugId field (not nested drug.id)
                    drug_id = str(row.get("drugId") or "").strip()
                    if not drug_id:
                        # fallback: some cancer_biomarkers rows have targetId as drug
                        drug_id = target_id if target_id.startswith("CHEMBL") else ""
                    if not drug_id:
                        continue

                    drug_disease_rows.append(_make_edge(
                        x_id=drug_id,
                        x_type=NodeType.MOLECULE.value,
                        y_id=disease_id,
                        y_type=NodeType.DISEASE.value,
                        relation="molecule_treats_disease",
                        display_relation="indication",
                        source=f"OpenTargets/{dsource}",
                        credibility=cred,
                        score=round(score, 4),
                    ))

                # ── Pathway-disease evidence ─────────────────────────────────
                elif dtype in EVIDENCE_PATHWAY_DISEASE_TYPES:
                    pathway_id = target_id
                    if pathway_id.startswith("R-HSA-"):
                        pathway_disease_rows.append(_make_edge(
                            x_id=disease_id, x_type=NodeType.DISEASE.value,
                            y_id=pathway_id, y_type=NodeType.PATHWAY.value,
                            relation="disease_involves_pathway",
                            display_relation="involves pathway",
                            source=f"OpenTargets/{dsource}",
                            credibility=cred,
                            score=round(score, 4),
                        ))
                    elif target_id.startswith("ENSG"):
                        gene_disease_rows.append(_make_edge(
                            x_id=disease_id, x_type=NodeType.DISEASE.value,
                            y_id=target_id, y_type=NodeType.GENE.value,
                            relation="disease_associated_gene",
                            display_relation="associated gene",
                            source=f"OpenTargets/{dsource}",
                            credibility=cred,
                            score=round(score, 4),
                        ))

                # ── Gene-disease evidence ────────────────────────────────────
                elif dtype in EVIDENCE_GENE_DISEASE_RELATIONS:
                    if target_id.startswith("ENSG"):
                        gene_disease_rows.append(_make_edge(
                            x_id=disease_id, x_type=NodeType.DISEASE.value,
                            y_id=target_id, y_type=NodeType.GENE.value,
                            relation="disease_associated_gene",
                            display_relation="associated gene",
                            source=f"OpenTargets/{dsource}",
                            credibility=cred,
                            score=round(score, 4),
                        ))
                else:
                    # Unknown datatype — emit as gene-disease if IDs look right
                    if target_id.startswith("ENSG"):
                        gene_disease_rows.append(_make_edge(
                            x_id=disease_id, x_type=NodeType.DISEASE.value,
                            y_id=target_id, y_type=NodeType.GENE.value,
                            relation="disease_associated_gene",
                            display_relation="associated gene",
                            source=f"OpenTargets/{dsource}",
                            credibility=Credibility.SINGLE_EVIDENCE,
                            score=round(score, 4),
                        ))

            # Flush each chunk's rows immediately to temp files
            if gene_disease_rows:
                _write_chunk(pd.DataFrame(gene_disease_rows), gd_chunks)
            if drug_disease_rows:
                _write_chunk(pd.DataFrame(drug_disease_rows), dd_chunks)
            if pathway_disease_rows:
                _write_chunk(pd.DataFrame(pathway_disease_rows), pd_chunks)

    dedup_edge = ["x_id", "y_id", "relation", "source"]
    counts: dict[str, int] = {}
    n = _finalize_chunks(gd_chunks,  out_dir / "edges" / "disease_associated_gene.parquet",  dedup_edge)
    if n: counts["disease_associated_gene"] = n
    n = _finalize_chunks(dd_chunks,  out_dir / "edges" / "molecule_treats_disease.parquet",  dedup_edge)
    if n: counts["molecule_treats_disease"] = n
    n = _finalize_chunks(pd_chunks,  out_dir / "edges" / "disease_involves_pathway.parquet", dedup_edge)
    if n: counts["disease_involves_pathway"] = n

    log.info("  Evidence edges: %s", counts)
    return counts


# ---------------------------------------------------------------------------
# 6. GO ingestion → pathway nodes + pathway_contains_gene edges
# ---------------------------------------------------------------------------

def ingest_go(ot_dir: Path, out_dir: Path) -> tuple[int, int]:
    """Ingest GO annotations → pathway (GO) nodes + pathway_contains_gene edges.

    OT's go/ directory only contains GO term definitions (id, name).
    The gene↔GO associations live in target.go (a list-of-structs per gene).
    Strategy:
      1. Load go/ for term name lookup.
      2. Iterate target dataset reading the nested `go` field per gene.

    Returns (n_pathway_nodes, n_edges).
    """
    go_path     = ot_dir / "go"
    target_path = ot_dir / "target"

    # ── Step 1: build GO term name index ─────────────────────────────────────
    go_names: dict[str, str] = {}
    if go_path.exists():
        df_go = _read_parquet_dir(go_path, columns=["id", "name"])
        for _, r in df_go.iterrows():
            go_names[str(r["id"]).strip()] = str(r.get("name") or "")
        log.info("  Loaded %d GO term names", len(go_names))
    else:
        log.warning("'go' dataset not found in %s — term names will be empty", ot_dir)

    if not target_path.exists():
        log.warning("'target' dataset not found in %s — cannot extract GO associations", ot_dir)
        return len(go_names), 0

    log.info("Extracting GO associations from target.go  (chunked)")

    pathway_rows: list[dict] = []
    edge_rows: list[dict] = []
    seen_pathways: set[str] = set()

    for chunk in _read_parquet_dir_chunked(
        target_path,
        columns=["id", "go"],
        chunksize=50_000,
    ):
        for _, row in chunk.iterrows():
            gene_id = str(row.get("id") or "").strip()
            if not gene_id.startswith("ENSG"):
                continue

            go_entries = _to_list(row.get("go"))

            for entry in go_entries:
                if not isinstance(entry, dict):
                    continue
                go_id    = str(entry.get("id") or "").strip()
                evidence = str(entry.get("evidence") or "").strip()
                aspect   = str(entry.get("aspect") or "").strip()

                if not go_id:
                    continue

                if go_id not in seen_pathways:
                    seen_pathways.add(go_id)
                    pathway_rows.append({
                        "id":     go_id,
                        "name":   go_names.get(go_id, ""),
                        "aspect": aspect,
                        "go_id":  go_id,
                        "source": SOURCE_NAME,
                    })

                cred = (
                    Credibility.ESTABLISHED_FACT
                    if evidence in ("IDA", "IMP", "IGI", "IEP", "EXP", "TAS", "IC")
                    else Credibility.SINGLE_EVIDENCE
                )
                edge_rows.append(_make_edge(
                    x_id=go_id,   x_type=NodeType.PATHWAY.value,
                    y_id=gene_id, y_type=NodeType.GENE.value,
                    relation="pathway_contains_gene",
                    display_relation="contains gene",
                    source="OpenTargets/GO",
                    credibility=cred,
                    go_evidence=evidence,
                    go_aspect=aspect,
                ))

    if pathway_rows:
        _save_node_df(pd.DataFrame(pathway_rows), out_dir, NodeType.PATHWAY.value)
    if edge_rows:
        _save_edge_df(pd.DataFrame(edge_rows), out_dir, "pathway_contains_gene")

    log.info("  %d GO pathway nodes, %d pathway→gene edges", len(pathway_rows), len(edge_rows))
    return len(pathway_rows), len(edge_rows)


# ---------------------------------------------------------------------------
# 7. Reactome ingestion → pathway nodes + hierarchy edges
# ---------------------------------------------------------------------------

def ingest_reactome(ot_dir: Path, out_dir: Path) -> tuple[int, int]:
    """Ingest OT reactome dataset → pathway nodes + pathway_child_of_pathway edges.

    Returns (n_pathway_nodes, n_hierarchy_edges).
    """
    reactome_path = ot_dir / "reactome"
    if not reactome_path.exists():
        log.warning("'reactome' dataset not found in %s — skipping", ot_dir)
        return 0, 0

    log.info("Loading reactome dataset from %s", reactome_path)

    df = _read_parquet_dir(
        reactome_path,
        columns=["id", "label", "ancestors", "descendants", "children"],
    )
    log.info("  %d reactome pathway rows", len(df))

    pathway_rows: list[dict] = []
    hier_rows: list[dict] = []

    for _, row in df.iterrows():
        pathway_id = str(row["id"]).strip()
        label      = str(row.get("label") or "").strip()

        pathway_rows.append({
            "id":     pathway_id,
            "name":   label,
            "source": SOURCE_NAME,
        })

        # Children → pathway_child_of_pathway (child is_a parent)
        for child_id in _to_list(row.get("children")):
                child_id = str(child_id).strip()
                if child_id and child_id != pathway_id:
                    hier_rows.append(_make_edge(
                        x_id=child_id,  x_type=NodeType.PATHWAY.value,
                        y_id=pathway_id, y_type=NodeType.PATHWAY.value,
                        relation="pathway_child_of_pathway",
                        display_relation="child pathway of",
                        source=SOURCE_NAME,
                        credibility=Credibility.ESTABLISHED_FACT,
                    ))

    if pathway_rows:
        _save_node_df(pd.DataFrame(pathway_rows), out_dir, NodeType.PATHWAY.value)
    if hier_rows:
        _save_edge_df(pd.DataFrame(hier_rows), out_dir, "pathway_child_of_pathway")

    log.info("  %d Reactome pathway nodes, %d hierarchy edges", len(pathway_rows), len(hier_rows))
    return len(pathway_rows), len(hier_rows)


# ---------------------------------------------------------------------------
# 8. Literature ingestion → paper nodes + mention edges
# ---------------------------------------------------------------------------

def ingest_literature(ot_dir: Path, out_dir: Path) -> tuple[int, int]:
    """Ingest paper mentions from evidence_europepmc → paper nodes + mention edges.

    OT's literature_vector directory contains word embeddings, not paper mentions.
    Paper mentions are in evidence_europepmc which has targetId, diseaseId, and
    a `literature` column with lists of PMIDs.

    Returns (n_papers, n_mention_edges).
    """
    lit_path = ot_dir / "evidence_europepmc"
    if not lit_path.exists():
        log.warning("'evidence_europepmc' dataset not found in %s — skipping", ot_dir)
        return 0, 0

    log.info("Loading europepmc evidence from %s  (chunked)", lit_path)

    chunks_base   = out_dir / ".chunks"
    paper_chunks  = chunks_base / "paper"
    gene_chunks   = chunks_base / "paper_mentions_gene"
    dis_chunks    = chunks_base / "paper_mentions_disease"
    seen_papers: set[str] = set()

    for chunk in _read_parquet_dir_chunked(
        lit_path,
        columns=["targetId", "diseaseId", "literature", "publicationYear"],
        chunksize=200_000,
    ):
        paper_rows: list[dict] = []
        gene_mention_rows: list[dict] = []
        disease_mention_rows: list[dict] = []

        for _, row in chunk.iterrows():
            target_id  = str(row.get("targetId") or "").strip()
            disease_id = str(row.get("diseaseId") or "").strip()
            pmids      = _to_list(row.get("literature"))
            year       = row.get("publicationYear")

            for pmid in pmids:
                pmid = str(pmid).strip()
                if not pmid:
                    continue
                paper_id = f"PMID:{pmid}"

                if paper_id not in seen_papers:
                    seen_papers.add(paper_id)
                    paper_rows.append({
                        "id":     paper_id,
                        "year":   year,
                        "source": SOURCE_NAME,
                    })

                if target_id.startswith("ENSG"):
                    gene_mention_rows.append(_make_edge(
                        x_id=paper_id, x_type=NodeType.PAPER.value,
                        y_id=target_id, y_type=NodeType.GENE.value,
                        relation="paper_mentions_gene",
                        display_relation="mentions gene",
                        source="OpenTargets/europepmc",
                        credibility=Credibility.SINGLE_EVIDENCE,
                    ))

                if disease_id:
                    disease_mention_rows.append(_make_edge(
                        x_id=paper_id, x_type=NodeType.PAPER.value,
                        y_id=disease_id, y_type=NodeType.DISEASE.value,
                        relation="paper_mentions_disease",
                        display_relation="mentions disease",
                        source="OpenTargets/europepmc",
                        credibility=Credibility.SINGLE_EVIDENCE,
                    ))

        # Flush each chunk immediately to temp files
        if paper_rows:
            _write_chunk(pd.DataFrame(paper_rows), paper_chunks)
        if gene_mention_rows:
            _write_chunk(pd.DataFrame(gene_mention_rows), gene_chunks)
        if disease_mention_rows:
            _write_chunk(pd.DataFrame(disease_mention_rows), dis_chunks)

    n_papers = _finalize_chunks(
        paper_chunks, out_dir / "nodes" / f"{NodeType.PAPER.value}.parquet",
        dedup_cols=["id"],
    )
    n_gene = _finalize_chunks(
        gene_chunks, out_dir / "edges" / "paper_mentions_gene.parquet",
        dedup_cols=["x_id", "y_id", "relation", "source"],
    )
    n_dis = _finalize_chunks(
        dis_chunks, out_dir / "edges" / "paper_mentions_disease.parquet",
        dedup_cols=["x_id", "y_id", "relation", "source"],
    )
    total_mentions = n_gene + n_dis
    log.info("  %d papers, %d mention edges", n_papers, total_mentions)
    return n_papers, total_mentions


# ---------------------------------------------------------------------------
# 9. Indication ingestion → molecule_treats/contraindicates_disease
# ---------------------------------------------------------------------------

def ingest_indication(ot_dir: Path, out_dir: Path) -> tuple[int, int]:
    """Ingest OT indication dataset (EMA/FDA approved indications).

    Returns (n_indication_edges, n_contraindication_edges).
    """
    ind_path = ot_dir / "drug_indication"
    if not ind_path.exists():
        log.warning("'drug_indication' dataset not found in %s — skipping", ot_dir)
        return 0, 0

    log.info("Loading drug_indication dataset from %s", ind_path)

    df = _read_parquet_dir(
        ind_path,
        columns=["id", "approvedIndications", "indications"],
    )
    log.info("  %d indication rows", len(df))

    treat_rows: list[dict] = []
    contra_rows: list[dict] = []

    for _, row in df.iterrows():
        chembl_id = str(row["id"]).strip()
        if not chembl_id.startswith("CHEMBL"):
            continue

        # approvedIndications: list of disease EFO IDs
        approved = _to_list(row.get("approvedIndications"))
        for disease_id in approved:
                disease_id = str(disease_id).strip()
                if disease_id:
                    treat_rows.append(_make_edge(
                        x_id=chembl_id, x_type=NodeType.MOLECULE.value,
                        y_id=disease_id, y_type=NodeType.DISEASE.value,
                        relation="molecule_treats_disease",
                        display_relation="approved indication",
                        source=f"OpenTargets/indication",
                        credibility=Credibility.ESTABLISHED_FACT,
                    ))

        # indications: list of dicts with {disease: "<EFO_ID>", maxPhaseForIndication, ...}
        # (disease is a plain string EFO/MONDO ID, not a nested dict)
        for ind in _to_list(row.get("indications")):
                if not isinstance(ind, dict):
                    continue
                disease_id = str(ind.get("disease") or "").strip()
                max_phase = ind.get("maxPhaseForIndication") or 0
                if not disease_id:
                    continue

                cred = (
                    Credibility.ESTABLISHED_FACT if max_phase >= 4
                    else Credibility.MULTI_EVIDENCE if max_phase >= 3
                    else Credibility.SINGLE_EVIDENCE
                )
                treat_rows.append(_make_edge(
                    x_id=chembl_id, x_type=NodeType.MOLECULE.value,
                    y_id=disease_id, y_type=NodeType.DISEASE.value,
                    relation="molecule_treats_disease",
                    display_relation=f"indication (phase {max_phase})",
                    source=f"OpenTargets/indication",
                    credibility=cred,
                    max_phase=max_phase,
                ))

    if treat_rows:
        _save_edge_df(pd.DataFrame(treat_rows), out_dir, "molecule_treats_disease")
    if contra_rows:
        _save_edge_df(pd.DataFrame(contra_rows), out_dir, "molecule_contraindicates_disease")

    log.info("  %d indication edges, %d contraindication edges",
             len(treat_rows), len(contra_rows))
    return len(treat_rows), len(contra_rows)


# ---------------------------------------------------------------------------
# 10. mechanismOfAction → molecule_targets_protein edges
# ---------------------------------------------------------------------------

def ingest_mechanism_of_action(ot_dir: Path, out_dir: Path) -> int:
    """Ingest OT mechanismOfAction dataset → molecule_targets_protein edges.

    Returns number of edges written.
    """
    moa_path = ot_dir / "drug_mechanism_of_action"
    if not moa_path.exists():
        log.warning("'drug_mechanism_of_action' dataset not found in %s — skipping", ot_dir)
        return 0

    log.info("Loading drug_mechanism_of_action dataset from %s", moa_path)

    df = _read_parquet_dir(
        moa_path,
        columns=["chemblIds", "targetName", "targets", "actionType",
                 "mechanismOfAction"],
    )
    log.info("  %d MoA rows", len(df))

    edge_rows: list[dict] = []

    for _, row in df.iterrows():
        chembl_ids = _to_list(row.get("chemblIds"))
        targets    = _to_list(row.get("targets"))
        action     = str(row.get("actionType") or "").strip()
        moa_label  = str(row.get("mechanismOfAction") or "").strip()

        for chembl_id in chembl_ids:
            chembl_id = str(chembl_id or "").strip()
            if not chembl_id.startswith("CHEMBL"):
                continue

            for target in targets:
                if isinstance(target, dict):
                    gene_id = str(target.get("id") or "").strip()
                else:
                    gene_id = str(target or "").strip()

                if not gene_id.startswith("ENSG"):
                    continue

                # Emit gene-level edge (Ensembl); protein resolution is deferred
                edge_rows.append(_make_edge(
                    x_id=chembl_id, x_type=NodeType.MOLECULE.value,
                    y_id=gene_id,   y_type=NodeType.GENE.value,
                    relation="molecule_targets_protein",
                    display_relation=moa_label or action or "targets",
                    source=SOURCE_NAME,
                    credibility=Credibility.ESTABLISHED_FACT,
                    action_type=action,
                ))

    if edge_rows:
        _save_edge_df(pd.DataFrame(edge_rows), out_dir, "molecule_targets_protein")
    log.info("  %d molecule→gene (MoA) edges saved", len(edge_rows))
    return len(edge_rows)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

ALL_DATASETS = [
    "target",
    "disease",
    "drug_molecule",
    "interaction",
    "evidence",          # pseudo-name: ingests all evidence_* subdirs
    "go",
    "reactome",
    "literature",        # pseudo-name: reads from evidence_europepmc
    "drug_indication",
    "drug_mechanism_of_action",
]

# ---------------------------------------------------------------------------
# Phase 5a — Disease-phenotype (HPO) associations
# ---------------------------------------------------------------------------

def ingest_disease_phenotype(ot_dir: Path, out_dir: Path) -> int:
    """Ingest disease-phenotype associations → ``disease_has_phenotype`` edges.

    Source: ``data/opentargets/disease_phenotype/``
    Schema: disease (MONDO_...), phenotype (HP_...), evidence (list of dicts)
    Produces: ``edges/disease_has_phenotype.parquet``

    Credibility is assigned from the HPO ``evidenceType``:
    - TAS / PCS  → 3 (curated / published clinical series)
    - IEA        → 2 (inferred from electronic annotation)
    - other      → 1
    """
    dp_dir = ot_dir / "disease_phenotype"
    if not dp_dir.exists():
        raise FileNotFoundError(dp_dir)

    rows: list[dict] = []
    for chunk in _read_parquet_dir_chunked(
        dp_dir, columns=["disease", "phenotype", "evidence"], chunksize=100_000
    ):
        for _, row in chunk.iterrows():
            disease_id  = row["disease"]
            phenotype_id = row["phenotype"]
            evidence_list = _to_list(row.get("evidence", []))

            # Basic ID validation
            if not isinstance(disease_id, str) or not disease_id.startswith("MONDO_"):
                continue
            if not isinstance(phenotype_id, str) or not phenotype_id.startswith("HP_"):
                continue

            # Skip negated associations (qualifierNot=True in any evidence item)
            if any(
                isinstance(e, dict) and e.get("qualifierNot", False)
                for e in evidence_list
            ):
                continue

            # Derive credibility from the strongest evidenceType present
            ev_types = {
                e.get("evidenceType", "")
                for e in evidence_list
                if isinstance(e, dict)
            }
            if ev_types & {"TAS", "PCS"}:
                cred = Credibility.ESTABLISHED_FACT
            elif "IEA" in ev_types:
                cred = Credibility.MULTI_EVIDENCE
            else:
                cred = Credibility.SINGLE_EVIDENCE

            rows.append(_make_edge(
                x_id=disease_id,
                x_type=NodeType.DISEASE.value,
                y_id=phenotype_id,
                y_type=NodeType.PHENOTYPE.value,
                relation="disease_has_phenotype",
                display_relation="has phenotype",
                source="OpenTargets/HPO",
                credibility=int(cred),
            ))

    if not rows:
        log.warning("ingest_disease_phenotype: no rows written")
        return 0

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["x_id", "y_id", "relation", "source"], keep="first")
    out_path = out_dir / "edges" / "disease_has_phenotype.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(out_path, index=False)
    log.info("  saved disease_has_phenotype.parquet  (%d rows)", len(df))
    return len(df)


# ---------------------------------------------------------------------------
# Phase 5b — Gene expression (GTEx / HPA via OpenTargets)
# ---------------------------------------------------------------------------

def ingest_expression(ot_dir: Path, out_dir: Path) -> dict[str, int]:
    """Ingest gene-expression data → tissue/cell-type expression edges.

    Source: ``data/opentargets/expression/``
    Schema: id (ENSG), tissues (array of dicts with efo_code, rna.value, …)
    Produces:
      ``edges/tissue_expresses_gene.parquet``   (UBERON_ tissues)
      ``edges/cell_type_expresses_gene.parquet``  (CL_ cell types)
    """
    exp_dir = ot_dir / "expression"
    if not exp_dir.exists():
        raise FileNotFoundError(exp_dir)

    tissue_rows:    list[dict] = []
    cell_type_rows: list[dict] = []

    for chunk in _read_parquet_dir_chunked(
        exp_dir, columns=["id", "tissues"], chunksize=50_000
    ):
        for _, row in chunk.iterrows():
            gene_id   = row["id"]
            if not isinstance(gene_id, str) or not gene_id.startswith("ENSG"):
                continue
            tissues = _to_list(row.get("tissues", []))
            for t in tissues:
                if not isinstance(t, dict):
                    continue
                efo_code = t.get("efo_code", "")
                if not isinstance(efo_code, str):
                    continue

                # RNA expression value (TPM)
                rna = t.get("rna") or {}
                tpm   = rna.get("value") if isinstance(rna, dict) else None
                level = rna.get("level") if isinstance(rna, dict) else None

                extra: dict = {}
                if tpm is not None:
                    extra["tpm"] = float(tpm)
                if level is not None:
                    extra["expression_level"] = int(level)

                if efo_code.startswith("UBERON_"):
                    tissue_rows.append(_make_edge(
                        x_id=efo_code,
                        x_type=NodeType.TISSUE.value,
                        y_id=gene_id,
                        y_type=NodeType.GENE.value,
                        relation="tissue_expresses_gene",
                        display_relation="expresses",
                        source="OpenTargets/HPA",
                        credibility=int(Credibility.ESTABLISHED_FACT),
                        **extra,
                    ))
                elif efo_code.startswith("CL_"):
                    cell_type_rows.append(_make_edge(
                        x_id=efo_code,
                        x_type=NodeType.CELL_TYPE.value,
                        y_id=gene_id,
                        y_type=NodeType.GENE.value,
                        relation="cell_type_expresses_gene",
                        display_relation="expresses",
                        source="OpenTargets/HPA",
                        credibility=int(Credibility.ESTABLISHED_FACT),
                        **extra,
                    ))

    dedup = ["x_id", "y_id", "relation", "source"]
    results: dict[str, int] = {}

    for relation, rows in [
        ("tissue_expresses_gene",    tissue_rows),
        ("cell_type_expresses_gene", cell_type_rows),
    ]:
        if not rows:
            log.warning("ingest_expression: no rows for %s", relation)
            results[relation] = 0
            continue
        df = pd.DataFrame(rows).drop_duplicates(subset=dedup, keep="first")
        out_path = out_dir / "edges" / f"{relation}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.reset_index(drop=True).to_parquet(out_path, index=False)
        log.info("  saved %s.parquet  (%d rows)", relation, len(df))
        results[relation] = len(df)

    return results


# ---------------------------------------------------------------------------
# Phase 5c — Biosample (cell-type and tissue node registry)
# ---------------------------------------------------------------------------

def ingest_biosample(ot_dir: Path, out_dir: Path) -> dict[str, int]:
    """Register cell-type and tissue nodes from the OpenTargets biosample table.

    Source: ``data/opentargets/biosample/``
    Columns: biosampleId, biosampleName, …
    Produces:
      ``nodes/cell_type.parquet``  (CL_ IDs)
      ``nodes/tissue.parquet``     (UBERON_ IDs)
    """
    bs_dir = ot_dir / "biosample"
    if not bs_dir.exists():
        raise FileNotFoundError(bs_dir)

    cell_type_rows: list[dict] = []
    tissue_rows:    list[dict] = []

    for chunk in _read_parquet_dir_chunked(
        bs_dir, columns=["biosampleId", "biosampleName"], chunksize=50_000
    ):
        for _, row in chunk.iterrows():
            bid  = row["biosampleId"]
            name = row.get("biosampleName", "")
            if not isinstance(bid, str):
                continue
            node = {"id": bid, "name": str(name) if name else None, "source": SOURCE_NAME}
            if bid.startswith("CL_"):
                cell_type_rows.append(node)
            elif bid.startswith("UBERON_"):
                tissue_rows.append(node)

    results: dict[str, int] = {}
    for ntype, rows in [
        (NodeType.CELL_TYPE.value, cell_type_rows),
        (NodeType.TISSUE.value,    tissue_rows),
    ]:
        if not rows:
            log.warning("ingest_biosample: no rows for node type %s", ntype)
            results[ntype] = 0
            continue
        df = pd.DataFrame(rows).drop_duplicates(subset=["id"], keep="first")
        out_path = out_dir / "nodes" / f"{ntype}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.reset_index(drop=True).to_parquet(out_path, index=False)
        log.info("  saved nodes/%s.parquet  (%d rows)", ntype, len(df))
        results[ntype] = len(df)

    return results


# ---------------------------------------------------------------------------
# Phase 5d — Pharmacogenomics (variant–drug response)
# ---------------------------------------------------------------------------

def ingest_pharmacogenomics(ot_dir: Path, out_dir: Path) -> int:
    """Ingest pharmacogenomics data → ``mutation_affects_molecule_response`` edges.

    Source: ``data/opentargets/pharmacogenomics/``
    Key columns: variantId (chr_pos_ref_alt), variantRsId, targetFromSourceId (ENSG),
                 drugs (array of {drugFromSource, drugId (ChEMBL)})
    Produces: ``edges/mutation_affects_molecule_response.parquet``

    Only rows where a ChEMBL drugId is present are emitted.
    """
    pg_dir = ot_dir / "pharmacogenomics"
    if not pg_dir.exists():
        raise FileNotFoundError(pg_dir)

    rows: list[dict] = []
    pg_cols = ["variantId", "variantRsId", "targetFromSourceId", "drugs",
               "evidenceLevel", "pgxCategory", "datasourceId"]

    for chunk in _read_parquet_dir_chunked(pg_dir, columns=pg_cols, chunksize=100_000):
        for _, row in chunk.iterrows():
            variant_id = row.get("variantId")
            if not isinstance(variant_id, str) or not variant_id:
                continue

            drugs = _to_list(row.get("drugs", []))
            ev_level = row.get("evidenceLevel")
            pgx_cat  = row.get("pgxCategory", "")
            datasrc  = str(row.get("datasourceId", SOURCE_NAME))

            # Assign credibility from evidenceLevel (PharmGKB: 1A/1B > 2A/2B > 3/4)
            try:
                level_str = str(ev_level).strip() if ev_level is not None else ""
                if level_str in ("1A", "1B"):
                    cred = int(Credibility.ESTABLISHED_FACT)
                elif level_str in ("2A", "2B"):
                    cred = int(Credibility.MULTI_EVIDENCE)
                else:
                    cred = int(Credibility.SINGLE_EVIDENCE)
            except Exception:
                cred = int(Credibility.SINGLE_EVIDENCE)

            for drug in drugs:
                if not isinstance(drug, dict):
                    continue
                drug_id = drug.get("drugId")
                if not isinstance(drug_id, str) or not drug_id.startswith("CHEMBL"):
                    continue

                rows.append(_make_edge(
                    x_id=variant_id,
                    x_type=NodeType.MUTATION.value,
                    y_id=drug_id,
                    y_type=NodeType.MOLECULE.value,
                    relation="mutation_affects_molecule_response",
                    display_relation="affects response to",
                    source=f"OpenTargets/{datasrc}",
                    credibility=cred,
                    pgx_category=str(pgx_cat) if pgx_cat else None,
                ))

    if not rows:
        log.warning("ingest_pharmacogenomics: no rows written")
        return 0

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["x_id", "y_id", "relation", "source"], keep="first")
    out_path = out_dir / "edges" / "mutation_affects_molecule_response.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(out_path, index=False)
    log.info("  saved mutation_affects_molecule_response.parquet  (%d rows)", len(df))
    return len(df)


# ---------------------------------------------------------------------------
# Phase 5e — Variant (mutation nodes + consequence edges)
# ---------------------------------------------------------------------------

def ingest_variants(ot_dir: Path, out_dir: Path) -> dict[str, int]:
    """Ingest variant data → mutation nodes + gene/transcript/protein edges.

    Source: ``data/opentargets/variant/`` (25 parquet files, large)
    Key columns: variantId (chr_pos_ref_alt), hgvsId, rsIds,
                 transcriptConsequences (array of consequence dicts)
    Produces:
      ``nodes/mutation.parquet``
      ``edges/mutation_in_gene.parquet``              (→ ENSG via targetId)
      ``edges/mutation_affects_transcript.parquet``   (→ ENST via transcriptId)
      ``edges/mutation_causes_protein_change.parquet`` (→ UniProt, only if aminoAcidChange)

    Uses per-chunk flushing to avoid OOM on large files.
    """
    var_dir = ot_dir / "variant"
    if not var_dir.exists():
        raise FileNotFoundError(var_dir)

    chunks_base   = out_dir / ".chunks" / "variants"
    mut_chunks    = chunks_base / "mutation"
    gene_chunks   = chunks_base / "mutation_in_gene"
    tx_chunks     = chunks_base / "mutation_affects_transcript"
    prot_chunks   = chunks_base / "mutation_causes_protein_change"

    var_cols = [
        "variantId", "hgvsId", "rsIds", "chromosome", "position",
        "referenceAllele", "alternateAllele", "mostSevereConsequenceId",
        "transcriptConsequences",
    ]

    for chunk in _read_parquet_dir_chunked(var_dir, columns=var_cols, chunksize=500_000):
        # ── Mutation nodes (fully vectorized) ───────────────────────────────
        mut_df = chunk.rename(columns={
            "variantId":       "id",
            "hgvsId":          "hgvs_id",
            "referenceAllele": "ref_allele",
            "alternateAllele": "alt_allele",
        })[["id", "hgvs_id", "rsIds", "chromosome", "position",
            "ref_allele", "alt_allele"]].copy()

        # First rsId element as alias (list column → scalar)
        mut_df["rs_id"] = mut_df["rsIds"].apply(
            lambda x: list(x)[0] if x is not None and hasattr(x, "__len__") and len(x) > 0 else None
        )
        # Human-readable name: prefer HGVS, fall back to variantId
        mut_df["name"] = mut_df["hgvs_id"].combine_first(mut_df["id"])
        mut_df["source"] = SOURCE_NAME
        mut_df = mut_df.drop(columns=["rsIds"])
        # Drop rows with missing variantId
        mut_df = mut_df[mut_df["id"].notna() & (mut_df["id"] != "")]
        _write_chunk(mut_df, mut_chunks)

        # ── Consequence edges (explode → json_normalize → mask) ─────────────
        tc_df = chunk[["variantId", "transcriptConsequences"]].copy()
        tc_df = tc_df.explode("transcriptConsequences")
        tc_df = tc_df.dropna(subset=["transcriptConsequences"])

        # Keep only Ensembl canonical transcripts
        is_canonical = tc_df["transcriptConsequences"].apply(
            lambda x: isinstance(x, dict) and bool(x.get("isEnsemblCanonical", False))
        )
        tc_df = tc_df[is_canonical]

        if len(tc_df) == 0:
            _write_chunk(pd.DataFrame(), gene_chunks)
            _write_chunk(pd.DataFrame(), tx_chunks)
            _write_chunk(pd.DataFrame(), prot_chunks)
            continue

        # Expand the consequence dict into flat columns
        tc_exp = pd.json_normalize(tc_df["transcriptConsequences"].tolist())
        tc_exp.index = tc_df.index
        tc_exp["variantId"] = tc_df["variantId"].values

        # Gene edges  (mutation → ENSG)
        if "targetId" in tc_exp.columns:
            gene_mask = tc_exp["targetId"].str.startswith("ENSG", na=False)
            g = tc_exp.loc[gene_mask, ["variantId", "targetId"]].rename(
                columns={"variantId": "x_id", "targetId": "y_id"}
            ).copy()
            g["x_type"]          = NodeType.MUTATION.value
            g["y_type"]          = NodeType.GENE.value
            g["relation"]        = "mutation_in_gene"
            g["display_relation"] = "in gene"
            g["source"]          = SOURCE_NAME
            g["credibility"]     = int(Credibility.ESTABLISHED_FACT)
            _write_chunk(g, gene_chunks)
        else:
            _write_chunk(pd.DataFrame(), gene_chunks)

        # Transcript edges  (mutation → ENST)
        if "transcriptId" in tc_exp.columns:
            tx_mask = tc_exp["transcriptId"].str.startswith("ENST", na=False)
            t = tc_exp.loc[tx_mask, ["variantId", "transcriptId"]].rename(
                columns={"variantId": "x_id", "transcriptId": "y_id"}
            ).copy()
            t["x_type"]          = NodeType.MUTATION.value
            t["y_type"]          = NodeType.TRANSCRIPT.value
            t["relation"]        = "mutation_affects_transcript"
            t["display_relation"] = "affects transcript"
            t["source"]          = SOURCE_NAME
            t["credibility"]     = int(Credibility.ESTABLISHED_FACT)
            _write_chunk(t, tx_chunks)
        else:
            _write_chunk(pd.DataFrame(), tx_chunks)

        # Protein-change edges  (mutation → UniProt, only if aminoAcidChange set)
        if "aminoAcidChange" in tc_exp.columns and "uniprotAccessions" in tc_exp.columns:
            aa_mask = (
                tc_exp["aminoAcidChange"].notna()
                & (tc_exp["aminoAcidChange"].astype(str).str.strip() != "")
                & (tc_exp["aminoAcidChange"].astype(str) != "nan")
            )
            prot_tc = tc_exp.loc[aa_mask, ["variantId", "uniprotAccessions",
                                           "aminoAcidChange"]].copy()
            if len(prot_tc) > 0:
                prot_tc = prot_tc.explode("uniprotAccessions")
                prot_tc = prot_tc.dropna(subset=["uniprotAccessions"])
                valid_up = prot_tc["uniprotAccessions"].str.len() > 0
                prot_tc = prot_tc[valid_up]
                if len(prot_tc) > 0:
                    p = prot_tc.rename(columns={
                        "variantId": "x_id", "uniprotAccessions": "y_id"
                    }).copy()
                    p["x_type"]          = NodeType.MUTATION.value
                    p["y_type"]          = NodeType.PROTEIN.value
                    p["relation"]        = "mutation_causes_protein_change"
                    p["display_relation"] = "causes protein change"
                    p["source"]          = SOURCE_NAME
                    p["credibility"]     = int(Credibility.ESTABLISHED_FACT)
                    p["amino_acid_change"] = p["aminoAcidChange"]
                    p = p.drop(columns=["aminoAcidChange"])
                    _write_chunk(p, prot_chunks)
                    continue
        _write_chunk(pd.DataFrame(), prot_chunks)

    dedup_edge = ["x_id", "y_id", "relation", "source"]
    results: dict[str, int] = {}
    results["mutation"] = _finalize_chunks(
        mut_chunks,
        out_dir / "nodes" / f"{NodeType.MUTATION.value}.parquet",
        dedup_cols=["id"],
    )
    results["mutation_in_gene"] = _finalize_chunks(
        gene_chunks,
        out_dir / "edges" / "mutation_in_gene.parquet",
        dedup_cols=dedup_edge,
    )
    results["mutation_affects_transcript"] = _finalize_chunks(
        tx_chunks,
        out_dir / "edges" / "mutation_affects_transcript.parquet",
        dedup_cols=dedup_edge,
    )
    results["mutation_causes_protein_change"] = _finalize_chunks(
        prot_chunks,
        out_dir / "edges" / "mutation_causes_protein_change.parquet",
        dedup_cols=dedup_edge,
    )
    return results


# ---------------------------------------------------------------------------
# Phase 5f — Enhancer-to-gene (E2G predictions)
# ---------------------------------------------------------------------------

def ingest_enhancers(ot_dir: Path, out_dir: Path) -> dict[str, int]:
    """Ingest enhancer-to-gene links → enhancer nodes + regulatory edges.

    Source: ``data/opentargets/enhancer_to_gene/`` (83 parquet files)
    Key columns: intervalId, geneId (ENSG), biosampleId (UBERON_/CL_),
                 biosampleName, chromosome, start, end, score, datasourceId
    Produces:
      ``nodes/enhancer.parquet``
      ``edges/enhancer_regulates_gene.parquet``
      ``edges/enhancer_active_in_tissue.parquet``   (UBERON_ biosamples)
      ``edges/enhancer_active_in_cell_type.parquet`` (CL_ biosamples)

    Uses per-chunk flushing (83 files, large).
    """
    enh_dir = ot_dir / "enhancer_to_gene"
    if not enh_dir.exists():
        raise FileNotFoundError(enh_dir)

    chunks_base    = out_dir / ".chunks" / "enhancers"
    enh_node_chks  = chunks_base / "enhancer"
    gene_edge_chks = chunks_base / "enhancer_regulates_gene"
    tis_edge_chks  = chunks_base / "enhancer_active_in_tissue"
    ct_edge_chks   = chunks_base / "enhancer_active_in_cell_type"

    enh_cols = [
        "intervalId", "geneId", "biosampleId", "biosampleName",
        "chromosome", "start", "end", "score", "datasourceId", "pmid",
    ]

    dedup_edge = ["x_id", "y_id", "relation", "source"]

    for chunk in _read_parquet_dir_chunked(enh_dir, columns=enh_cols, chunksize=500_000):
        # Drop rows with missing intervalId
        chunk = chunk[chunk["intervalId"].notna() & (chunk["intervalId"] != "")].copy()
        if len(chunk) == 0:
            continue

        # Shared derived columns
        src_col = "OpenTargets/" + chunk["datasourceId"].fillna("E2G").astype(str)

        # Credibility from E2G score using pd.cut (vectorized)
        score_col = pd.to_numeric(chunk["score"], errors="coerce").fillna(0.0)
        cred_col = pd.cut(
            score_col,
            bins=[-np.inf, 0.5, 0.9, np.inf],
            labels=[int(Credibility.SINGLE_EVIDENCE),
                    int(Credibility.MULTI_EVIDENCE),
                    int(Credibility.ESTABLISHED_FACT)],
        ).astype(int)

        # ── Enhancer nodes ──────────────────────────────────────────────────
        enh_df = chunk[["intervalId", "chromosome", "start", "end"]].rename(
            columns={"intervalId": "id"}
        ).copy()
        enh_df["name"]   = enh_df["id"]
        enh_df["source"] = src_col.values
        _write_chunk(enh_df, enh_node_chks)

        # ── enhancer → gene edges ───────────────────────────────────────────
        gene_mask = chunk["geneId"].str.startswith("ENSG", na=False)
        if gene_mask.any():
            g = chunk.loc[gene_mask, ["intervalId", "geneId", "score"]].rename(
                columns={"intervalId": "x_id", "geneId": "y_id", "score": "e2g_score"}
            ).copy()
            g["x_type"]          = NodeType.ENHANCER.value
            g["y_type"]          = NodeType.GENE.value
            g["relation"]        = "enhancer_regulates_gene"
            g["display_relation"] = "regulates"
            g["source"]          = src_col[gene_mask].values
            g["credibility"]     = cred_col[gene_mask].values
            _write_chunk(g, gene_edge_chks)

        # ── enhancer → tissue edges (UBERON_) ───────────────────────────────
        tis_mask = chunk["biosampleId"].str.startswith("UBERON_", na=False)
        if tis_mask.any():
            t = chunk.loc[tis_mask, ["intervalId", "biosampleId"]].rename(
                columns={"intervalId": "x_id", "biosampleId": "y_id"}
            ).copy()
            t["x_type"]          = NodeType.ENHANCER.value
            t["y_type"]          = NodeType.TISSUE.value
            t["relation"]        = "enhancer_active_in_tissue"
            t["display_relation"] = "active in tissue"
            t["source"]          = src_col[tis_mask].values
            t["credibility"]     = cred_col[tis_mask].values
            _write_chunk(t, tis_edge_chks)

        # ── enhancer → cell-type edges (CL_) ────────────────────────────────
        ct_mask = chunk["biosampleId"].str.startswith("CL_", na=False)
        if ct_mask.any():
            c = chunk.loc[ct_mask, ["intervalId", "biosampleId"]].rename(
                columns={"intervalId": "x_id", "biosampleId": "y_id"}
            ).copy()
            c["x_type"]          = NodeType.ENHANCER.value
            c["y_type"]          = NodeType.CELL_TYPE.value
            c["relation"]        = "enhancer_active_in_cell_type"
            c["display_relation"] = "active in cell type"
            c["source"]          = src_col[ct_mask].values
            c["credibility"]     = cred_col[ct_mask].values
            _write_chunk(c, ct_edge_chks)

    results: dict[str, int] = {}
    results["enhancer"] = _finalize_chunks(
        enh_node_chks,
        out_dir / "nodes" / f"{NodeType.ENHANCER.value}.parquet",
        dedup_cols=["id"],
    )
    results["enhancer_regulates_gene"] = _finalize_chunks(
        gene_edge_chks,
        out_dir / "edges" / "enhancer_regulates_gene.parquet",
        dedup_cols=dedup_edge,
    )
    results["enhancer_active_in_tissue"] = _finalize_chunks(
        tis_edge_chks,
        out_dir / "edges" / "enhancer_active_in_tissue.parquet",
        dedup_cols=dedup_edge,
    )
    results["enhancer_active_in_cell_type"] = _finalize_chunks(
        ct_edge_chks,
        out_dir / "edges" / "enhancer_active_in_cell_type.parquet",
        dedup_cols=dedup_edge,
    )
    return results


# ---------------------------------------------------------------------------
# Dataset dispatch table
# ---------------------------------------------------------------------------

DATASET_FUNCTIONS = {
    "target":                   ingest_targets,
    "disease":                  ingest_diseases,
    "drug_molecule":            ingest_drugs,
    "molecule":                 ingest_drugs,   # alias
    "drug":                     ingest_drugs,   # alias
    "interaction":              ingest_interactions,
    "evidence":                 ingest_evidence,
    "go":                       ingest_go,
    "reactome":                 ingest_reactome,
    "literature":               ingest_literature,
    "drug_indication":          ingest_indication,
    "indication":               ingest_indication,  # alias
    "drug_mechanism_of_action": ingest_mechanism_of_action,
    "mechanismOfAction":        ingest_mechanism_of_action,  # alias
    # Phase 5 additions
    "disease_phenotype":        ingest_disease_phenotype,
    "expression":               ingest_expression,
    "biosample":                ingest_biosample,
    "pharmacogenomics":         ingest_pharmacogenomics,
    "variant":                  ingest_variants,
    "enhancer_to_gene":         ingest_enhancers,
    "enhancers":                ingest_enhancers,  # alias
}


def run(
    data_dir: Path,
    datasets: list[str] | None = None,
    release: str = "latest",
    download: bool = True,
    workers: int = 8,
) -> None:
    """Download (optionally) and ingest OpenTargets datasets.

    Args:
        data_dir:  Root data directory; OT data lands in ``{data_dir}/opentargets/``.
        datasets:  Dataset names to process.  Defaults to ``ALL_DATASETS``.
        release:   OT release tag or ``"latest"``.
        download:  If True (default), download missing datasets first.
        workers:   Parallel download threads.
    """
    if datasets is None:
        datasets = list(ALL_DATASETS)

    ot_dir  = data_dir / "opentargets"
    out_dir = data_dir / "kg"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Download ─────────────────────────────────────────────────────────────
    if download:
        try:
            # Import inside to avoid hard dependency at module import time
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from txdata_download import download_opentargets_datasets

            download_opentargets_datasets(
                datasets=datasets,
                dest_dir=ot_dir,
                release=release,
                workers=workers,
            )
        except ImportError:
            log.warning("txdata_download not importable; assuming data is already local")

    # ── Ingest ───────────────────────────────────────────────────────────────
    summary: dict[str, object] = {}
    for ds_name in datasets:
        fn = DATASET_FUNCTIONS.get(ds_name)
        if fn is None:
            log.warning("No ingestion function for dataset %r — skipping", ds_name)
            continue
        log.info("\n=== Ingesting %s ===", ds_name)
        try:
            result = fn(ot_dir, out_dir)
            summary[ds_name] = result
        except FileNotFoundError as exc:
            log.error("Dataset %r not found: %s", ds_name, exc)
            summary[ds_name] = "MISSING"
        except Exception as exc:
            log.error("Error ingesting %r: %s", ds_name, exc, exc_info=True)
            summary[ds_name] = f"ERROR: {exc}"

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n=== OpenTargets ingestion summary ===")
    for ds_name, result in summary.items():
        print(f"  {ds_name:<25}  {result}")
    print(f"\n  Output directory: {out_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Ingest OpenTargets Platform data into the TxGNN KG Parquet schema"
    )
    parser.add_argument(
        "--data-dir", default="./data",
        help="Root data directory (default: ./data)",
    )
    parser.add_argument(
        "--release", default="latest",
        help="OpenTargets release tag, e.g. '25.06' (default: latest)",
    )
    parser.add_argument(
        "--datasets", nargs="+", default=None,
        metavar="DATASET",
        help=f"Datasets to ingest (default: all). Choices: {ALL_DATASETS}",
    )
    parser.add_argument(
        "--no-download", action="store_true",
        help="Skip downloading; use already-local data only",
    )
    parser.add_argument(
        "--workers", type=int, default=8,
        help="Parallel download threads (default: 8)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
        stream=sys.stderr,
    )

    run(
        data_dir=Path(args.data_dir),
        datasets=args.datasets,
        release=args.release,
        download=not args.no_download,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
