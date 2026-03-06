"""Single source of truth for the TxGNN expanded knowledge graph schema.

Defines:
- Node types with their primary ontology namespaces (``NODE_TYPES``)
- Per-node-type cross-reference column names (``xref_columns``)
- Relation taxonomy (``RELATIONS``) with kind, direct flag, source/target types
- Credibility scoring constants
- Cross-reference resolution helpers (``XREF_RESOLUTION``)

Primary ontology databases
--------------------------
Each node type is canonically identified by exactly **one** primary ontology.
Additional identifiers from other namespaces are stored as extra columns
alongside the primary ID (see ``NodeTypeInfo.xref_columns``).

  Node type    Primary ontology     Primary ID example
  ----------   ------------------   -----------------------
  gene         Ensembl              ENSG00000139618
  transcript   Ensembl              ENST00000380152
  protein      UniProt              P38398
  disease      EFO                  EFO:0000305
  cell_type    CL (Cell Ontology)   CL:0000576
  tissue       UBERON               UBERON:0002107
  molecule     ChEMBL               CHEMBL941
  phenotype    HP                   HP:0000118
  pathway      Reactome             R-HSA-5633007
  mutation     dbSNP rsID           rs7412
  organism     NCBI Taxonomy        9606
  cell_line    Cellosaurus          CVCL_0023
  paper        PubMed               PMID:12345678
  dataset      DOI / UUID           DOI:10.1038/s41586-023-06221-2
  enhancer     ENCODE               EH38E1516972
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Credibility scores
# ---------------------------------------------------------------------------


class Credibility(int, Enum):
    """Evidence credibility level for edges."""

    SINGLE_EVIDENCE = 1  # one paper, possibly same authors
    MULTI_EVIDENCE = 2  # multiple independent evidence sources
    ESTABLISHED_FACT = 3  # curated DB, no ambiguity


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    PAPER = "paper"
    GENE = "gene"
    TRANSCRIPT = "transcript"
    PROTEIN = "protein"
    PATHWAY = "pathway"
    MOLECULE = "molecule"
    MUTATION = "mutation"
    DISEASE = "disease"
    CELL_TYPE = "cell_type"
    TISSUE = "tissue"
    PHENOTYPE = "phenotype"
    CELL_LINE = "cell_line"
    ORGANISM = "organism"
    DATASET = "dataset"
    ENHANCER = "enhancer"


@dataclass(frozen=True)
class NodeTypeInfo:
    """Metadata for a single node type.

    Attributes:
        node_type:        The ``NodeType`` enum value.
        primary_ontology: Short name of the canonical ID namespace (e.g. ``"EFO"``).
        id_format:        Regex-style description or example of the ID pattern.
        bionty_registry:  Dotted path to the bionty registry class, or ``None``.
        example_id:       A concrete example of a valid primary ID.
        xref_columns:     Names of additional cross-reference ID columns stored
                          alongside the primary ID in node Parquet files and
                          LaminDB records.  Each entry is a column name whose
                          value is an optional string (null when unavailable).
    """

    node_type: NodeType
    primary_ontology: str
    id_format: str
    bionty_registry: Optional[str]
    example_id: str
    xref_columns: tuple[str, ...] = ()


NODE_TYPES: dict[NodeType, NodeTypeInfo] = {
    NodeType.GENE: NodeTypeInfo(
        node_type=NodeType.GENE,
        primary_ontology="Ensembl",
        id_format="ENSG<11digits>",
        bionty_registry="bionty.Gene",
        example_id="ENSG00000139618",
        xref_columns=(
            "ncbi_gene_id",  # NCBI / Entrez Gene ID (integer string)
            "hgnc_id",  # HGNC approved symbol
            "uniprot_id",  # canonical UniProt accession (via Ensembl BioMart)
            "gene_name",  # approved HGNC gene symbol
        ),
    ),
    NodeType.TRANSCRIPT: NodeTypeInfo(
        node_type=NodeType.TRANSCRIPT,
        primary_ontology="Ensembl",
        id_format="ENST<11digits>",
        bionty_registry=None,
        example_id="ENST00000380152",
        xref_columns=(
            "refseq_mrna",  # RefSeq NM_ accession
            "ccds_id",  # CCDS identifier
        ),
    ),
    NodeType.PROTEIN: NodeTypeInfo(
        node_type=NodeType.PROTEIN,
        primary_ontology="UniProt",
        id_format="[A-Z][0-9][A-Z0-9]{3}[0-9]",
        bionty_registry=None,
        example_id="P38398",
        xref_columns=(
            "ensembl_gene_id",  # parent Ensembl gene
            "refseq_protein",  # RefSeq NP_ accession
            "pdb_ids",  # pipe-separated PDB structure IDs
        ),
    ),
    NodeType.DISEASE: NodeTypeInfo(
        node_type=NodeType.DISEASE,
        primary_ontology="EFO",
        id_format="EFO:<7digits>",
        bionty_registry="bionty.Disease",
        example_id="EFO:0000305",
        xref_columns=(
            "mondo_id",  # MONDO disease ontology ID
            "omim_id",  # OMIM MIM number
            "doid_id",  # Disease Ontology ID
            "icd10_code",  # ICD-10 code
            "mesh_id",  # MeSH descriptor ID
            "hp_id",  # HPO term if disease is also a phenotype
        ),
    ),
    NodeType.CELL_TYPE: NodeTypeInfo(
        node_type=NodeType.CELL_TYPE,
        primary_ontology="CL",
        id_format="CL:<7digits>",
        bionty_registry="bionty.CellType",
        example_id="CL:0000576",
        xref_columns=(
            "uberon_id",  # associated UBERON tissue where cell normally resides
            "mesh_id",  # MeSH term for the cell type
        ),
    ),
    NodeType.TISSUE: NodeTypeInfo(
        node_type=NodeType.TISSUE,
        primary_ontology="UBERON",
        id_format="UBERON:<7digits>",
        bionty_registry="bionty.Tissue",
        example_id="UBERON:0002107",
        xref_columns=(
            "bto_id",  # BRENDA Tissue Ontology ID
            "mesh_id",  # MeSH anatomical term
            "fma_id",  # Foundational Model of Anatomy ID
        ),
    ),
    NodeType.MOLECULE: NodeTypeInfo(
        node_type=NodeType.MOLECULE,
        primary_ontology="ChEMBL",
        id_format="CHEMBL<int>",
        bionty_registry="pertdb.Compound",
        example_id="CHEMBL941",
        xref_columns=(
            "drugbank_id",  # DrugBank primary accession
            "pubchem_cid",  # PubChem compound ID
            "cas_rn",  # CAS Registry Number
            "inchikey",  # Standard InChIKey (27 chars)
            "smiles",  # Canonical SMILES
        ),
    ),
    NodeType.PHENOTYPE: NodeTypeInfo(
        node_type=NodeType.PHENOTYPE,
        primary_ontology="HP",
        id_format="HP:<7digits>",
        bionty_registry="bionty.Phenotype",
        example_id="HP:0000118",
        xref_columns=(
            "mondo_id",  # MONDO term if phenotype is also classified as disease
            "efo_id",  # EFO cross-reference
            "mp_id",  # Mammalian Phenotype Ontology (mouse ortholog)
            "mesh_id",  # MeSH descriptor
        ),
    ),
    NodeType.PATHWAY: NodeTypeInfo(
        node_type=NodeType.PATHWAY,
        primary_ontology="Reactome",
        id_format="R-HSA-<int>",
        bionty_registry="bionty.Pathway",
        example_id="R-HSA-5633007",
        xref_columns=(
            "go_id",  # Gene Ontology term (Biological Process, Molecular Function, or CC)
            "kegg_id",  # KEGG pathway ID
        ),
    ),
    NodeType.MUTATION: NodeTypeInfo(
        node_type=NodeType.MUTATION,
        primary_ontology="dbSNP",
        id_format="rs<int>",
        bionty_registry=None,
        example_id="rs7412",
        xref_columns=(
            "hgvs",  # HGVS notation (genomic or coding)
            "clinvar_id",  # ClinVar VariationID
            "gnomad_id",  # gnomAD variant ID (chr_pos_ref_alt)
        ),
    ),
    NodeType.ORGANISM: NodeTypeInfo(
        node_type=NodeType.ORGANISM,
        primary_ontology="NCBI Taxonomy",
        id_format="<int>",
        bionty_registry="bionty.Organism",
        example_id="9606",
        xref_columns=("gbif_id",),  # GBIF species ID
    ),
    NodeType.CELL_LINE: NodeTypeInfo(
        node_type=NodeType.CELL_LINE,
        primary_ontology="Cellosaurus",
        id_format="CVCL_<4chars>",
        bionty_registry="bionty.CellLine",
        example_id="CVCL_0023",
        xref_columns=(
            "ccle_name",  # CCLE / DepMap cell line name
            "cosmic_id",  # COSMIC cell line ID
            "efo_id",  # EFO cell line term
        ),
    ),
    NodeType.PAPER: NodeTypeInfo(
        node_type=NodeType.PAPER,
        primary_ontology="PubMed",
        id_format="PMID:<int>",
        bionty_registry=None,
        example_id="PMID:12345678",
        xref_columns=(
            "doi",  # Digital Object Identifier
            "pmc_id",  # PubMed Central ID (PMC...)
            "arxiv_id",  # arXiv preprint ID
        ),
    ),
    NodeType.DATASET: NodeTypeInfo(
        node_type=NodeType.DATASET,
        primary_ontology="DOI / UUID",
        id_format="DOI:<string> or UUID4",
        bionty_registry=None,
        example_id="DOI:10.1038/s41586-023-06221-2",
        xref_columns=(),
    ),
    NodeType.ENHANCER: NodeTypeInfo(
        node_type=NodeType.ENHANCER,
        primary_ontology="ENCODE",
        id_format="EH38E<int>",
        bionty_registry=None,
        example_id="EH38E1516972",
        xref_columns=(
            "ensembl_regulatory_id",  # Ensembl Regulatory Build feature ID
            "encode_experiment_id",  # ENCODE experiment accession
        ),
    ),
}

# Convenience: map NodeType → tuple of xref column names
NODE_XREF_COLUMNS: dict[NodeType, tuple[str, ...]] = {
    nt: info.xref_columns for nt, info in NODE_TYPES.items()
}


# ---------------------------------------------------------------------------
# Relation taxonomy
# ---------------------------------------------------------------------------


class RelationKind(str, Enum):
    CENTRAL_DOGMA = "central_dogma"
    REGULATORY = "regulatory"
    PHYSICAL = "physical"
    GENETIC = "genetic"
    PATHWAY = "pathway"
    PHARMACOLOGICAL = "pharmacological"
    EXPRESSION = "expression"
    DISEASE_ASSOC = "disease_assoc"
    PHENOTYPE_ASSOC = "phenotype_assoc"
    ONTOLOGICAL = "ontological"
    EXPERIMENTAL = "experimental"
    EPIDEMIOLOGICAL = "epidemiological"
    LITERATURE = "literature"
    METADATA = "metadata"


@dataclass(frozen=True)
class Relation:
    """A directed relation type in the knowledge graph.

    Attributes:
        name: Canonical relation name (snake_case).
        source: Source node type.
        target: Target node type.
        kind: Semantic category of the relation.
        direct: True = direct biological interaction; False = associative/indirect.
        notes: Free-text annotation (data sources, caveats…).
    """

    name: str
    source: NodeType
    target: NodeType
    kind: RelationKind
    direct: bool
    notes: str = ""


RELATIONS: list[Relation] = [
    # ── Central dogma ───────────────────────────────────────────────────────
    Relation(
        "gene_has_transcript",
        NodeType.GENE,
        NodeType.TRANSCRIPT,
        RelationKind.CENTRAL_DOGMA,
        True,
        "Transcription",
    ),
    Relation(
        "transcript_encodes_protein",
        NodeType.TRANSCRIPT,
        NodeType.PROTEIN,
        RelationKind.CENTRAL_DOGMA,
        True,
        "Translation",
    ),
    Relation(
        "gene_encodes_protein",
        NodeType.GENE,
        NodeType.PROTEIN,
        RelationKind.CENTRAL_DOGMA,
        False,
        "Shortcut edge",
    ),
    Relation(
        "transcript_alternative_transcript",
        NodeType.TRANSCRIPT,
        NodeType.TRANSCRIPT,
        RelationKind.CENTRAL_DOGMA,
        True,
        "Alternative splicing",
    ),
    # ── Genetic ─────────────────────────────────────────────────────────────
    Relation(
        "mutation_in_gene",
        NodeType.MUTATION,
        NodeType.GENE,
        RelationKind.GENETIC,
        True,
        "Genomic position",
    ),
    Relation(
        "mutation_affects_transcript",
        NodeType.MUTATION,
        NodeType.TRANSCRIPT,
        RelationKind.GENETIC,
        True,
        "Splicing / UTR variant",
    ),
    Relation(
        "mutation_causes_protein_change",
        NodeType.MUTATION,
        NodeType.PROTEIN,
        RelationKind.GENETIC,
        True,
        "Amino acid change",
    ),
    Relation(
        "mutation_overlaps_enhancer",
        NodeType.MUTATION,
        NodeType.ENHANCER,
        RelationKind.GENETIC,
        True,
        "Regulatory variant",
    ),
    Relation(
        "mutation_associated_disease",
        NodeType.MUTATION,
        NodeType.DISEASE,
        RelationKind.GENETIC,
        False,
        "GWAS / ClinVar",
    ),
    Relation(
        "mutation_causes_phenotype",
        NodeType.MUTATION,
        NodeType.PHENOTYPE,
        RelationKind.GENETIC,
        False,
        "Mendelian / GWAS",
    ),
    Relation(
        "mutation_affects_molecule_response",
        NodeType.MUTATION,
        NodeType.MOLECULE,
        RelationKind.PHARMACOLOGICAL,
        False,
        "Pharmacogenomics",
    ),
    Relation(
        "mutation_associated_cell_type",
        NodeType.MUTATION,
        NodeType.CELL_TYPE,
        RelationKind.GENETIC,
        False,
        "eQTL cell-type enrichment",
    ),
    Relation(
        "gene_ortholog_gene",
        NodeType.GENE,
        NodeType.GENE,
        RelationKind.GENETIC,
        True,
        "Cross-species orthology",
    ),
    # ── Regulatory ──────────────────────────────────────────────────────────
    Relation(
        "enhancer_regulates_gene",
        NodeType.ENHANCER,
        NodeType.GENE,
        RelationKind.REGULATORY,
        False,
        "ChIP-seq / Hi-C",
    ),
    Relation(
        "enhancer_regulates_transcript",
        NodeType.ENHANCER,
        NodeType.TRANSCRIPT,
        RelationKind.REGULATORY,
        True,
        "TSS-specific regulation",
    ),
    Relation(
        "enhancer_active_in_cell_type",
        NodeType.ENHANCER,
        NodeType.CELL_TYPE,
        RelationKind.REGULATORY,
        True,
        "ATAC-seq / ChIP-seq",
    ),
    Relation(
        "enhancer_active_in_tissue",
        NodeType.ENHANCER,
        NodeType.TISSUE,
        RelationKind.REGULATORY,
        True,
        "Bulk ATAC / DNase-seq",
    ),
    Relation(
        "enhancer_associated_disease",
        NodeType.ENHANCER,
        NodeType.DISEASE,
        RelationKind.DISEASE_ASSOC,
        False,
        "GWAS overlap",
    ),
    # ── Expression ──────────────────────────────────────────────────────────
    Relation(
        "gene_coexpressed_gene",
        NodeType.GENE,
        NodeType.GENE,
        RelationKind.EXPRESSION,
        False,
        "Co-expression network",
    ),
    Relation(
        "tissue_expresses_gene",
        NodeType.TISSUE,
        NodeType.GENE,
        RelationKind.EXPRESSION,
        True,
        "GTEx / HPA bulk RNA",
    ),
    Relation(
        "tissue_expresses_protein",
        NodeType.TISSUE,
        NodeType.PROTEIN,
        RelationKind.EXPRESSION,
        True,
        "HPA / proteomics",
    ),
    Relation(
        "cell_type_expresses_gene",
        NodeType.CELL_TYPE,
        NodeType.GENE,
        RelationKind.EXPRESSION,
        True,
        "scRNA-seq (CellxGene)",
    ),
    Relation(
        "cell_type_expresses_protein",
        NodeType.CELL_TYPE,
        NodeType.PROTEIN,
        RelationKind.EXPRESSION,
        True,
        "CyTOF / sc-proteomics",
    ),
    Relation(
        "cell_line_expresses_gene",
        NodeType.CELL_LINE,
        NodeType.GENE,
        RelationKind.EXPERIMENTAL,
        True,
        "RNA-seq (CCLE…)",
    ),
    Relation(
        "cell_line_expresses_protein",
        NodeType.CELL_LINE,
        NodeType.PROTEIN,
        RelationKind.EXPERIMENTAL,
        True,
        "Proteomics (CCLE…)",
    ),
    # ── Physical ────────────────────────────────────────────────────────────
    Relation(
        "protein_interacts_protein",
        NodeType.PROTEIN,
        NodeType.PROTEIN,
        RelationKind.PHYSICAL,
        True,
        "PPI (STRING, IntAct…)",
    ),
    # ── Pathway ─────────────────────────────────────────────────────────────
    Relation(
        "pathway_contains_gene",
        NodeType.PATHWAY,
        NodeType.GENE,
        RelationKind.PATHWAY,
        False,
        "Reactome / GO",
    ),
    Relation(
        "pathway_contains_protein",
        NodeType.PATHWAY,
        NodeType.PROTEIN,
        RelationKind.PATHWAY,
        False,
        "Reactome / KEGG",
    ),
    Relation(
        "pathway_child_of_pathway",
        NodeType.PATHWAY,
        NodeType.PATHWAY,
        RelationKind.ONTOLOGICAL,
        True,
        "Reactome hierarchy",
    ),
    Relation(
        "molecule_in_pathway",
        NodeType.MOLECULE,
        NodeType.PATHWAY,
        RelationKind.PATHWAY,
        False,
        "Metabolic pathway",
    ),
    # ── Pharmacological ─────────────────────────────────────────────────────
    Relation(
        "molecule_targets_protein",
        NodeType.MOLECULE,
        NodeType.PROTEIN,
        RelationKind.PHARMACOLOGICAL,
        True,
        "Drug-target binding",
    ),
    Relation(
        "molecule_treats_disease",
        NodeType.MOLECULE,
        NodeType.DISEASE,
        RelationKind.PHARMACOLOGICAL,
        False,
        "Indication (clinical)",
    ),
    Relation(
        "molecule_contraindicates_disease",
        NodeType.MOLECULE,
        NodeType.DISEASE,
        RelationKind.PHARMACOLOGICAL,
        False,
        "Contraindication",
    ),
    Relation(
        "molecule_interacts_molecule",
        NodeType.MOLECULE,
        NodeType.MOLECULE,
        RelationKind.PHARMACOLOGICAL,
        False,
        "Drug-drug interaction",
    ),
    Relation(
        "cell_type_responds_to_molecule",
        NodeType.CELL_TYPE,
        NodeType.MOLECULE,
        RelationKind.PHARMACOLOGICAL,
        False,
        "Drug screen / perturbation",
    ),
    Relation(
        "cell_line_responds_to_molecule",
        NodeType.CELL_LINE,
        NodeType.MOLECULE,
        RelationKind.EXPERIMENTAL,
        True,
        "GDSC / PRISM viability",
    ),
    Relation(
        "phenotype_associated_molecule",
        NodeType.PHENOTYPE,
        NodeType.MOLECULE,
        RelationKind.PHARMACOLOGICAL,
        False,
        "Side effect / rescue",
    ),
    # ── Disease associations ─────────────────────────────────────────────────
    Relation(
        "disease_associated_gene",
        NodeType.DISEASE,
        NodeType.GENE,
        RelationKind.DISEASE_ASSOC,
        False,
        "GWAS / rare variant",
    ),
    Relation(
        "disease_associated_protein",
        NodeType.DISEASE,
        NodeType.PROTEIN,
        RelationKind.DISEASE_ASSOC,
        False,
        "Proteomics / genetics",
    ),
    Relation(
        "disease_involves_pathway",
        NodeType.DISEASE,
        NodeType.PATHWAY,
        RelationKind.DISEASE_ASSOC,
        False,
        "Pathway enrichment",
    ),
    Relation(
        "disease_associated_mutation",
        NodeType.DISEASE,
        NodeType.MUTATION,
        RelationKind.GENETIC,
        False,
        "ClinVar / GWAS",
    ),
    Relation(
        "disease_manifests_in_tissue",
        NodeType.DISEASE,
        NodeType.TISSUE,
        RelationKind.DISEASE_ASSOC,
        False,
        "Pathology annotation",
    ),
    # ── Disease ontological ──────────────────────────────────────────────────
    Relation(
        "disease_subtype_of_disease",
        NodeType.DISEASE,
        NodeType.DISEASE,
        RelationKind.ONTOLOGICAL,
        True,
        "EFO / MONDO hierarchy",
    ),
    Relation(
        "disease_comorbid_disease",
        NodeType.DISEASE,
        NodeType.DISEASE,
        RelationKind.EPIDEMIOLOGICAL,
        False,
        "Co-occurrence in EHR",
    ),
    Relation(
        "disease_has_phenotype",
        NodeType.DISEASE,
        NodeType.PHENOTYPE,
        RelationKind.PHENOTYPE_ASSOC,
        True,
        "HPO annotation",
    ),
    # ── Phenotype associations ───────────────────────────────────────────────
    Relation(
        "phenotype_observed_in_tissue",
        NodeType.PHENOTYPE,
        NodeType.TISSUE,
        RelationKind.PHENOTYPE_ASSOC,
        False,
        "Anatomical manifestation",
    ),
    Relation(
        "phenotype_caused_by_mutation",
        NodeType.PHENOTYPE,
        NodeType.MUTATION,
        RelationKind.GENETIC,
        False,
        "Mendelian causal",
    ),
    Relation(
        "phenotype_associated_gene",
        NodeType.PHENOTYPE,
        NodeType.GENE,
        RelationKind.PHENOTYPE_ASSOC,
        False,
        "HPO-gene annotation",
    ),
    Relation(
        "phenotype_associated_protein",
        NodeType.PHENOTYPE,
        NodeType.PROTEIN,
        RelationKind.PHENOTYPE_ASSOC,
        False,
        "Inferred via gene",
    ),
    Relation(
        "phenotype_associated_cell_type",
        NodeType.PHENOTYPE,
        NodeType.CELL_TYPE,
        RelationKind.PHENOTYPE_ASSOC,
        False,
        "Cell type enrichment",
    ),
    Relation(
        "phenotype_subtype_of_phenotype",
        NodeType.PHENOTYPE,
        NodeType.PHENOTYPE,
        RelationKind.ONTOLOGICAL,
        True,
        "HPO hierarchy",
    ),
    # ── Tissue ───────────────────────────────────────────────────────────────
    Relation(
        "tissue_subtype_of_tissue",
        NodeType.TISSUE,
        NodeType.TISSUE,
        RelationKind.ONTOLOGICAL,
        True,
        "UBERON parent-child hierarchy",
    ),
    # ── Cell type ────────────────────────────────────────────────────────────
    Relation(
        "cell_type_found_in_tissue",
        NodeType.CELL_TYPE,
        NodeType.TISSUE,
        RelationKind.ONTOLOGICAL,
        True,
        "Cell Ontology / UBERON",
    ),
    Relation(
        "cell_type_involved_in_disease",
        NodeType.CELL_TYPE,
        NodeType.DISEASE,
        RelationKind.DISEASE_ASSOC,
        False,
        "scRNA disease enrichment",
    ),
    Relation(
        "cell_type_subtype_of_cell_type",
        NodeType.CELL_TYPE,
        NodeType.CELL_TYPE,
        RelationKind.ONTOLOGICAL,
        True,
        "Cell Ontology IS-A",
    ),
    # ── Cell line ────────────────────────────────────────────────────────────
    Relation(
        "cell_line_models_disease",
        NodeType.CELL_LINE,
        NodeType.DISEASE,
        RelationKind.EXPERIMENTAL,
        False,
        "Curated annotation",
    ),
    Relation(
        "cell_line_derived_from_cell_type",
        NodeType.CELL_LINE,
        NodeType.CELL_TYPE,
        RelationKind.EXPERIMENTAL,
        True,
        "Cellosaurus",
    ),
    Relation(
        "cell_line_derived_from_tissue",
        NodeType.CELL_LINE,
        NodeType.TISSUE,
        RelationKind.EXPERIMENTAL,
        True,
        "Cellosaurus origin",
    ),
    Relation(
        "cell_line_from_organism",
        NodeType.CELL_LINE,
        NodeType.ORGANISM,
        RelationKind.METADATA,
        True,
        "Donor species",
    ),
    Relation(
        "cell_line_associated_disease",
        NodeType.CELL_LINE,
        NodeType.DISEASE,
        RelationKind.EXPERIMENTAL,
        False,
        "Added by user",
    ),
    # ── Organism ─────────────────────────────────────────────────────────────
    Relation(
        "organism_has_gene",
        NodeType.ORGANISM,
        NodeType.GENE,
        RelationKind.GENETIC,
        True,
        "Ensembl species",
    ),
    Relation(
        "organism_models_disease",
        NodeType.ORGANISM,
        NodeType.DISEASE,
        RelationKind.EXPERIMENTAL,
        False,
        "MGI / Alliance",
    ),
    Relation(
        "organism_has_tissue",
        NodeType.ORGANISM,
        NodeType.TISSUE,
        RelationKind.ONTOLOGICAL,
        True,
        "Anatomy ontology",
    ),
    # ── Literature ───────────────────────────────────────────────────────────
    Relation(
        "paper_mentions_gene",
        NodeType.PAPER,
        NodeType.GENE,
        RelationKind.LITERATURE,
        False,
        "NLP / Europe PMC",
    ),
    Relation(
        "paper_mentions_disease",
        NodeType.PAPER,
        NodeType.DISEASE,
        RelationKind.LITERATURE,
        False,
        "NLP / Europe PMC",
    ),
    Relation(
        "paper_mentions_protein",
        NodeType.PAPER,
        NodeType.PROTEIN,
        RelationKind.LITERATURE,
        False,
        "NLP / Europe PMC",
    ),
    Relation(
        "paper_mentions_molecule",
        NodeType.PAPER,
        NodeType.MOLECULE,
        RelationKind.LITERATURE,
        False,
        "NLP / Europe PMC",
    ),
    Relation(
        "paper_mentions_mutation",
        NodeType.PAPER,
        NodeType.MUTATION,
        RelationKind.LITERATURE,
        False,
        "NLP / Europe PMC",
    ),
    Relation(
        "paper_mentions_pathway",
        NodeType.PAPER,
        NodeType.PATHWAY,
        RelationKind.LITERATURE,
        False,
        "NLP / Europe PMC",
    ),
    Relation(
        "paper_produced_dataset",
        NodeType.PAPER,
        NodeType.DATASET,
        RelationKind.METADATA,
        True,
        "Provenance",
    ),
    Relation(
        "paper_cites_paper",
        NodeType.PAPER,
        NodeType.PAPER,
        RelationKind.LITERATURE,
        True,
        "Citation graph",
    ),
    # ── Dataset metadata ─────────────────────────────────────────────────────
    Relation(
        "dataset_contains_gene",
        NodeType.DATASET,
        NodeType.GENE,
        RelationKind.METADATA,
        True,
        "Measured entity",
    ),
    Relation(
        "dataset_contains_disease",
        NodeType.DATASET,
        NodeType.DISEASE,
        RelationKind.METADATA,
        True,
        "Measured entity",
    ),
    Relation(
        "dataset_contains_molecule",
        NodeType.DATASET,
        NodeType.MOLECULE,
        RelationKind.METADATA,
        True,
        "Measured entity",
    ),
    Relation(
        "dataset_contains_cell_type",
        NodeType.DATASET,
        NodeType.CELL_TYPE,
        RelationKind.METADATA,
        True,
        "Measured entity",
    ),
    Relation(
        "dataset_contains_cell_line",
        NodeType.DATASET,
        NodeType.CELL_LINE,
        RelationKind.METADATA,
        True,
        "Measured entity",
    ),
    Relation(
        "dataset_contains_tissue",
        NodeType.DATASET,
        NodeType.TISSUE,
        RelationKind.METADATA,
        True,
        "Measured entity",
    ),
]

# Fast lookup by relation name
RELATION_BY_NAME: dict[str, Relation] = {r.name: r for r in RELATIONS}

# Fast lookup: all relations for a given source node type
RELATIONS_BY_SOURCE: dict[NodeType, list[Relation]] = {}
for _r in RELATIONS:
    RELATIONS_BY_SOURCE.setdefault(_r.source, []).append(_r)

# Fast lookup: all relations for a given target node type
RELATIONS_BY_TARGET: dict[NodeType, list[Relation]] = {}
for _r in RELATIONS:
    RELATIONS_BY_TARGET.setdefault(_r.target, []).append(_r)


# ---------------------------------------------------------------------------
# Edge Parquet schema (column names and dtypes description)
# ---------------------------------------------------------------------------

EDGE_PARQUET_COLUMNS: list[tuple[str, str]] = [
    ("x_id", "str  — primary ontology ID of the source node"),
    ("x_type", "str  — NodeType value of the source node"),
    ("y_id", "str  — primary ontology ID of the target node"),
    ("y_type", "str  — NodeType value of the target node"),
    ("relation", "str  — canonical Relation.name"),
    ("display_relation", "str  — human-readable label"),
    ("source", "str  — database / dataset the edge came from"),
    ("credibility", "int  — 1 | 2 | 3 (Credibility enum value)"),
]

# Node Parquet files always contain the primary ID column plus whatever
# is listed in NodeTypeInfo.xref_columns.  Additional domain-specific
# columns (name, description, …) may be present but are not required.
NODE_PARQUET_PRIMARY_COLUMN = "id"  # always the primary ontology ID


# ---------------------------------------------------------------------------
# Cross-reference resolution helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class XrefResolution:
    """Describes how to resolve an external ID to the primary ontology ID.

    This represents the direction *from* an external namespace *to* the
    node's canonical primary ID.  The column_name matches the corresponding
    entry in ``NodeTypeInfo.xref_columns``.

    Attributes:
        node_type:      Node type this resolution applies to.
        xref_column:    Column name where the external ID is stored (matches
                        an entry in ``NodeTypeInfo.xref_columns``).
        from_namespace: Human-readable name of the external namespace.
        description:    How the resolution is performed.
        url_template:   Optional API URL to resolve one external ID → primary
                        ID.  Use ``{id}`` as a placeholder for the external ID.
    """

    node_type: NodeType
    xref_column: str
    from_namespace: str
    description: str
    url_template: str = ""


XREF_RESOLUTION: list[XrefResolution] = [
    # ── Gene ─────────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.GENE,
        xref_column="ncbi_gene_id",
        from_namespace="NCBI Gene ID",
        description="NCBI Entrez Gene ID → Ensembl Gene ID via MyGene.info or Ensembl BioMart",
        url_template="https://mygene.info/v3/gene/{id}?fields=ensembl.gene",
    ),
    XrefResolution(
        node_type=NodeType.GENE,
        xref_column="hgnc_id",
        from_namespace="HGNC",
        description="HGNC gene symbol → Ensembl Gene ID via HGNC REST API",
        url_template="https://rest.genenames.org/fetch/symbol/{id}",
    ),
    XrefResolution(
        node_type=NodeType.GENE,
        xref_column="uniprot_id",
        from_namespace="UniProt",
        description="UniProt accession → Ensembl Gene ID via UniProt ID mapping",
        url_template="https://rest.uniprot.org/uniprotkb/{id}?fields=xref_ensembl",
    ),
    # ── Protein ───────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.PROTEIN,
        xref_column="ensembl_gene_id",
        from_namespace="Ensembl Gene ID",
        description="Ensembl Gene ID → UniProt accession via Ensembl BioMart (swissprot)",
        url_template="https://rest.ensembl.org/xrefs/id/{id}?content-type=application/json&external_db=Uniprot/SWISSPROT",
    ),
    XrefResolution(
        node_type=NodeType.PROTEIN,
        xref_column="refseq_protein",
        from_namespace="RefSeq Protein",
        description="RefSeq NP_ → UniProt via UniProt ID mapping",
        url_template="https://rest.uniprot.org/uniprotkb/search?query=xref:refseq:{id}&fields=accession",
    ),
    # ── Disease ───────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.DISEASE,
        xref_column="mondo_id",
        from_namespace="MONDO",
        description="MONDO ID → EFO via OXO cross-reference service",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=EFO",
    ),
    XrefResolution(
        node_type=NodeType.DISEASE,
        xref_column="omim_id",
        from_namespace="OMIM",
        description="OMIM MIM number → EFO via MONDO owl mappings (skos:exactMatch)",
    ),
    XrefResolution(
        node_type=NodeType.DISEASE,
        xref_column="doid_id",
        from_namespace="DOID",
        description="Disease Ontology ID → EFO via OXO",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=EFO",
    ),
    XrefResolution(
        node_type=NodeType.DISEASE,
        xref_column="icd10_code",
        from_namespace="ICD-10",
        description="ICD-10 code → EFO via EFO annotations or MONDO mappings",
    ),
    XrefResolution(
        node_type=NodeType.DISEASE,
        xref_column="mesh_id",
        from_namespace="MeSH",
        description="MeSH disease descriptor → EFO via UMLS / OXO mappings",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=EFO",
    ),
    # ── Phenotype ─────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.PHENOTYPE,
        xref_column="mondo_id",
        from_namespace="MONDO",
        description="MONDO disease term used as phenotype cross-reference via HPO annotations",
    ),
    XrefResolution(
        node_type=NodeType.PHENOTYPE,
        xref_column="efo_id",
        from_namespace="EFO",
        description="EFO term → HPO via OXO",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=HP",
    ),
    XrefResolution(
        node_type=NodeType.PHENOTYPE,
        xref_column="mp_id",
        from_namespace="Mammalian Phenotype Ontology",
        description="MP term → HP (mouse-to-human phenotype translation) via HPO annotations",
    ),
    # ── Molecule ──────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.MOLECULE,
        xref_column="drugbank_id",
        from_namespace="DrugBank",
        description="DrugBank accession → ChEMBL via UniChem",
        url_template="https://www.ebi.ac.uk/unichem/api/v1/compounds?sourceId={id}&sourceName=drugbank",
    ),
    XrefResolution(
        node_type=NodeType.MOLECULE,
        xref_column="pubchem_cid",
        from_namespace="PubChem CID",
        description="PubChem compound ID → ChEMBL via UniChem",
        url_template="https://www.ebi.ac.uk/unichem/api/v1/compounds?sourceId={id}&sourceName=pubchem",
    ),
    XrefResolution(
        node_type=NodeType.MOLECULE,
        xref_column="inchikey",
        from_namespace="InChIKey",
        description="Standard InChIKey → ChEMBL via ChEMBL compound search",
        url_template="https://www.ebi.ac.uk/chembl/api/data/compound_structures?standard_inchi_key={id}",
    ),
    XrefResolution(
        node_type=NodeType.MOLECULE,
        xref_column="cas_rn",
        from_namespace="CAS Registry Number",
        description="CAS RN → ChEMBL via UniChem",
    ),
    # ── Tissue ────────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.TISSUE,
        xref_column="bto_id",
        from_namespace="BTO",
        description="BRENDA Tissue Ontology → UBERON via OXO",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=UBERON",
    ),
    # ── Pathway ───────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.PATHWAY,
        xref_column="go_id",
        from_namespace="GO",
        description="Gene Ontology term → Reactome pathway via Reactome GO cross-references",
    ),
    XrefResolution(
        node_type=NodeType.PATHWAY,
        xref_column="kegg_id",
        from_namespace="KEGG",
        description="KEGG Pathway ID → Reactome via BioMart / pathway mapping files",
    ),
    # ── Transcript ────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.TRANSCRIPT,
        xref_column="refseq_mrna",
        from_namespace="RefSeq mRNA",
        description="RefSeq NM_ → Ensembl Transcript ID via Ensembl",
        url_template="https://rest.ensembl.org/xrefs/symbol/homo_sapiens/{id}?content-type=application/json&external_db=RefSeq_mRNA",
    ),
    # ── Mutation ─────────────────────────────────────────────────────────
    XrefResolution(
        node_type=NodeType.MUTATION,
        xref_column="hgvs",
        from_namespace="HGVS",
        description="HGVS notation → dbSNP rsID via Ensembl Variation API",
    ),
    XrefResolution(
        node_type=NodeType.MUTATION,
        xref_column="clinvar_id",
        from_namespace="ClinVar VariationID",
        description="ClinVar variation ID → dbSNP rsID via ClinVar API",
    ),
]

# Lookup: all xref resolutions for a given (xref_column, node_type) pair
XREF_BY_COLUMN: dict[tuple[str, NodeType], XrefResolution] = {
    (x.xref_column, x.node_type): x for x in XREF_RESOLUTION
}


# ---------------------------------------------------------------------------
# Legacy TxGNN node type → new NodeType mapping
# ---------------------------------------------------------------------------

LEGACY_NODE_TYPE_MAP: dict[str, NodeType] = {
    "gene/protein": NodeType.GENE,  # TxGNN conflates gene+protein; split on load
    "drug": NodeType.MOLECULE,
    "disease": NodeType.DISEASE,
    "effect/phenotype": NodeType.PHENOTYPE,
    "anatomy": NodeType.TISSUE,
    "biological_process": NodeType.PATHWAY,
    "molecular_function": NodeType.PATHWAY,
    "cellular_component": NodeType.PATHWAY,
    "pathway": NodeType.PATHWAY,
    "exposure": NodeType.MOLECULE,  # environmental perturbation
}

# Legacy TxGNN relation → new canonical Relation.name
LEGACY_RELATION_MAP: dict[str, str] = {
    "indication": "molecule_treats_disease",
    "contraindication": "molecule_contraindicates_disease",
    "off-label use": "molecule_treats_disease",
    "target": "molecule_targets_protein",
    "enzyme": "molecule_targets_protein",
    "transporter": "molecule_targets_protein",
    "carrier": "molecule_targets_protein",
    "biomarker": "disease_associated_gene",
    "disease_protein": "disease_associated_protein",
    "protein_protein": "protein_interacts_protein",
    "drug_protein": "molecule_targets_protein",
    "drug_drug": "molecule_interacts_molecule",
    "phenotype_protein": "phenotype_associated_protein",
    "phenotype_phenotype": "phenotype_subtype_of_phenotype",
    "disease_phenotype_positive": "disease_has_phenotype",
    "disease_phenotype_negative": "disease_has_phenotype",
    "disease_disease": "disease_subtype_of_disease",
    "anatomy_protein_present": "tissue_expresses_protein",
    "anatomy_protein_absent": "tissue_expresses_protein",
    "anatomy_anatomy": "tissue_subtype_of_tissue",
    "drug_disease": "molecule_treats_disease",
    "drug_effect": "phenotype_associated_molecule",
    "pathway_pathway": "pathway_child_of_pathway",
    "pathway_protein": "pathway_contains_protein",
    "protein_pathway": "pathway_contains_protein",  # alternate form
    "drug_pathway": "molecule_in_pathway",
    "disease_pathway": "disease_involves_pathway",
    # GO term → gene/protein edges (biological_process / molfunc / cellcomp)
    "bioprocess_protein": "pathway_contains_gene",
    "molfunc_protein": "pathway_contains_gene",
    "cellcomp_protein": "pathway_contains_gene",
    # GO term hierarchies
    "bioprocess_bioprocess": "pathway_child_of_pathway",
    "molfunc_molfunc": "pathway_child_of_pathway",
    "cellcomp_cellcomp": "pathway_child_of_pathway",
    # Exposure (environmental molecule) edges
    "exposure_disease": "molecule_treats_disease",
    "exposure_protein": "molecule_targets_protein",
    "exposure_bioprocess": "molecule_in_pathway",
    "exposure_molfunc": "molecule_in_pathway",
    "exposure_cellcomp": "molecule_in_pathway",
    "exposure_exposure": "molecule_interacts_molecule",
    "biomarker_disease": "disease_associated_gene",
}


# Relations where the legacy edge (x→y) direction is the *reverse* of the
# canonical relation direction and therefore x/y must be swapped on migration.
LEGACY_RELATION_FLIP: frozenset[str] = frozenset(
    {
        "disease_protein",  # gene/protein→disease  → flip → disease→gene  (disease_associated_protein)
        "anatomy_protein_present",  # gene/protein→anatomy  → flip → tissue→gene   (tissue_expresses_protein)
        "anatomy_protein_absent",  # gene/protein→anatomy  → flip → tissue→gene   (tissue_expresses_protein)
        "bioprocess_protein",  # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_gene)
        "molfunc_protein",  # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_gene)
        "cellcomp_protein",  # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_gene)
        "pathway_protein",  # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_protein)
        "phenotype_protein",  # gene/protein→phenotype→ flip → phenotype→gene (phenotype_associated_protein)
        "drug_effect",  # drug→effect/phenotype → flip → phenotype→molecule (phenotype_associated_molecule)
    }
)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def relation_names() -> list[str]:
    """Return all canonical relation names."""
    return [r.name for r in RELATIONS]


def node_type_names() -> list[str]:
    """Return all node type string values."""
    return [nt.value for nt in NodeType]


def relations_between(source: NodeType, target: NodeType) -> list[Relation]:
    """Return all relations with the given source and target node types."""
    return [r for r in RELATIONS_BY_SOURCE.get(source, []) if r.target == target]


def xref_columns_for(node_type: NodeType) -> tuple[str, ...]:
    """Return the cross-reference column names for a node type."""
    return NODE_TYPES[node_type].xref_columns


def primary_ontology_for(node_type: NodeType) -> str:
    """Return the primary ontology name for a node type."""
    return NODE_TYPES[node_type].primary_ontology
