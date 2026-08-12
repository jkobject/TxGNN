#!/usr/bin/env python3
"""Build the deterministic relation-expansion source/recovery contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manage_db.kg_schema import RELATIONS

DEFAULT_JSON = ROOT / "docs/relation-expansion-source-contract.json"
DEFAULT_MARKDOWN = ROOT / "docs/relation-expansion-source-contract.md"

AVAILABILITY_STATUSES = {
    "current-raw-available",
    "remote-refetch-required",
    "historical-builder-recoverable",
    "historical-artifact-deleted",
    "source-selection-required",
    "accepted-no-row-evidence",
}

NONCANONICAL_RELATIONS = {
    "enhancer_regulates_transcript", "gene_coexpressed_gene",
    "cell_type_expresses_protein", "cell_line_expresses_protein",
    "tf_regulates_gene", "tf_binds_enhancer", "transcript_interacts_protein",
    "transcript_interacts_gene", "pathway_contains_protein",
    "molecule_targets_protein", "cell_type_responds_to_molecule",
    "cell_line_responds_to_molecule", "disease_comorbid_disease",
    "phenotype_observed_in_tissue", "cell_type_found_in_tissue",
    "cell_type_involved_in_disease", "cell_type_subtype_of_cell_type",
    "cell_line_models_disease", "cell_line_derived_from_cell_type",
    "paper_produced_dataset", "paper_cites_paper", "dataset_contains_disease",
    "dataset_contains_molecule", "dataset_contains_cell_type",
}
PROVENANCE_GAPS = {
    "molecule_associated_phenotype", "molecule_contraindicates_disease",
    "molecule_parent_of_molecule", "molecule_synergizes_molecule",
    "molecule_treats_disease",
}
EXPRESSION_RELATIONS = {
    "tissue_expresses_gene", "cell_type_expresses_gene",
    "cell_line_expresses_gene",
}
CONTRACT_RELATIONS = NONCANONICAL_RELATIONS | PROVENANCE_GAPS | EXPRESSION_RELATIONS | {"organism_has_gene"}

DEFAULT_EVIDENCE_FIELDS = [
    "source", "source_dataset", "source_release", "source_record_id",
    "original_endpoint_ids", "mapping_method", "mapping_confidence", "license",
]


def _spec(
    preferred_sources: list[str],
    availability_statuses: list[str],
    *,
    release_version: str,
    license_access: str,
    raw_objects: list[dict[str, Any]] | None = None,
    historical_identity: str = "No accepted immutable historical producer/artifact identity recovered.",
    builder_status: str = "source-specific builder required",
    assertion_policy: str,
    mapping_rejection_policy: str,
    evidence_fields: list[str] | None = None,
    execution_placement: str = "bounded fixture/source audit on Mac; full or bulk build on txgnn-worker; task-scoped staging only",
    next_rebuild_card: str = "create a relation-specific producer card after this contract is reviewed and merged",
    missing_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "preferred_sources": preferred_sources,
        "availability_statuses": availability_statuses,
        "release_version": release_version,
        "license_access": license_access,
        "raw_objects": raw_objects or [],
        "historical_identity": historical_identity,
        "builder_status": builder_status,
        "assertion_policy": assertion_policy,
        "mapping_rejection_policy": mapping_rejection_policy,
        "evidence_fields": evidence_fields or DEFAULT_EVIDENCE_FIELDS,
        "execution_placement": execution_placement,
        "next_rebuild_card": next_rebuild_card,
        "missing_artifacts": missing_artifacts or [],
    }


SPECS: dict[str, dict[str, Any]] = {}

# The five retained canonical edge lineages are recoverable from the immutable
# TxGNN kg.csv release. Constituent releases are not encoded in that flattened
# file, so the release contract is exact at the accepted TxGNN source boundary.
TXGNN_KG_OBJECT = {
    "doi": "10.7910/DVN/CNQV69",
    "dataverse_file_id": "7144484",
    "filename": "kg.csv",
    "version": "6.0",
    "published": "2023-06-07T04:55:16Z",
    "size": 981751236,
    "md5": "aac8191d4fbc5bf09cdf8c3c78b4e75f",
    "license": "CC0-1.0",
    "url": "https://dataverse.harvard.edu/api/access/datafile/7144484",
}
for relation, source_hint, predicates, policy in [
    ("molecule_associated_phenotype", "SIDER side-effect assertions flattened by PrimeKG/TxGNN", ["side effect"], "source-native broad molecule-to-phenotype side-effect association; non-causal"),
    ("molecule_contraindicates_disease", "DrugCentral contraindication assertions flattened by PrimeKG/TxGNN", ["contraindication"], "negative/contraindication assertion only; never reuse positive indication evidence"),
    ("molecule_parent_of_molecule", "Comparative Toxicogenomics Database exposure hierarchy flattened by PrimeKG/TxGNN", ["parent of"], "directed parent-to-child CTD chemical/exposure hierarchy; preserve source orientation"),
    ("molecule_synergizes_molecule", "DrugBank drug-interaction assertions labeled `synergizes with` by PrimeKG/TxGNN", ["synergizes with"], "preserve the source pair orientation and label as legacy DrugBank interaction provenance; no combination-screen score, assay context, or threshold exists"),
    ("molecule_treats_disease", "DrugCentral indication/off-label assertions plus CTD exposure-disease links flattened by PrimeKG/TxGNN", ["indication", "off-label use", "linked to"], "positive treatment/association assertion; original TxGNN edge lineage remains separate from later OpenTargets/ClinicalTrials support"),
]:
    SPECS[relation] = _spec(
        [source_hint], ["remote-refetch-required"],
        release_version="TxGNN/DeepPurpose Dataverse v6.0, published 2023-06-07",
        license_access="The accepted flattened kg.csv is CC0-1.0; upstream constituent release labels are not encoded and must not be invented.",
        raw_objects=[TXGNN_KG_OBJECT],
        historical_identity="Canonical generation is frozen in relation-evidence-ledger.json; source replay is bound to TxGNN kg.csv file 7144484 and the current canonical generation.",
        builder_status="immutable task-scoped builder present; full parity remains review-required",
        assertion_policy=policy,
        mapping_rejection_policy="Normalize typed DrugBank, CTD, HPO and MONDO endpoints exactly; quarantine unsupported predicates, malformed IDs and ambiguous/unmapped endpoints; preserve direction and source multiplicity; compare candidate-only/canonical-only/intersection against the frozen canonical generation.",
        evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["source_predicate", "original_x_id", "original_y_id", "pair_orientation", "symmetric"],
        next_rebuild_card="t_86299745 — full worker replay, parity report and independent review",
        missing_artifacts=["verified full worker replay and parity/exception report", "independent review"],
    )
    SPECS[relation]["source_predicates"] = predicates

SPECS["tf_binds_enhancer"] = _spec(
    ["ReMap observed all-peak ChIP binding", "ReMap CRM reconstructed support", "JASPAR/HOCOMOCO motif support only"],
    ["historical-builder-recoverable", "remote-refetch-required"],
    release_version="Historical bounded pilot t_a405fe3b; exact source release/input identities must be refrozen for reprise.",
    license_access="ReMap/JASPAR/HOCOMOCO terms must be recorded per fetched release.",
    historical_identity="t_a405fe3b (reviewer t_95856c15): 1,224,536 staged edges / 6,356,561 evidence; t_656a1102 and t_f2a2952e are CRM sidecar lanes, not final topology.",
    builder_status="historical staged builder is recoverable from Git/card artifacts; refactor to current flat paths",
    assertion_policy="active edges require observed ChIP-like binding to an accepted enhancer; CRM is reconstructed support; motif-only rows never create active edges",
    mapping_rejection_policy="Harmonize genome build; map TF and enhancer endpoints explicitly; retain peak-to-enhancer overlap rule, biosample and source peak; reject motif-only and incompatible coordinates.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["evidence_type", "assay", "biosample", "genome_build", "peak_coordinates", "overlap_rule", "score", "q_value"],
)
SPECS["transcript_interacts_protein"] = _spec(
    ["POSTAR3/POSTAR lineage", "ENCORI/starBase RBP modules", "NPInter v5 and RNAInter v4 direct experimental subsets"],
    ["remote-refetch-required", "historical-builder-recoverable"],
    release_version="NPInter v5 and RNAInter v4 audited in t_e76149bc; POSTAR/ENCORI exact release still requires pinning.",
    license_access="NPInter redistribution unclear; RNAInter academic/commercial terms differ; verify POSTAR/ENCORI terms before build.",
    historical_identity="t_e76149bc audited official NPInter/RNAInter exports and found zero policy-valid ENST+protein endpoint rows; no edge artifact was created.",
    builder_status="audit code/history recoverable; active builder blocked on transcript/protein endpoint mapping",
    assertion_policy="physical source-native RNA/transcript-protein binding only; predictions/motifs/context remain sidecars",
    mapping_rejection_policy="Require current ENST or reviewed transcript mapping and source-native UniProt/ENSP or unambiguous protein mapping; reject gene-symbol projection, ncRNA catalog IDs without node mapping, and coordinate-only rows without reviewed mapping.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["rna_class", "assay", "clip_method", "coordinates", "biosample", "experimental_status", "pmid"],
)
SPECS["transcript_interacts_gene"] = _spec(
    ["LncRNA2Target", "LncTarD", "narrow NPInter/RNAInter direct mechanism rows"],
    ["source-selection-required", "remote-refetch-required"],
    release_version="No accepted endpoint-valid release selected; t_e76149bc found zero active generic candidates in audited NPInter/RNAInter exports.",
    license_access="Source-specific access/redistribution review required; LncRNA2Target access previously timed out.",
    assertion_policy="source-native transcript/RNA-to-gene mechanism with perturbation, direction or effect; never mature-miRNA targets, ceRNA, correlation or projected RBP binding",
    mapping_rejection_policy="Require ENST/approved transcript mapping and canonical gene mapping; quarantine subtype-specific RNA IDs and all ambiguous/unmapped endpoints.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["rna_class", "mechanism", "perturbation", "direction", "effect", "assay", "context", "pmid"],
)
SPECS["tf_regulates_gene"] = _spec(
    ["derived only: reviewed tf_binds_enhancer plus compatible-context enhancer_regulates_gene"],
    ["source-selection-required"], release_version="No observed/source-native table is approved.",
    license_access="Inherited source licenses must remain attached to every derivation operand.",
    assertion_policy="not an observed direct relation; only a context-qualified inferred product of reviewed operands with full derivation evidence; keep observed tables separate",
    mapping_rejection_policy="Require exact enhancer identity and compatible biosample/context; reject missing, conflicting or pooled-incomparable contexts and all nearest-gene shortcuts.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["derivation_rule_version", "binding_evidence_id", "enhancer_gene_evidence_id", "full_path", "context_compatibility"],
    execution_placement="bounded derivation tests locally; full derivation on txgnn-worker into edges_inferred/evidence_inferred only",
)
SPECS["pathway_contains_protein"] = _spec(
    ["Reactome UniProt2Reactome_All_Levels"], ["current-raw-available", "historical-builder-recoverable"],
    release_version="2026-03-23 (historical Last-Modified)", license_access="Reactome license requires re-review before promotion.",
    raw_objects=[{"uri":"gs://jouvencekb/raw/reactome_UniProt2Reactome_All_Levels_20260323.txt","generation":"1785155500806613","crc32c_base64":"y0X/Og==","size":116822208}],
    historical_identity="t_15e780b9: 15,436 edges / 18,068 evidence; current builder manage_db/build_reactome_pathway_protein_membership.py at 12b9cde2af02fd1aae774a6a8b0f3059814e26e9.",
    builder_status="current builder and fixture tests present; update acquisition to require pinned checksum rather than mutable current URL",
    assertion_policy="Reactome all-level pathway membership from source-native UniProt endpoints; pathway-to-protein",
    mapping_rejection_policy="Human R-HSA only; exact pathway node; exact unambiguous UniProt-to-protein; reject missing pathway, unmapped and ambiguous UniProt; no gene projection.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["membership_type", "reactome_evidence_code", "source_pathway_id", "source_protein_id", "species"],
)
SPECS["molecule_targets_protein"] = _spec(
    ["ChEMBL mechanism API plus target protein components"], ["remote-refetch-required", "historical-builder-recoverable"],
    release_version="Historical label ChEMBL API 2026-06-23; immutable API payload checksums must be recreated.",
    license_access="ChEMBL terms/license must be recorded with the pinned payload.",
    historical_identity="t_15e780b9: 2,119 edges / 2,132 evidence; manage_db/build_chembl_molecule_targets_protein.py at ad0c2e3de8522025fc0f2d6a3f76caa0658d0e39.",
    builder_status="current builder present; add release/checksum manifest before replay claim",
    assertion_policy="source-native ChEMBL molecule mechanism to target protein component; no molecule-to-gene projection",
    mapping_rejection_policy="Canonical ChEMBL molecule ID plus human protein target component; exact unambiguous UniProt-to-protein; reject missing molecules/targets, nonhuman, nonprotein, unmapped and ambiguous rows.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["mec_id", "action_type", "mechanism", "target_chembl_id", "target_uniprot_id", "direct_interaction", "pmid"],
)
SPECS["cell_line_responds_to_molecule"] = _spec(
    ["PRISM Repurposing 20Q2 Secondary Figshare article 20564034", "GDSC/Sanger dose-response as an independent assay lane"],
    ["historical-builder-recoverable", "historical-artifact-deleted", "remote-refetch-required"],
    release_version="PRISM DOI 10.6084/m9.figshare.20564034.v1; five exact file identities pinned below.",
    license_access="PRISM CC BY 4.0; verify GDSC terms independently if that lane is rebuilt.",
    raw_objects=[
        {"figshare_file_id":"36794595","description":"dose-response curve parameters","md5":"eb0c7ee3ccb9e480148c71fcdc97312e"},
        {"figshare_file_id":"36794610","description":"pooling metadata","md5":"8a484f5f4b704abd06cd3201e1d7692b"},
        {"figshare_file_id":"36794613","description":"README","md5":"47419770d1edfcc36e0b11465f7d1fd0"},
        {"figshare_file_id":"36794616","description":"replicate-collapsed logfold change","md5":"d89c92f6d66366729c54389a4f3876b4"},
        {"figshare_file_id":"36794619","description":"replicate-collapsed treatment info","md5":"162da467eb97a67abdbdbee7af101091"},
    ],
    historical_identity="PR #15 builder manage_db/build_staged_prism_20q2.py at 3d65b66e15df03abb8c08e08de6e127134d31bcc (blob SHA-256 dd7aea221d7befd18f21292e9d4371a3451e692a7cdac5ec7fc6ccd007bccc05); 31,349 edges / 31,952 qualifying curves. GDSC t_103021f3: 11,040 / 11,713.",
    builder_status="PRISM historical builder recoverable from Git but intentionally not restored as active code in this contract card",
    assertion_policy="independent direct pharmacological viability screen; preferred screen, passed STR, AUC <= 0.70 and R2 >= 0.80; do not couple to CRISPR dependency",
    mapping_rejection_policy="Cell lines exact ACH identity; compounds exact unique RDKit InChIKey, names prohibited. Historical PRISM: 1,054/1,552 Broad IDs mapped; quarantine 447 unmatched structures, 39 conflicting structures, 12 missing structures.",
    evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["assay", "screen_id", "pooling_context", "auc", "r2", "ec50", "ic50", "threshold_rule", "source_curve_id"],
    missing_artifacts=["all five downloaded PRISM files", "fresh checksum manifest", "current flat-layout node snapshots/crosswalk", "mapping quarantine", "edge/evidence/features candidates", "validation and deterministic readback receipts"],
)
SPECS["cell_line_responds_to_molecule"]["missing_artifacts"].append(
    "historical GCS staging is not restorable: bounded soft-deleted probes matched no objects; refetch exact Figshare files instead"
)

# Historical ontology/cell-line candidates. The CL assertion payload itself is no
# longer in current raw storage; the retained UBERON object is only a tissue
# endpoint vocabulary and must not be mistaken for the missing CL source.
SPECS["cell_type_found_in_tissue"] = _spec(
    ["Cell Ontology CL relationship axioms plus UBERON endpoint vocabulary"],
    ["remote-refetch-required", "historical-builder-recoverable"],
    release_version="Historical CL source observed locally as releases/2026-06-08; exact refetched payload must be verified before replay.",
    license_access="Verify CL and UBERON ontology attribution/license metadata for the exact payloads before promotion.",
    raw_objects=[{"uri":"gs://jouvencekb/raw/uberon_basic.obo","generation":"1785155500137868","crc32c_base64":"iKspOA==","size":12078648,"role":"endpoint vocabulary only; not the CL assertion source"}],
    historical_identity="t_badd3e1e: 958 edges / 958 evidence from explicit CL part_of/located_in axioms; historical source note records CL releases/2026-06-08.",
    builder_status="manage_db/build_cell_type_context_relations.py is present; replay is blocked on exact CL refetch/checksum and current flat-path manifest updates",
    assertion_policy="explicit CL part_of/located_in tissue assertion; UBERON supplies typed tissue endpoints but cannot create the assertion",
    mapping_rejection_policy="Map CL and UBERON endpoints exactly; preserve predicate; reject missing, obsolete, ambiguous and wrong-type endpoints.",
    missing_artifacts=["CL OBO releases/2026-06-08 payload (or explicitly reviewed replacement release)", "immutable CL checksum/size/source manifest", "fresh mapping quarantine and replay/parity report"],
)
SPECS["cell_type_subtype_of_cell_type"] = _spec(
    ["Cell Ontology CL is_a hierarchy"],
    ["remote-refetch-required", "historical-builder-recoverable"],
    release_version="Historical CL source observed locally as releases/2026-06-08; exact refetched payload must be verified before replay.",
    license_access="Verify CL ontology attribution/license metadata for the exact payload before promotion.",
    historical_identity="t_badd3e1e: 4,526 edges / 4,526 evidence from CL is_a; historical source note records CL releases/2026-06-08.",
    builder_status="manage_db/build_cell_type_context_relations.py is present; replay is blocked on exact CL refetch/checksum and current flat-path manifest updates",
    assertion_policy="explicit CL is_a hierarchy",
    mapping_rejection_policy="Map CL endpoints exactly; preserve is_a; reject missing, obsolete, ambiguous and wrong-type endpoints.",
    missing_artifacts=["CL OBO releases/2026-06-08 payload (or explicitly reviewed replacement release)", "immutable CL checksum/size/source manifest", "fresh mapping quarantine and replay/parity report"],
)
for relation, source, identity, raw, policy in [
    ("cell_line_models_disease", "Cellosaurus disease annotations", "historical validated candidate: 983 edges / 1,218 evidence", [{"uri":"gs://jouvencekb/raw/cellosaurus_20260623.txt","generation":"1785155500485969","crc32c_base64":"STFRNQ==","size":119996997}], "source-native Cellosaurus cell-line disease annotation"),
    ("cell_line_derived_from_cell_type", "Cellosaurus cell-type annotations", "historical validated candidate: 65 / 65", [{"uri":"gs://jouvencekb/raw/cellosaurus_20260623.obo","generation":"1785155500649684","crc32c_base64":"coX5Eg==","size":116572609}], "source-native Cellosaurus cell-type derivation annotation"),
]:
    SPECS[relation] = _spec([source], ["current-raw-available", "historical-builder-recoverable"], release_version="2026-06-23 historical source snapshot", license_access="Verify ontology/source redistribution terms before promotion.", raw_objects=raw, historical_identity=identity, builder_status="historical/current builder lineage recoverable; update paths and manifest checks", assertion_policy=policy, mapping_rejection_policy="Map source-native typed endpoints exactly; preserve predicate; reject missing, obsolete, ambiguous and wrong-type endpoints.")

# Relations requiring a direct-source choice, not composition from neighboring edges.
for relation, sources, policy in [
    ("enhancer_regulates_transcript", ["transcript/TSS-native enhancer activity source; none accepted yet"], "direct enhancer-to-transcript assertion only; no gene-to-all-transcripts expansion"),
    ("cell_type_involved_in_disease", ["reviewed disease single-cell atlas/enrichment source"], "explicit disease-cell enrichment/annotation with cohort statistics; never infer from tissue or expression"),
    ("cell_type_expresses_protein", ["direct cell-type-resolved proteomics or validated protein-product measurement"], "retain direct protein measurement modality/context; no RNA-to-protein relabeling"),
    ("cell_type_responds_to_molecule", ["cell-type-resolved perturbational response atlas such as reviewed scPerturb/Sci-Plex lane"], "direct cell-type/drug response with assay, dose, time and direction; no cell-line proxy"),
    ("phenotype_observed_in_tissue", ["direct tissue-to-phenotype observation source"], "direct observation only; HPOA disease-to-phenotype plus anatomy is forbidden"),
    ("disease_comorbid_disease", ["public/licensable cohort, claims or curated comorbidity source"], "source-observed disease co-occurrence/statistic; never synthesize from shared genes, phenotypes or treatments"),
    ("gene_coexpressed_gene", ["GTEx tissue-specific correlation or other reviewed public context-specific coexpression source"], "symmetric correlative feature/context with sparse threshold/top-k and leakage policy; not causal regulation"),
]:
    SPECS[relation] = _spec(sources, ["source-selection-required", "remote-refetch-required"], release_version="No release-pinned accepted source selected.", license_access="Source-specific license/access review required.", assertion_policy=policy, mapping_rejection_policy="Require exact typed endpoint mapping and preserve all context/statistics; quarantine ambiguous/unmapped rows; never derive from adjacent KG paths.", evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["context", "assay_or_method", "score", "effect_size", "p_value", "q_value", "sample_count", "threshold_policy"])

SPECS["cell_line_expresses_protein"] = _spec(
    ["DepMap/Harmonized MS CCLE Gygi"], ["historical-builder-recoverable", "remote-refetch-required"],
    release_version="Historical t_103021f3 candidate release; exact DepMap file identity/checksum must be recreated.", license_access="DepMap access/redistribution terms apply.", historical_identity="t_103021f3: 3,083 edges / 3,090 direct-MS evidence; seven edges have two evidence rows.", builder_status="manage_db/build_staged_cell_line_assays.py recoverable/current; pin source payload", assertion_policy="direct mass-spectrometry protein abundance only; no RNA projection; future threshold must retain numeric abundance", mapping_rejection_policy="Exact ACH mapping and source protein-to-current protein mapping; reject non-MS, missing and ambiguous endpoints.", evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["assay", "protein_abundance", "threshold_rule", "source_protein_column"])

# Existing expression topology is retained and enriched, not threshold-deleted.
for relation in sorted(EXPRESSION_RELATIONS):
    SPECS[relation] = _spec(
        ["the release-pinned native expression source that produced the retained canonical table"],
        ["source-selection-required"], release_version="Table exists canonically; exact accepted source/release and numeric payload must be recovered before enrichment.", license_access="Inherit and record the native expression source license.",
        historical_identity="Current flat edge generation is frozen in relation-evidence-ledger.json; numeric expression is not present in edge-only topology.",
        builder_status="feature/evidence enrichment builder required; canonical edge deletion is out of scope",
        assertion_policy="retain every existing edge whose native expression is non-zero; preserve numeric expression and add deterministic low|medium|high bins",
        mapping_rejection_policy="Quantiles must be computed within an explicitly recorded source/context/modality group; record exact grouping and q cutoffs; never pool incomparable modalities; quarantine rows lacking a comparable group or typed endpoint.",
        evidence_fields=DEFAULT_EVIDENCE_FIELDS + ["numeric_expression", "unit", "modality", "context_group", "quantile_grouping_columns", "q_low_cutoff", "q_high_cutoff", "expression_bin"],
    )

SPECS["organism_has_gene"] = _spec(
    ["current human organism slice plus release-pinned canonical gene registry membership"], ["accepted-no-row-evidence"],
    release_version="Table-level provenance must bind organism taxonomy identity and the accepted canonical gene registry snapshot.", license_access="Record the taxonomy/gene-registry source licenses at table level.",
    historical_identity="Canonical flat object: 109,325 rows; generation 1785155488582377 (see relation-evidence-ledger.json).",
    builder_status="manage_db/export_human_organism_slice.py constructs the structural reference edge",
    assertion_policy="accepted structural/reference membership exception; no row-level evidence table is required or desired",
    mapping_rejection_policy="Bind the organism ID and exact accepted gene registry/release; exclude nonhuman/orthology stubs according to the reviewed human-gene policy; report table-level counts and anti-joins.",
    evidence_fields=["table_source", "taxonomy_release", "gene_registry_release", "builder_commit", "edge_generation", "row_count", "endpoint_antijoin_count"],
    execution_placement="bounded fixture locally; any full registry rebuild on txgnn-worker; no fabricated evidence parquet",
    next_rebuild_card="no evidence-backfill card; table-level source/release documentation only",
)

# Provenance/catalog metadata relations remain graph-disconnected.
for relation in ["paper_produced_dataset", "paper_cites_paper", "dataset_contains_disease", "dataset_contains_molecule", "dataset_contains_cell_type"]:
    SPECS[relation] = _spec(
        ["release-pinned provenance/catalog registry selected by a future metadata card"], ["source-selection-required"],
        release_version="No accepted source release selected.", license_access="Source-specific metadata license required.",
        assertion_policy="metadata/provenance only; keep disconnected from default biomedical training adjacency",
        mapping_rejection_policy="Require stable catalog identifiers and exact typed members; reject unresolved aliases and never infer membership from graph proximity.",
        execution_placement="bounded metadata build locally or on worker by size; graph-disconnected output only",
    )


def build_contract() -> dict[str, Any]:
    schema = {relation.name: relation for relation in RELATIONS}
    if set(SPECS) != CONTRACT_RELATIONS:
        raise ValueError(f"contract spec drift: missing={sorted(CONTRACT_RELATIONS-set(SPECS))}, extra={sorted(set(SPECS)-CONTRACT_RELATIONS)}")
    if not NONCANONICAL_RELATIONS <= set(schema):
        raise ValueError("noncanonical relation set no longer matches active schema")
    rows = []
    for name in sorted(CONTRACT_RELATIONS):
        relation = schema[name]
        spec = SPECS[name]
        statuses = spec["availability_statuses"]
        if not statuses or not set(statuses) <= AVAILABILITY_STATUSES:
            raise ValueError(f"invalid availability status for {name}: {statuses}")
        rows.append({
            "relation": name,
            "x_type": relation.source.value,
            "y_type": relation.target.value,
            "direct": relation.direct,
            "kind": relation.kind.value,
            **spec,
        })
    return {
        "schema_version": "relation-expansion-source-contract-v1",
        "generated_from": ["manage_db/kg_schema.py", "docs/relation-evidence-ledger.json", "docs/storage-migration-20260727/object-map.json", "Git history and relation-specific reports named in each row"],
        "canonical_root": "gs://jouvencekb/main",
        "raw_root": "gs://jouvencekb/raw",
        "contract_statuses": sorted(AVAILABILITY_STATUSES),
        "policies": {
            "no_canonical_writes": True,
            "provenance_gap_exit_gate": ["release-pinned native source and checksum", "exact mapping/quarantine", "immutable builder", "verified replay command", "canonical-generation parity/exception report", "independent review"],
            "expression": "retain non-zero topology; preserve numeric values; deterministic source/context-specific low|medium|high quantiles with exact group and cutoffs",
            "tf_regulates_gene": "inferred/context-specific only from reviewed tf_binds_enhancer plus compatible-context enhancer_regulates_gene; observed tables remain separate",
            "organism_has_gene": "accepted no-row-evidence structural/reference exception; table-level source/release provenance only",
            "gcs_recovery": "Bucket soft delete is 31 days (2678400s) effective only from 2026-08-12T09:27:50.492Z; object versioning and lifecycle are absent. Bounded soft-deleted probes under kg/staging/** and staging/** matched no objects. This is not retroactive recovery: PRISM #15 must be refetched from exact Figshare identities and replayed with the historical builder.",
        },
        "summary": {"relations": len(rows), "noncanonical_relations": len(NONCANONICAL_RELATIONS), "provenance_gaps": len(PROVENANCE_GAPS), "retained_expression_relations": len(EXPRESSION_RELATIONS), "accepted_no_row_evidence": 1},
        "relations": rows,
    }


def render_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# Relation expansion source and recovery contract", "",
        "Status: **review-required source freeze; no data or canonical write authorization**", "",
        "This contract freezes the independently executable inputs for the reopened relation expansion. Historical row counts are evidence of prior work, not current artifact identity. Old `.omoc`, `kg/v2`, and deleted staging paths are never replay targets.", "",
        "## Non-negotiable policies", "",
        "- The five molecule lineages remain `provenance-gap` until the full six-part exit gate in the JSON contract passes independent review.",
        "- `cell_line_responds_to_molecule` is mandatory. PRISM and GDSC are independent pharmacology assay lanes; neither is coupled to CRISPR dependency.",
        "- `organism_has_gene` is an accepted structural/reference exception: record table-level source/release provenance and do not fabricate row evidence.",
        "- Retain existing non-zero expression topology. Preserve numeric expression and compute `low|medium|high` only within recorded source/context/modality groups, with exact quantile cutoffs.",
        "- `tf_regulates_gene` is never an observed direct table. It may exist only as a context-compatible inferred derivation of reviewed `tf_binds_enhancer` and `enhancer_regulates_gene`, with complete operand evidence.",
        "- Heavy/full rebuilds run on `txgnn-worker`; this source-freeze card performs no bulk fetch, GCS write, canonical promotion, or deleted-staging restoration.", "",
        "## GCS recovery boundary", "",
        "Bucket soft delete is now 31 days (`2678400s`) but became effective only at `2026-08-12T09:27:50.492Z`; object versioning and lifecycle are absent. Bounded `--soft-deleted` probes of `gs://jouvencekb/kg/staging/**` and `gs://jouvencekb/staging/**` matched no objects. Soft delete is not retroactive: PRISM #15 historical staging is not GCS-restorable and must be rebuilt by exact Figshare refetch/checksum verification plus the historical builder.", "",
        "## Availability vocabulary", "",
    ]
    for status in contract["contract_statuses"]:
        lines.append(f"- `{status}`")
    lines += ["", "## Frozen relation rows", "", "| Relation | Endpoints | Availability | Preferred source/release | Historical builder/artifact | Next lane |", "| --- | --- | --- | --- | --- | --- |"]
    for row in contract["relations"]:
        statuses = ", ".join(f"`{x}`" for x in row["availability_statuses"])
        sources = "; ".join(row["preferred_sources"])
        hist = row["historical_identity"]
        lines.append(f"| `{row['relation']}` | `{row['x_type']}→{row['y_type']}` | {statuses} | {sources}; {row['release_version']} | {hist} | {row['next_rebuild_card']} |")
    lines += ["", "## Per-row execution contract", "", "The machine-readable partner is [`relation-expansion-source-contract.json`](relation-expansion-source-contract.json). Every row records licensing/access, current raw identities where known, exact assertion semantics, mapping/quarantine policy, evidence fields, execution placement, missing artifacts, builder status, and the next rebuild lane. The JSON is generated and checked by `scripts/build_relation_expansion_source_contract.py`; tests require exact coverage of all 24 active noncanonical relations plus the five provenance gaps, three retained expression relations, and `organism_has_gene`.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    contract = build_contract()
    json_text = json.dumps(contract, indent=2, sort_keys=True) + "\n"
    markdown_text = render_markdown(contract)
    if args.check:
        stale = []
        for path, expected in [(args.json_output, json_text), (args.markdown_output, markdown_text)]:
            if not path.exists() or path.read_text() != expected:
                stale.append(str(path))
        if stale:
            raise SystemExit("generated output is stale: " + ", ".join(stale))
        return
    args.json_output.write_text(json_text)
    args.markdown_output.write_text(markdown_text)


if __name__ == "__main__":
    main()
