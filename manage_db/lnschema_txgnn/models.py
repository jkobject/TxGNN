"""Custom LaminDB record types for TxGNN node types not covered by bionty.

Primary-ontology mapping
------------------------
Each model stores its canonical (primary) ID in a clearly named field.
Additional identifiers from other namespaces are stored as nullable
cross-reference (xref) fields, matching the ``xref_columns`` declared in
``kg_schema.NodeTypeInfo``.

For node types already covered by bionty (Gene → bionty.Gene,
Disease → bionty.Disease, CellType → bionty.CellType,
Tissue → bionty.Tissue, Phenotype → bionty.Phenotype,
CellLine → bionty.CellLine, Organism → bionty.Organism),
this module provides *extension* mixins (``*XrefMixin``) that can be used
if you need to store the xref columns in a custom table.
"""

from __future__ import annotations

from lamindb.base.fields import BooleanField, CharField, IntegerField, TextField
from lamindb.models import SQLRecord, TracksRun, TracksUpdates


# ---------------------------------------------------------------------------
# Custom node-type models (not covered by bionty)
# ---------------------------------------------------------------------------

class Paper(SQLRecord, TracksRun, TracksUpdates):
    """A scientific paper identified by PubMed ID.

    Node type:        ``paper``
    Primary ontology: PubMed (PMID)
    Xref columns:     doi, pmc_id, arxiv_id
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    # Primary identifier
    pmid: str | None = CharField(max_length=32, null=True, db_index=True, unique=True)
    """PubMed ID (e.g., ``"12345678"``). Primary identifier."""

    # Cross-reference identifiers
    doi: str | None = CharField(max_length=255, null=True, db_index=True)
    """Digital Object Identifier."""
    pmc_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """PubMed Central accession (e.g., ``"PMC9046468"``)."""
    arxiv_id: str | None = CharField(max_length=64, null=True, db_index=True)
    """arXiv preprint ID (e.g., ``"2303.12345"``)."""

    # Metadata fields
    title: str | None = CharField(max_length=1024, null=True, db_index=True)
    """Title of the paper."""
    year: int | None = IntegerField(null=True, db_index=True)
    """Publication year."""
    journal: str | None = CharField(max_length=512, null=True, db_index=True)
    """Journal name."""
    abstract: str | None = TextField(null=True)
    """Abstract text."""


class Transcript(SQLRecord, TracksRun, TracksUpdates):
    """An Ensembl transcript (RNA isoform of a gene).

    Node type:        ``transcript``
    Primary ontology: Ensembl (ENST…)
    Xref columns:     refseq_mrna, ccds_id
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    # Primary identifier
    ensembl_transcript_id: str = CharField(max_length=64, db_index=True, unique=True)
    """Ensembl transcript ID (e.g., ``"ENST00000000233"``). Primary identifier."""

    # Cross-reference identifiers
    refseq_mrna: str | None = CharField(max_length=64, null=True, db_index=True)
    """RefSeq mRNA accession (e.g., ``"NM_000492.4"``)."""
    ccds_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """Consensus CDS (CCDS) identifier."""

    # Metadata
    ensembl_gene_id: str | None = CharField(max_length=64, null=True, db_index=True)
    """Parent Ensembl gene ID (e.g., ``"ENSG00000139618"``)."""
    biotype: str | None = CharField(max_length=64, null=True, db_index=True)
    """Transcript biotype (e.g., ``"protein_coding"``, ``"lncRNA"``)."""
    is_canonical: bool = BooleanField(default=False, db_default=False)
    """Whether this is the canonical / MANE Select transcript for its gene."""


class Enhancer(SQLRecord, TracksRun, TracksUpdates):
    """A regulatory enhancer element from ENCODE or Ensembl Regulatory Build.

    Node type:        ``enhancer``
    Primary ontology: ENCODE (EH38E…)
    Xref columns:     ensembl_regulatory_id, encode_experiment_id
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    # Primary identifier
    encode_id: str | None = CharField(max_length=64, null=True, db_index=True, unique=True)
    """ENCODE enhancer element ID (e.g., ``"EH38E1516972"``). Primary identifier."""

    # Cross-reference identifiers
    ensembl_regulatory_id: str | None = CharField(max_length=64, null=True, db_index=True)
    """Ensembl Regulatory Build feature ID (e.g., ``"ENSR00000000001"``)."""
    encode_experiment_id: str | None = CharField(max_length=64, null=True, db_index=True)
    """ENCODE experiment accession that identified this enhancer."""

    # Genomic coordinates
    chromosome: str | None = CharField(max_length=16, null=True, db_index=True)
    """Chromosome (e.g., ``"chr1"``)."""
    start_pos: int | None = IntegerField(null=True, db_index=True)
    """Genomic start position (0-based, GRCh38)."""
    end_pos: int | None = IntegerField(null=True, db_index=True)
    """Genomic end position (exclusive, GRCh38)."""


class Dataset(SQLRecord, TracksRun, TracksUpdates):
    """A dataset with provenance information.

    Node type:        ``dataset``
    Primary ontology: DOI / internal UUID
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    name: str = CharField(max_length=512, db_index=True)
    """Human-readable dataset name."""
    doi: str | None = CharField(max_length=255, null=True, db_index=True)
    """DOI of the dataset or associated publication. Used as primary ID when available."""
    description: str | None = TextField(null=True)
    """Longer description of the dataset."""
    version: str | None = CharField(max_length=64, null=True, db_index=True)
    """Dataset version string."""
    source_url: str | None = CharField(max_length=2048, null=True)
    """URL where the dataset can be accessed or downloaded."""


class Mutation(SQLRecord, TracksRun, TracksUpdates):
    """A genetic variant: SNP, indel, or structural variant.

    Node type:        ``mutation``
    Primary ontology: dbSNP rsID
    Xref columns:     hgvs, clinvar_id, gnomad_id
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    # Primary identifier
    rsid: str | None = CharField(max_length=32, null=True, db_index=True, unique=True)
    """dbSNP rsID (e.g., ``"rs7412"``). Primary identifier for SNPs."""

    # Cross-reference identifiers
    hgvs: str | None = CharField(max_length=512, null=True, db_index=True)
    """HGVS notation (e.g., ``"NM_000492.4:c.1521_1523delCTT"``)."""
    clinvar_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """ClinVar VariationID."""
    gnomad_id: str | None = CharField(max_length=64, null=True, db_index=True)
    """gnomAD variant ID in chr_pos_ref_alt format (GRCh38)."""

    # Genomic coordinates
    chromosome: str | None = CharField(max_length=16, null=True, db_index=True)
    """Chromosome (e.g., ``"chr19"``)."""
    position: int | None = IntegerField(null=True, db_index=True)
    """Genomic position (1-based, GRCh38)."""
    ref_allele: str | None = CharField(max_length=512, null=True)
    """Reference allele sequence."""
    alt_allele: str | None = CharField(max_length=512, null=True)
    """Alternate allele sequence."""
    consequence: str | None = CharField(max_length=64, null=True, db_index=True)
    """Predicted molecular consequence (e.g., ``"missense_variant"``)."""


# ---------------------------------------------------------------------------
# Xref extension mixins for bionty-managed node types
#
# Use these if you need to attach extra cross-reference columns to nodes
# that are normally stored in bionty registries.  In practice, the xref
# columns can also be stored as JSON/text in bionty's built-in 'synonyms'
# or as separate LaminDB Artifact metadata — choose the approach that fits
# your query patterns.
# ---------------------------------------------------------------------------

class GeneXrefMixin:
    """Cross-reference fields for gene nodes (primary: Ensembl Gene ID).

    Mix into a custom SQLRecord subclass alongside ``bionty.Gene`` if you
    need typed columns for the gene xref identifiers.

    Xref columns: ncbi_gene_id, hgnc_id, uniprot_id, gene_name
    """
    ncbi_gene_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """NCBI / Entrez Gene ID (integer string, e.g., ``"672"``)."""
    hgnc_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """HGNC ID (e.g., ``"HGNC:1100"``)."""
    uniprot_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """Canonical UniProt accession (e.g., ``"P38398"``)."""
    gene_name: str | None = CharField(max_length=64, null=True, db_index=True)
    """HGNC-approved gene symbol (e.g., ``"BRCA2"``)."""


class DiseaseXrefMixin:
    """Cross-reference fields for disease nodes (primary: EFO ID).

    Xref columns: mondo_id, omim_id, doid_id, icd10_code, mesh_id, hp_id
    """
    mondo_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """MONDO disease ontology ID (e.g., ``"MONDO:0007254"``)."""
    omim_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """OMIM MIM number (e.g., ``"114480"``)."""
    doid_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """Disease Ontology ID (e.g., ``"DOID:1612"``)."""
    icd10_code: str | None = CharField(max_length=16, null=True, db_index=True)
    """ICD-10 code (e.g., ``"C50.9"``)."""
    mesh_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """MeSH descriptor ID (e.g., ``"D001943"``)."""
    hp_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """HPO term cross-reference when the disease is also a phenotype."""


class CellTypeXrefMixin:
    """Cross-reference fields for cell-type nodes (primary: CL ID).

    Xref columns: uberon_id, mesh_id
    """
    uberon_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """Associated UBERON tissue ID where cell normally resides."""
    mesh_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """MeSH term for this cell type."""


class TissueXrefMixin:
    """Cross-reference fields for tissue nodes (primary: UBERON ID).

    Xref columns: bto_id, mesh_id, fma_id
    """
    bto_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """BRENDA Tissue Ontology ID (e.g., ``"BTO:0000567"``)."""
    mesh_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """MeSH anatomical term ID."""
    fma_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """Foundational Model of Anatomy ID (e.g., ``"FMA:7195"``)."""


class MoleculeXrefMixin:
    """Cross-reference fields for molecule nodes (primary: ChEMBL ID).

    Xref columns: drugbank_id, pubchem_cid, cas_rn, inchikey, smiles
    """
    drugbank_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """DrugBank primary accession (e.g., ``"DB01267"``)."""
    pubchem_cid: str | None = CharField(max_length=16, null=True, db_index=True)
    """PubChem compound ID."""
    cas_rn: str | None = CharField(max_length=32, null=True, db_index=True)
    """CAS Registry Number."""
    inchikey: str | None = CharField(max_length=27, null=True, db_index=True)
    """Standard InChIKey (27 characters)."""
    smiles: str | None = TextField(null=True)
    """Canonical SMILES string."""


class PhenotypeXrefMixin:
    """Cross-reference fields for phenotype nodes (primary: HP ID).

    Xref columns: mondo_id, efo_id, mp_id, mesh_id
    """
    mondo_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """MONDO term when phenotype is also classified as a disease."""
    efo_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """EFO cross-reference."""
    mp_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """Mammalian Phenotype Ontology ID (mouse ortholog)."""
    mesh_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """MeSH descriptor ID."""


class CellLineXrefMixin:
    """Cross-reference fields for cell-line nodes (primary: Cellosaurus CVCL_).

    Xref columns: ccle_name, cosmic_id, efo_id
    """
    ccle_name: str | None = CharField(max_length=64, null=True, db_index=True)
    """CCLE / DepMap cell line name (e.g., ``"MCF7_BREAST"``)."""
    cosmic_id: str | None = CharField(max_length=16, null=True, db_index=True)
    """COSMIC cell line ID."""
    efo_id: str | None = CharField(max_length=32, null=True, db_index=True)
    """EFO cell line term."""
