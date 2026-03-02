"""Single source of truth for the TxGNN expanded knowledge graph schema.

Defines:
- Node types with their primary ontology namespaces (``NODE_TYPES``)
- Relation taxonomy (``RELATIONS``) with kind, direct flag, source/target types
- Credibility scoring constants
- Cross-reference / alias namespace tables
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Optional


# ---------------------------------------------------------------------------
# Credibility scores
# ---------------------------------------------------------------------------

class Credibility(int, Enum):
    """Evidence credibility level for edges."""
    SINGLE_EVIDENCE = 1       # one paper, possibly same authors
    MULTI_EVIDENCE = 2        # multiple independent evidence sources
    ESTABLISHED_FACT = 3      # curated DB, no ambiguity


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
    node_type: NodeType
    primary_ontology: str
    id_format: str
    bionty_registry: Optional[str]
    example_id: str


NODE_TYPES: dict[NodeType, NodeTypeInfo] = {
    NodeType.PAPER: NodeTypeInfo(
        node_type=NodeType.PAPER,
        primary_ontology="PubMed / DOI",
        id_format="PMID:<int> or DOI:<string>",
        bionty_registry=None,
        example_id="PMID:12345678",
    ),
    NodeType.GENE: NodeTypeInfo(
        node_type=NodeType.GENE,
        primary_ontology="Ensembl Gene ID",
        id_format="ENSG<11digits>",
        bionty_registry="bionty.Gene",
        example_id="ENSG00000139618",
    ),
    NodeType.TRANSCRIPT: NodeTypeInfo(
        node_type=NodeType.TRANSCRIPT,
        primary_ontology="Ensembl Transcript ID",
        id_format="ENST<11digits>",
        bionty_registry=None,
        example_id="ENST00000380152",
    ),
    NodeType.PROTEIN: NodeTypeInfo(
        node_type=NodeType.PROTEIN,
        primary_ontology="UniProt accession",
        id_format="[A-Z][0-9][A-Z0-9]{3}[0-9] or [OPQ][0-9][A-Z0-9]{3}[0-9]",
        bionty_registry=None,
        example_id="P38398",
    ),
    NodeType.PATHWAY: NodeTypeInfo(
        node_type=NodeType.PATHWAY,
        primary_ontology="Reactome / GO",
        id_format="R-HSA-<int> or GO:<7digits>",
        bionty_registry="bionty.Pathway",
        example_id="R-HSA-5633007",
    ),
    NodeType.MOLECULE: NodeTypeInfo(
        node_type=NodeType.MOLECULE,
        primary_ontology="ChEMBL ID / InChIKey",
        id_format="CHEMBL<int> or InChIKey=<27chars>",
        bionty_registry="pertdb.Compound",
        example_id="CHEMBL941",
    ),
    NodeType.MUTATION: NodeTypeInfo(
        node_type=NodeType.MUTATION,
        primary_ontology="dbSNP rsID / HGVS",
        id_format="rs<int> or HGVS notation",
        bionty_registry=None,
        example_id="rs7412",
    ),
    NodeType.DISEASE: NodeTypeInfo(
        node_type=NodeType.DISEASE,
        primary_ontology="MONDO / EFO / HP",
        id_format="MONDO:<7digits> or EFO:<7digits>",
        bionty_registry="bionty.Disease",
        example_id="MONDO:0007254",
    ),
    NodeType.CELL_TYPE: NodeTypeInfo(
        node_type=NodeType.CELL_TYPE,
        primary_ontology="Cell Ontology",
        id_format="CL:<7digits>",
        bionty_registry="bionty.CellType",
        example_id="CL:0000576",
    ),
    NodeType.TISSUE: NodeTypeInfo(
        node_type=NodeType.TISSUE,
        primary_ontology="UBERON",
        id_format="UBERON:<7digits>",
        bionty_registry="bionty.Tissue",
        example_id="UBERON:0002107",
    ),
    NodeType.PHENOTYPE: NodeTypeInfo(
        node_type=NodeType.PHENOTYPE,
        primary_ontology="Human Phenotype Ontology",
        id_format="HP:<7digits>",
        bionty_registry="bionty.Phenotype",
        example_id="HP:0000118",
    ),
    NodeType.CELL_LINE: NodeTypeInfo(
        node_type=NodeType.CELL_LINE,
        primary_ontology="Cellosaurus",
        id_format="CVCL_<4chars>",
        bionty_registry="bionty.CellLine",
        example_id="CVCL_0023",
    ),
    NodeType.ORGANISM: NodeTypeInfo(
        node_type=NodeType.ORGANISM,
        primary_ontology="NCBI Taxonomy",
        id_format="<int>",
        bionty_registry="bionty.Organism",
        example_id="9606",
    ),
    NodeType.DATASET: NodeTypeInfo(
        node_type=NodeType.DATASET,
        primary_ontology="Internal UUID / DOI",
        id_format="UUID4 or DOI:<string>",
        bionty_registry=None,
        example_id="DOI:10.1038/s41586-023-06221-2",
    ),
    NodeType.ENHANCER: NodeTypeInfo(
        node_type=NodeType.ENHANCER,
        primary_ontology="ENCODE / Ensembl Regulatory Build",
        id_format="EH38E<int> or ENCODE:ENC*",
        bionty_registry=None,
        example_id="EH38E1516972",
    ),
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
    Relation("gene_has_transcript",           NodeType.GENE,       NodeType.TRANSCRIPT, RelationKind.CENTRAL_DOGMA,   True,  "Transcription"),
    Relation("transcript_encodes_protein",    NodeType.TRANSCRIPT, NodeType.PROTEIN,    RelationKind.CENTRAL_DOGMA,   True,  "Translation"),
    Relation("gene_encodes_protein",          NodeType.GENE,       NodeType.PROTEIN,    RelationKind.CENTRAL_DOGMA,   False,  "Shortcut edge"),
    Relation("transcript_alternative_transcript", NodeType.TRANSCRIPT, NodeType.TRANSCRIPT, RelationKind.CENTRAL_DOGMA, True, "Alternative splicing"),

    # ── Genetic ─────────────────────────────────────────────────────────────
    Relation("mutation_in_gene",                   NodeType.MUTATION, NodeType.GENE,      RelationKind.GENETIC,    True,  "Genomic position"),
    Relation("mutation_affects_transcript",         NodeType.MUTATION, NodeType.TRANSCRIPT,RelationKind.GENETIC,    True,  "Splicing / UTR variant"),
    Relation("mutation_causes_protein_change",      NodeType.MUTATION, NodeType.PROTEIN,   RelationKind.GENETIC,    True,  "Amino acid change"),
    Relation("mutation_overlaps_enhancer",          NodeType.MUTATION, NodeType.ENHANCER,  RelationKind.GENETIC,    True,  "Regulatory variant"),
    Relation("mutation_associated_disease",         NodeType.MUTATION, NodeType.DISEASE,   RelationKind.GENETIC,    False, "GWAS / ClinVar"),
    Relation("mutation_causes_phenotype",           NodeType.MUTATION, NodeType.PHENOTYPE, RelationKind.GENETIC,    False, "Mendelian / GWAS"),
    Relation("mutation_affects_molecule_response",  NodeType.MUTATION, NodeType.MOLECULE,  RelationKind.PHARMACOLOGICAL, False, "Pharmacogenomics"),
    Relation("mutation_associated_cell_type",       NodeType.MUTATION, NodeType.CELL_TYPE, RelationKind.GENETIC,    False, "eQTL cell-type enrichment"),
    Relation("gene_ortholog_gene",                  NodeType.GENE,     NodeType.GENE,      RelationKind.GENETIC,    False,  "Cross-species orthology"),

    # ── Regulatory ──────────────────────────────────────────────────────────
    Relation("enhancer_regulates_gene",         NodeType.ENHANCER,   NodeType.GENE,      RelationKind.REGULATORY,  False, "ChIP-seq / Hi-C"),
    Relation("enhancer_regulates_transcript",   NodeType.ENHANCER,   NodeType.TRANSCRIPT,RelationKind.REGULATORY,  True, "TSS-specific regulation"),
    Relation("enhancer_active_in_cell_type",    NodeType.ENHANCER,   NodeType.CELL_TYPE, RelationKind.REGULATORY,  True, "ATAC-seq / ChIP-seq"),
    Relation("enhancer_active_in_tissue",       NodeType.ENHANCER,   NodeType.TISSUE,    RelationKind.REGULATORY,  True, "Bulk ATAC / DNase-seq"),
    Relation("enhancer_associated_disease",     NodeType.ENHANCER,   NodeType.DISEASE,   RelationKind.DISEASE_ASSOC, False, "GWAS overlap"),

    # ── Expression ──────────────────────────────────────────────────────────
    Relation("gene_coexpressed_gene",        NodeType.GENE,      NodeType.GENE,    RelationKind.EXPRESSION, False, "Co-expression network"),
    Relation("tissue_expresses_gene",        NodeType.TISSUE,    NodeType.GENE,    RelationKind.EXPRESSION, True,  "GTEx / HPA bulk RNA"),
    Relation("tissue_expresses_protein",     NodeType.TISSUE,    NodeType.PROTEIN, RelationKind.EXPRESSION, True,  "HPA / proteomics"),
    Relation("cell_type_expresses_gene",     NodeType.CELL_TYPE, NodeType.GENE,    RelationKind.EXPRESSION, True,  "scRNA-seq (CellxGene)"),
    Relation("cell_type_expresses_protein",  NodeType.CELL_TYPE, NodeType.PROTEIN, RelationKind.EXPRESSION, True,  "CyTOF / sc-proteomics"),
    Relation("cell_line_expresses_gene",     NodeType.CELL_LINE, NodeType.GENE,    RelationKind.EXPERIMENTAL, True, "RNA-seq (CCLE…)"),
    Relation("cell_line_expresses_protein",  NodeType.CELL_LINE, NodeType.PROTEIN, RelationKind.EXPERIMENTAL, True, "Proteomics (CCLE…)"),

    # ── Physical ────────────────────────────────────────────────────────────
    Relation("protein_interacts_protein", NodeType.PROTEIN, NodeType.PROTEIN, RelationKind.PHYSICAL, True, "PPI (STRING, IntAct…)"),

    # ── Pathway ─────────────────────────────────────────────────────────────
    Relation("pathway_contains_gene",    NodeType.PATHWAY,  NodeType.GENE,    RelationKind.PATHWAY, False, "Reactome / GO"),
    Relation("pathway_contains_protein", NodeType.PATHWAY,  NodeType.PROTEIN, RelationKind.PATHWAY, False, "Reactome / KEGG"),
    Relation("pathway_child_of_pathway", NodeType.PATHWAY,  NodeType.PATHWAY, RelationKind.ONTOLOGICAL, True, "Reactome hierarchy"),
    Relation("molecule_in_pathway",      NodeType.MOLECULE, NodeType.PATHWAY, RelationKind.PATHWAY, False, "Metabolic pathway"),

    # ── Pharmacological ─────────────────────────────────────────────────────
    Relation("molecule_targets_protein",         NodeType.MOLECULE, NodeType.PROTEIN,  RelationKind.PHARMACOLOGICAL, True,  "Drug-target binding"),
    Relation("molecule_treats_disease",          NodeType.MOLECULE, NodeType.DISEASE,  RelationKind.PHARMACOLOGICAL, False, "Indication (clinical)"),
    Relation("molecule_contraindicates_disease", NodeType.MOLECULE, NodeType.DISEASE,  RelationKind.PHARMACOLOGICAL, False, "Contraindication"),
    Relation("molecule_interacts_molecule",      NodeType.MOLECULE, NodeType.MOLECULE, RelationKind.PHARMACOLOGICAL, False, "Drug-drug interaction"),
    Relation("cell_type_responds_to_molecule",   NodeType.CELL_TYPE, NodeType.MOLECULE,RelationKind.PHARMACOLOGICAL, False, "Drug screen / perturbation"),
    Relation("cell_line_responds_to_molecule",   NodeType.CELL_LINE, NodeType.MOLECULE,RelationKind.EXPERIMENTAL,   True,  "GDSC / PRISM viability"),
    Relation("phenotype_associated_molecule",    NodeType.PHENOTYPE, NodeType.MOLECULE,RelationKind.PHARMACOLOGICAL, False, "Side effect / rescue"),

    # ── Disease associations ─────────────────────────────────────────────────
    Relation("disease_associated_gene",     NodeType.DISEASE, NodeType.GENE,     RelationKind.DISEASE_ASSOC,  False, "GWAS / rare variant"),
    Relation("disease_associated_protein",  NodeType.DISEASE, NodeType.PROTEIN,  RelationKind.DISEASE_ASSOC,  False, "Proteomics / genetics"),
    Relation("disease_involves_pathway",    NodeType.DISEASE, NodeType.PATHWAY,  RelationKind.DISEASE_ASSOC,  False, "Pathway enrichment"),
    Relation("disease_associated_mutation", NodeType.DISEASE, NodeType.MUTATION, RelationKind.GENETIC,        False, "ClinVar / GWAS"),
    Relation("disease_manifests_in_tissue", NodeType.DISEASE, NodeType.TISSUE,   RelationKind.DISEASE_ASSOC,  False, "Pathology annotation"),

    # ── Disease ontological ──────────────────────────────────────────────────
    Relation("disease_subtype_of_disease", NodeType.DISEASE, NodeType.DISEASE, RelationKind.ONTOLOGICAL,    True,  "MONDO / EFO hierarchy"),
    Relation("disease_comorbid_disease",   NodeType.DISEASE, NodeType.DISEASE, RelationKind.EPIDEMIOLOGICAL, False, "Co-occurrence in EHR"),
    Relation("disease_has_phenotype",      NodeType.DISEASE, NodeType.PHENOTYPE, RelationKind.PHENOTYPE_ASSOC, True, "HPO annotation"),

    # ── Phenotype associations ───────────────────────────────────────────────
    Relation("phenotype_observed_in_tissue",    NodeType.PHENOTYPE, NodeType.TISSUE,    RelationKind.PHENOTYPE_ASSOC, False, "Anatomical manifestation"),
    Relation("phenotype_caused_by_mutation",    NodeType.PHENOTYPE, NodeType.MUTATION,  RelationKind.GENETIC,         False, "Mendelian causal"),
    Relation("phenotype_associated_gene",       NodeType.PHENOTYPE, NodeType.GENE,      RelationKind.PHENOTYPE_ASSOC, False, "HPO-gene annotation"),
    Relation("phenotype_associated_protein",    NodeType.PHENOTYPE, NodeType.PROTEIN,   RelationKind.PHENOTYPE_ASSOC, False, "Inferred via gene"),
    Relation("phenotype_associated_cell_type",  NodeType.PHENOTYPE, NodeType.CELL_TYPE, RelationKind.PHENOTYPE_ASSOC, False, "Cell type enrichment"),
    Relation("phenotype_subtype_of_phenotype",  NodeType.PHENOTYPE, NodeType.PHENOTYPE, RelationKind.ONTOLOGICAL,     True,  "HPO hierarchy"),

    # ── Tissue ───────────────────────────────────────────────────────────────
    Relation("tissue_subtype_of_tissue", NodeType.TISSUE, NodeType.TISSUE, RelationKind.ONTOLOGICAL, True, "UBERON parent-child hierarchy"),

    # ── Cell type ────────────────────────────────────────────────────────────
    Relation("cell_type_found_in_tissue",     NodeType.CELL_TYPE, NodeType.TISSUE,    RelationKind.ONTOLOGICAL,   True,  "Cell Ontology / UBERON"),
    Relation("cell_type_involved_in_disease", NodeType.CELL_TYPE, NodeType.DISEASE,   RelationKind.DISEASE_ASSOC, False, "scRNA disease enrichment"),
    Relation("cell_type_subtype_of_cell_type",NodeType.CELL_TYPE, NodeType.CELL_TYPE, RelationKind.ONTOLOGICAL,   True,  "Cell Ontology IS-A"),

    # ── Cell line ────────────────────────────────────────────────────────────
    Relation("cell_line_models_disease",         NodeType.CELL_LINE, NodeType.DISEASE,   RelationKind.EXPERIMENTAL, False, "Curated annotation"),
    Relation("cell_line_derived_from_cell_type", NodeType.CELL_LINE, NodeType.CELL_TYPE, RelationKind.EXPERIMENTAL, True,  "Cellosaurus"),
    Relation("cell_line_derived_from_tissue",    NodeType.CELL_LINE, NodeType.TISSUE,    RelationKind.EXPERIMENTAL, True,  "Cellosaurus origin"),
    Relation("cell_line_from_organism",          NodeType.CELL_LINE, NodeType.ORGANISM,  RelationKind.METADATA,     True,  "Donor species"),
    Relation("cell_line_associated_disease",     NodeType.CELL_LINE, NodeType.DISEASE,   RelationKind.EXPERIMENTAL, False, "Added by user"),

    # ── Organism ─────────────────────────────────────────────────────────────
    Relation("organism_has_gene",     NodeType.ORGANISM, NodeType.GENE,    RelationKind.GENETIC,     True, "Ensembl species"),
    Relation("organism_models_disease",NodeType.ORGANISM, NodeType.DISEASE, RelationKind.EXPERIMENTAL, False, "MGI / Alliance"),
    Relation("organism_has_tissue",   NodeType.ORGANISM, NodeType.TISSUE,  RelationKind.ONTOLOGICAL, True,  "Anatomy ontology"),

    # ── Literature ───────────────────────────────────────────────────────────
    Relation("paper_mentions_gene",     NodeType.PAPER, NodeType.GENE,    RelationKind.LITERATURE, False, "NLP / Europe PMC"),
    Relation("paper_mentions_disease",  NodeType.PAPER, NodeType.DISEASE, RelationKind.LITERATURE, False, "NLP / Europe PMC"),
    Relation("paper_mentions_protein",  NodeType.PAPER, NodeType.PROTEIN, RelationKind.LITERATURE, False, "NLP / Europe PMC"),
    Relation("paper_mentions_molecule", NodeType.PAPER, NodeType.MOLECULE,RelationKind.LITERATURE, False, "NLP / Europe PMC"),
    Relation("paper_mentions_mutation", NodeType.PAPER, NodeType.MUTATION,RelationKind.LITERATURE, False, "NLP / Europe PMC"),
    Relation("paper_mentions_pathway",  NodeType.PAPER, NodeType.PATHWAY, RelationKind.LITERATURE, False, "NLP / Europe PMC"),
    Relation("paper_produced_dataset",  NodeType.PAPER, NodeType.DATASET, RelationKind.METADATA,   True,  "Provenance"),
    Relation("paper_cites_paper",       NodeType.PAPER, NodeType.PAPER,   RelationKind.LITERATURE, True,  "Citation graph"),

    # ── Dataset metadata ─────────────────────────────────────────────────────
    Relation("dataset_contains_gene",      NodeType.DATASET, NodeType.GENE,      RelationKind.METADATA, True, "Measured entity"),
    Relation("dataset_contains_disease",   NodeType.DATASET, NodeType.DISEASE,   RelationKind.METADATA, True, "Measured entity"),
    Relation("dataset_contains_molecule",  NodeType.DATASET, NodeType.MOLECULE,  RelationKind.METADATA, True, "Measured entity"),
    Relation("dataset_contains_cell_type", NodeType.DATASET, NodeType.CELL_TYPE, RelationKind.METADATA, True, "Measured entity"),
    Relation("dataset_contains_cell_line", NodeType.DATASET, NodeType.CELL_LINE, RelationKind.METADATA, True, "Measured entity"),
    Relation("dataset_contains_tissue",    NodeType.DATASET, NodeType.TISSUE,    RelationKind.METADATA, True, "Measured entity"),
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
    ("x_id",              "str  — ontology ID of the source node"),
    ("x_type",            "str  — NodeType value of the source node"),
    ("y_id",              "str  — ontology ID of the target node"),
    ("y_type",            "str  — NodeType value of the target node"),
    ("relation",          "str  — canonical Relation.name"),
    ("display_relation",  "str  — human-readable label"),
    ("source",            "str  — database / dataset the edge came from"),
    ("credibility",       "int  — 1 | 2 | 3 (Credibility enum value)"),
]


# ---------------------------------------------------------------------------
# Cross-reference / alias tables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class XrefMapping:
    """Describes a known cross-reference mapping between two ID namespaces."""
    from_namespace: str
    to_namespace: str
    node_type: NodeType
    description: str
    url_template: str = ""         # {id} placeholder for the source ID
    reverse_url_template: str = "" # {id} placeholder for target→source lookup


XREF_MAPPINGS: list[XrefMapping] = [
    # ── Gene / Protein ────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="NCBI Gene ID",
        to_namespace="Ensembl Gene ID",
        node_type=NodeType.GENE,
        description="NCBI → Ensembl via Ensembl BioMart or MyGene.info",
        url_template="https://rest.ensembl.org/xrefs/id/{id}?content-type=application/json",
    ),
    XrefMapping(
        from_namespace="Ensembl Gene ID",
        to_namespace="UniProt accession",
        node_type=NodeType.GENE,
        description="Ensembl Gene → canonical UniProt (swissprot) via Ensembl BioMart",
        url_template="https://rest.ensembl.org/xrefs/id/{id}?content-type=application/json&external_db=Uniprot/SWISSPROT",
    ),

    # ── Disease ───────────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="EFO",
        to_namespace="MONDO",
        node_type=NodeType.DISEASE,
        description="EFO disease → MONDO via OXO cross-reference service or OBO mapping",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=MONDO",
    ),
    XrefMapping(
        from_namespace="OMIM",
        to_namespace="MONDO",
        node_type=NodeType.DISEASE,
        description="OMIM MIM ID → MONDO via MONDO owl mappings (skos:exactMatch, oboInOwl:hasDbXref)",
    ),
    XrefMapping(
        from_namespace="DOID",
        to_namespace="MONDO",
        node_type=NodeType.DISEASE,
        description="Disease Ontology ID → MONDO via MONDO mappings",
    ),
    XrefMapping(
        from_namespace="ICD-10",
        to_namespace="MONDO",
        node_type=NodeType.DISEASE,
        description="ICD-10 code → MONDO via MONDO / EFO mappings",
    ),
    XrefMapping(
        from_namespace="MeSH",
        to_namespace="MONDO",
        node_type=NodeType.DISEASE,
        description="MeSH disease term → MONDO via UMLS / OXO mappings",
    ),

    # ── Phenotype ─────────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="HP",
        to_namespace="MONDO",
        node_type=NodeType.PHENOTYPE,
        description="HPO phenotype → MONDO disease (phenotype→disease via HPO annotations)",
    ),
    XrefMapping(
        from_namespace="HP",
        to_namespace="EFO",
        node_type=NodeType.PHENOTYPE,
        description="HPO → EFO via OXO",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=EFO",
    ),
    XrefMapping(
        from_namespace="MP",
        to_namespace="HP",
        node_type=NodeType.PHENOTYPE,
        description="Mammalian Phenotype Ontology → HPO (mouse→human phenotype translation)",
    ),

    # ── Molecule / Drug ───────────────────────────────────────────────────
    XrefMapping(
        from_namespace="DrugBank ID",
        to_namespace="ChEMBL ID",
        node_type=NodeType.MOLECULE,
        description="DrugBank → ChEMBL via UniChem cross-reference",
        url_template="https://www.ebi.ac.uk/unichem/api/v1/compounds?sourceId={id}&sourceName=drugbank",
    ),
    XrefMapping(
        from_namespace="ChEMBL ID",
        to_namespace="DrugBank ID",
        node_type=NodeType.MOLECULE,
        description="ChEMBL → DrugBank via UniChem",
        url_template="https://www.ebi.ac.uk/unichem/api/v1/compounds?sourceId={id}&sourceName=chembl",
    ),
    XrefMapping(
        from_namespace="InChIKey",
        to_namespace="ChEMBL ID",
        node_type=NodeType.MOLECULE,
        description="InChIKey → ChEMBL via ChEMBL compound search",
        url_template="https://www.ebi.ac.uk/chembl/api/data/compound_structures?standard_inchi_key={id}",
    ),
    XrefMapping(
        from_namespace="PubChem CID",
        to_namespace="ChEMBL ID",
        node_type=NodeType.MOLECULE,
        description="PubChem CID → ChEMBL via UniChem",
        url_template="https://www.ebi.ac.uk/unichem/api/v1/compounds?sourceId={id}&sourceName=pubchem",
    ),
    XrefMapping(
        from_namespace="CAS RN",
        to_namespace="ChEMBL ID",
        node_type=NodeType.MOLECULE,
        description="CAS Registry Number → ChEMBL via UniChem",
    ),

    # ── Tissue ────────────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="BTO",
        to_namespace="UBERON",
        node_type=NodeType.TISSUE,
        description="BRENDA Tissue Ontology (BTO) → UBERON via OXO",
        url_template="https://www.ebi.ac.uk/spot/oxo/api/mappings?fromId={id}&toDb=UBERON",
    ),

    # ── Pathway ───────────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="Reactome",
        to_namespace="GO",
        node_type=NodeType.PATHWAY,
        description="Reactome pathway → GO Biological Process (Reactome ↔ GO cross-references)",
    ),
    XrefMapping(
        from_namespace="KEGG Pathway",
        to_namespace="Reactome",
        node_type=NodeType.PATHWAY,
        description="KEGG Pathway → Reactome via BioMart / pathway mapping files",
    ),

    # ── Transcript ────────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="Ensembl Transcript ID",
        to_namespace="RefSeq mRNA",
        node_type=NodeType.TRANSCRIPT,
        description="ENST → RefSeq NM_ via Ensembl BioMart",
        url_template="https://rest.ensembl.org/xrefs/id/{id}?content-type=application/json&external_db=RefSeq_mRNA",
    ),
    XrefMapping(
        from_namespace="RefSeq mRNA",
        to_namespace="Ensembl Transcript ID",
        node_type=NodeType.TRANSCRIPT,
        description="RefSeq NM_ → ENST via Ensembl",
    ),

    # ── Mutation ─────────────────────────────────────────────────────────
    XrefMapping(
        from_namespace="dbSNP rsID",
        to_namespace="HGVS",
        node_type=NodeType.MUTATION,
        description="rsID → HGVS notation via Ensembl Variation API",
        url_template="https://rest.ensembl.org/variation/human/{id}?content-type=application/json",
    ),
    XrefMapping(
        from_namespace="ClinVar VariationID",
        to_namespace="dbSNP rsID",
        node_type=NodeType.MUTATION,
        description="ClinVar variation ID → rsID",
    ),
]

# Lookup: all xrefs for a given (from_namespace, node_type) pair
XREF_BY_SOURCE: dict[tuple[str, NodeType], list[XrefMapping]] = {}
for _x in XREF_MAPPINGS:
    XREF_BY_SOURCE.setdefault((_x.from_namespace, _x.node_type), []).append(_x)


# ---------------------------------------------------------------------------
# Legacy TxGNN node type → new NodeType mapping
# ---------------------------------------------------------------------------

LEGACY_NODE_TYPE_MAP: dict[str, NodeType] = {
    "gene/protein":           NodeType.GENE,       # TxGNN conflates gene+protein; split on load
    "drug":                   NodeType.MOLECULE,
    "disease":                NodeType.DISEASE,
    "effect/phenotype":       NodeType.PHENOTYPE,
    "anatomy":                NodeType.TISSUE,
    "biological_process":     NodeType.PATHWAY,
    "molecular_function":     NodeType.PATHWAY,
    "cellular_component":     NodeType.PATHWAY,
    "pathway":                NodeType.PATHWAY,
    "exposure":               NodeType.MOLECULE,   # environmental perturbation
}

# Legacy TxGNN relation → new canonical Relation.name
LEGACY_RELATION_MAP: dict[str, str] = {
    "indication":                  "molecule_treats_disease",
    "contraindication":            "molecule_contraindicates_disease",
    "off-label use":               "molecule_treats_disease",
    "target":                      "molecule_targets_protein",
    "enzyme":                      "molecule_targets_protein",
    "transporter":                 "molecule_targets_protein",
    "carrier":                     "molecule_targets_protein",
    "biomarker":                   "disease_associated_gene",
    "disease_protein":             "disease_associated_protein",
    "protein_protein":             "protein_interacts_protein",
    "drug_protein":                "molecule_targets_protein",
    "drug_drug":                   "molecule_interacts_molecule",
    "phenotype_protein":           "phenotype_associated_protein",
    "phenotype_phenotype":         "phenotype_subtype_of_phenotype",
    "disease_phenotype_positive":  "disease_has_phenotype",
    "disease_phenotype_negative":  "disease_has_phenotype",
    "disease_disease":             "disease_subtype_of_disease",
    "anatomy_protein_present":     "tissue_expresses_protein",
    "anatomy_protein_absent":      "tissue_expresses_protein",
    "anatomy_anatomy":             "tissue_subtype_of_tissue",
    "drug_disease":                "molecule_treats_disease",
    "drug_effect":                 "phenotype_associated_molecule",
    "pathway_pathway":             "pathway_child_of_pathway",
    "pathway_protein":             "pathway_contains_protein",
    "protein_pathway":             "pathway_contains_protein",  # alternate form
    "drug_pathway":                "molecule_in_pathway",
    "disease_pathway":             "disease_involves_pathway",
    # GO term → gene/protein edges (biological_process / molfunc / cellcomp)
    "bioprocess_protein":          "pathway_contains_gene",
    "molfunc_protein":             "pathway_contains_gene",
    "cellcomp_protein":            "pathway_contains_gene",
    # GO term hierarchies
    "bioprocess_bioprocess":       "pathway_child_of_pathway",
    "molfunc_molfunc":             "pathway_child_of_pathway",
    "cellcomp_cellcomp":           "pathway_child_of_pathway",
    # Exposure (environmental molecule) edges
    "exposure_disease":            "molecule_treats_disease",   # CTD exposure→disease (direction: molecule→disease)
    "exposure_protein":            "molecule_targets_protein",
    "exposure_bioprocess":         "molecule_in_pathway",
    "exposure_molfunc":            "molecule_in_pathway",
    "exposure_cellcomp":           "molecule_in_pathway",
    "exposure_exposure":           "molecule_interacts_molecule",
    "biomarker_disease":           "disease_associated_gene",
}


# Relations where the legacy edge (x→y) direction is the *reverse* of the
# canonical relation direction and therefore x/y must be swapped on migration.
#
# Root cause: TxGNN's original edge convention stored some edges as
# (gene/protein → entity) even when the canonical semantics are (entity → gene).
LEGACY_RELATION_FLIP: frozenset[str] = frozenset({
    "disease_protein",           # gene/protein→disease  → flip → disease→gene  (disease_associated_protein)
    "anatomy_protein_present",   # gene/protein→anatomy  → flip → tissue→gene   (tissue_expresses_protein)
    "anatomy_protein_absent",    # gene/protein→anatomy  → flip → tissue→gene   (tissue_expresses_protein)
    "bioprocess_protein",        # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_gene)
    "molfunc_protein",           # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_gene)
    "cellcomp_protein",          # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_gene)
    "pathway_protein",           # gene/protein→pathway  → flip → pathway→gene  (pathway_contains_protein)
    "phenotype_protein",         # gene/protein→phenotype→ flip → phenotype→gene (phenotype_associated_protein)
    "drug_effect",               # drug→effect/phenotype → flip → phenotype→molecule (phenotype_associated_molecule)
})


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
