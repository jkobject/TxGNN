"""Custom LaminDB record types for TxGNN node types not covered by bionty."""

from __future__ import annotations

from lamindb.base.fields import BooleanField, CharField, IntegerField, TextField
from lamindb.models import SQLRecord, TracksRun, TracksUpdates


class Paper(SQLRecord, TracksRun, TracksUpdates):
    """A scientific paper identified by PubMed ID or DOI.

    Node type: ``paper``
    Ontology namespace: PubMed ID / DOI
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    pmid: str | None = CharField(max_length=32, null=True, db_index=True, unique=True)
    """PubMed ID (e.g., ``"12345678"``)."""
    doi: str | None = CharField(max_length=255, null=True, db_index=True)
    """Digital Object Identifier."""
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

    Node type: ``transcript``
    Ontology namespace: Ensembl Transcript ID (ENST…)
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    ensembl_transcript_id: str = CharField(max_length=64, db_index=True, unique=True)
    """Ensembl transcript ID (e.g., ``"ENST00000000233"``). Primary identifier."""
    ensembl_gene_id: str | None = CharField(max_length=64, null=True, db_index=True)
    """Parent Ensembl gene ID (e.g., ``"ENSG00000139618"``)."""
    biotype: str | None = CharField(max_length=64, null=True, db_index=True)
    """Transcript biotype (e.g., ``"protein_coding"``, ``"lncRNA"``)."""
    is_canonical: bool = BooleanField(default=False, db_default=False)
    """Whether this is the canonical/MANE Select transcript for its gene."""


class Enhancer(SQLRecord, TracksRun, TracksUpdates):
    """A regulatory enhancer element from ENCODE or Ensembl Regulatory Build.

    Node type: ``enhancer``
    Ontology namespace: ENCODE ID / Ensembl Regulatory Build ID
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    encode_id: str | None = CharField(max_length=64, null=True, db_index=True, unique=True)
    """ENCODE enhancer ID (e.g., ``"EH38E1516972"``). Primary identifier."""
    chromosome: str | None = CharField(max_length=16, null=True, db_index=True)
    """Chromosome (e.g., ``"chr1"``)."""
    start_pos: int | None = IntegerField(null=True, db_index=True)
    """Genomic start position (0-based)."""
    end_pos: int | None = IntegerField(null=True, db_index=True)
    """Genomic end position (exclusive)."""


class Dataset(SQLRecord, TracksRun, TracksUpdates):
    """A dataset with provenance information.

    Node type: ``dataset``
    Ontology namespace: Internal UUID / DOI
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    name: str = CharField(max_length=512, db_index=True)
    """Human-readable dataset name."""
    doi: str | None = CharField(max_length=255, null=True, db_index=True)
    """DOI of the dataset or associated publication."""
    description: str | None = TextField(null=True)
    """Longer description of the dataset."""
    version: str | None = CharField(max_length=64, null=True, db_index=True)
    """Dataset version string."""
    source_url: str | None = CharField(max_length=2048, null=True)
    """URL where the dataset can be accessed or downloaded."""


class Mutation(SQLRecord, TracksRun, TracksUpdates):
    """A genetic variant: SNP, indel, or structural variant.

    Node type: ``mutation``
    Ontology namespace: dbSNP rsID / HGVS
    """

    class Meta(SQLRecord.Meta, TracksRun.Meta, TracksUpdates.Meta):
        abstract = False
        app_label = "lnschema_txgnn"

    rsid: str | None = CharField(max_length=32, null=True, db_index=True, unique=True)
    """dbSNP rsID (e.g., ``"rs7412"``). Primary identifier for SNPs."""
    hgvs: str | None = CharField(max_length=512, null=True, db_index=True)
    """HGVS notation (e.g., ``"NM_000492.4:c.1521_1523delCTT"``)."""
    chromosome: str | None = CharField(max_length=16, null=True, db_index=True)
    """Chromosome (e.g., ``"chr19"``)."""
    position: int | None = IntegerField(null=True, db_index=True)
    """Genomic position (1-based GRCh38)."""
    ref_allele: str | None = CharField(max_length=512, null=True)
    """Reference allele sequence."""
    alt_allele: str | None = CharField(max_length=512, null=True)
    """Alternate allele sequence."""
    consequence: str | None = CharField(max_length=64, null=True, db_index=True)
    """Predicted molecular consequence (e.g., ``"missense_variant"``)."""
