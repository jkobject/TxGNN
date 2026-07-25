from __future__ import annotations

from pathlib import Path

import pandas as pd

from manage_db import kg_storage
from manage_db.sync_parquet_nodes_to_lamindb import (
    _iter_node_batches,
    _row_to_record_spec,
    main,
    sync_parquet_nodes_to_lamindb,
)


def test_row_to_record_spec_maps_supported_custom_records() -> None:
    mutation = _row_to_record_spec("mutation", {"id": "rs7412", "hgvs": "NC_000019.10:g.44908822C>T"})
    assert mutation is not None
    assert mutation.registry_name == "lnschema_txgnn.Mutation"
    assert mutation.key_field == "rsid"
    assert mutation.create_kwargs["rsid"] == "rs7412"

    paper = _row_to_record_spec("paper", {"id": "PMID:123", "doi": "10.1/example"})
    assert paper is not None
    assert paper.registry_name == "lnschema_txgnn.Paper"
    assert paper.key_value == "123"
    assert paper.create_kwargs["doi"] == "10.1/example"

    transcript = _row_to_record_spec("transcript", {"id": "ENST00000380152", "ensembl_gene_id": "ENSG1"})
    assert transcript is not None
    assert transcript.registry_name == "lnschema_txgnn.Transcript"
    assert transcript.create_kwargs["ensembl_gene_id"] == "ENSG1"

    protein = _row_to_record_spec(
        "protein",
        {
            "id": "ENSP00000369497",
            "ensembl_gene_id": "ENSG00000139618",
            "uniprot_id": "P51587",
            "refseq_protein": "NP_000050.2",
            "pdb_ids": "1N0W|1N0V",
        },
    )
    assert protein is not None
    assert protein.registry_name == "lnschema_txgnn.Protein"
    assert protein.key_field == "ensembl_protein_id"
    assert protein.key_value == "ENSP00000369497"
    assert protein.create_kwargs == {
        "ensembl_protein_id": "ENSP00000369497",
        "ensembl_gene_id": "ENSG00000139618",
        "uniprot_id": "P51587",
        "refseq_protein": "NP_000050.2",
        "pdb_ids": "1N0W|1N0V",
    }

    enhancer = _row_to_record_spec(
        "enhancer",
        {"id": "EH38E1516972", "chromosome": "chr1", "start": 10, "end": 20},
    )
    assert enhancer is not None
    assert enhancer.registry_name == "lnschema_txgnn.Enhancer"
    assert enhancer.key_field == "encode_id"
    assert enhancer.key_value == "EH38E1516972"
    assert enhancer.create_kwargs == {
        "encode_id": "EH38E1516972",
        "ensembl_regulatory_id": None,
        "encode_experiment_id": None,
        "chromosome": "chr1",
        "start_pos": 10,
        "end_pos": 20,
    }


def test_row_to_record_spec_maps_bionty_and_pertdb_records() -> None:
    disease = _row_to_record_spec("disease", {"id": "EFO_0000305", "name": "breast carcinoma"})
    assert disease is not None
    assert disease.registry_name == "lnschema_txgnn.Disease"
    assert disease.key_field == "ontology_id"
    assert disease.key_value == "EFO:0000305"
    assert disease.create_kwargs["source_ontology"] == "EFO"

    gene = _row_to_record_spec("gene", {"id": "ENSG00000139618", "gene_name": "BRCA2"})
    assert gene is not None
    assert gene.registry_name == "lnschema_txgnn.Gene"
    assert gene.key_field == "ensembl_gene_id"
    assert gene.create_kwargs["symbol"] == "BRCA2"


    molecule = _row_to_record_spec("molecule", {"id": "CHEMBL941", "smiles": "CCO"})
    assert molecule is not None
    assert molecule.registry_name == "lnschema_txgnn.Molecule"
    assert molecule.create_kwargs["chembl_id"] == "CHEMBL941"

    pathway = _row_to_record_spec("pathway", {"id": "GO:0008150", "name": "biological_process"})
    assert pathway is not None
    assert pathway.registry_name == "lnschema_txgnn.Pathway"
    assert pathway.key_field == "ontology_id"
    assert pathway.create_kwargs == {"ontology_id": "GO:0008150", "name": "biological_process"}

    tissue = _row_to_record_spec("tissue", {"id": "UBERON:0002107", "label": "liver"})
    assert tissue is not None
    assert tissue.registry_name == "lnschema_txgnn.Tissue"
    assert tissue.create_kwargs == {"ontology_id": "UBERON:0002107", "name": "liver"}

    cell_type = _row_to_record_spec("cell_type", {"id": "CL:0000576"})
    assert cell_type is not None
    assert cell_type.registry_name == "lnschema_txgnn.CellType"
    assert cell_type.create_kwargs == {"ontology_id": "CL:0000576", "name": "CL:0000576"}


def test_mutation_record_spec_uses_gnomad_like_node_id_as_parity_key() -> None:
    mutation = _row_to_record_spec(
        "mutation",
        {"id": "10_111076745_G_C", "name": "rs1800544", "gnomad_id": None},
    )
    assert mutation is not None
    assert mutation.key_field == "gnomad_id"
    assert mutation.key_value == "10_111076745_G_C"
    assert mutation.create_kwargs["gnomad_id"] == "10_111076745_G_C"
    assert mutation.create_kwargs["rsid"] == "rs1800544"


def test_connect_lamin_skips_hub_refresh_when_slug_already_current(monkeypatch) -> None:
    from manage_db import sync_parquet_nodes_to_lamindb as sync_mod

    calls = []

    class FakeLn:
        class setup:
            class settings:
                class instance:
                    slug = "jkobject/jouvencekb"

        @staticmethod
        def connect(instance):
            calls.append(instance)

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._configure_sqlite_timeout", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "lamindb", FakeLn)

    sync_mod._connect_lamin("jkobject/jouvencekb")

    assert calls == []


def test_dry_run_without_lamindb_counts_valid_rows_as_would_create(tmp_path: Path, monkeypatch) -> None:
    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(
        root,
        "paper",
        pd.DataFrame(
            [
                {"id": "PMID:1", "doi": "10.1/a", "pmc_id": None, "arxiv_id": None},
                {"id": "PMID:2", "doi": None, "pmc_id": None, "arxiv_id": None},
            ]
        ),
    )

    def _boom(_lamin_instance):
        raise RuntimeError("no lamindb")

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", _boom)

    summaries = sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["paper"], batch_size=1)

    assert len(summaries) == 1
    assert summaries[0].seen == 2
    assert summaries[0].would_create == 2
    assert summaries[0].created == 0


def test_node_batch_iterator_resumes_from_exact_row_offset(tmp_path: Path) -> None:
    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(
        root,
        "paper",
        pd.DataFrame(
            [
                {"id": "PMID:1", "doi": None, "pmc_id": None, "arxiv_id": None},
                {"id": "PMID:2", "doi": None, "pmc_id": None, "arxiv_id": None},
                {"id": "PMID:3", "doi": None, "pmc_id": None, "arxiv_id": None},
            ]
        ),
    )

    ids = [
        node_id
        for batch in _iter_node_batches(root, "paper", batch_size=1, row_offset=1)
        for node_id in batch["id"].tolist()
    ]

    assert ids == ["PMID:2", "PMID:3"]



def test_dry_run_reports_schema_module_not_configured(tmp_path: Path, monkeypatch) -> None:
    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(
        root,
        "gene",
        pd.DataFrame([{
            "id": "NCBI:1",
            "ncbi_gene_id": "1",
            "hgnc_id": None,
            "uniprot_id": None,
            "gene_name": "A1BG",
        }]),
    )

    def _boom():
        raise RuntimeError("'lnschema_txgnn' wasn't configured for this instance")

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", lambda _: None)
    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._registry_models", _boom)

    summaries = sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["gene"], batch_size=1)

    assert summaries[0].status == "schema_module_not_configured"
    assert summaries[0].would_create == 1
    assert summaries[0].status_detail is not None
    assert "wasn't configured" in summaries[0].status_detail


def test_dry_run_counts_protein_rows_as_would_create_without_lamindb(
    tmp_path: Path, monkeypatch
) -> None:
    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(
        root,
        "protein",
        pd.DataFrame(
            [
                {
                    "id": "ENSP00000369497",
                    "ensembl_gene_id": "ENSG00000139618",
                    "uniprot_id": "P51587",
                    "refseq_protein": "NP_000050.2",
                    "pdb_ids": "1N0W|1N0V",
                },
                {
                    "id": "ENSP00000439902",
                    "ensembl_gene_id": "ENSG00000157764",
                    "uniprot_id": None,
                    "refseq_protein": None,
                    "pdb_ids": None,
                },
            ]
        ),
    )

    def _boom(_lamin_instance):
        raise RuntimeError("no lamindb")

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", _boom)

    summaries = sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["protein"], batch_size=1)

    assert len(summaries) == 1
    assert summaries[0].node_type == "protein"
    assert summaries[0].registry == "lnschema_txgnn.Protein"
    assert summaries[0].key_field == "ensembl_protein_id"
    assert summaries[0].seen == 2
    assert summaries[0].would_create == 2
    assert summaries[0].created == 0

def test_cli_defaults_to_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(
        root,
        "mutation",
        pd.DataFrame([{"id": "rs1", "hgvs": None, "clinvar_id": None, "gnomad_id": None}]),
    )
    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", lambda _: (_ for _ in ()).throw(RuntimeError("no db")))

    assert main([str(tmp_path / "kg"), "--node-types", "mutation", "--batch-size", "1"]) == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "would_create=1" in out
    assert "created=0" in out


def test_dry_run_reports_schema_pending_for_missing_registry_table(tmp_path: Path, monkeypatch) -> None:
    from manage_db.sync_parquet_nodes_to_lamindb import OperationalError

    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(root, "protein", pd.DataFrame([{
        "id": "ENSP00000369497",
        "ensembl_gene_id": None,
        "uniprot_id": None,
        "refseq_protein": None,
        "pdb_ids": None,
    }]))

    class Field:
        name = "ensembl_protein_id"

    class Meta:
        db_table = "lnschema_txgnn_protein"
        fields = [Field()]

    class QuerySet:
        def values_list(self, field, flat=False):
            raise OperationalError("no such table: lnschema_txgnn_protein")

    class Objects:
        def filter(self, **kwargs):
            return QuerySet()

    class Protein:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", lambda _: None)
    monkeypatch.setattr(
        "manage_db.sync_parquet_nodes_to_lamindb._registry_models",
        lambda: {"lnschema_txgnn.Protein": Protein},
    )

    summaries = sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["protein"], batch_size=1)

    assert summaries[0].status == "schema_pending"
    assert summaries[0].would_create == 0
    assert summaries[0].skipped == 1
    assert "lnschema_txgnn_protein" in summaries[0].status_detail


def test_write_refuses_missing_registry_table(tmp_path: Path, monkeypatch) -> None:
    from manage_db.sync_parquet_nodes_to_lamindb import OperationalError
    import pytest

    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(root, "protein", pd.DataFrame([{
        "id": "ENSP00000369497",
        "ensembl_gene_id": None,
        "uniprot_id": None,
        "refseq_protein": None,
        "pdb_ids": None,
    }]))

    class Field:
        name = "ensembl_protein_id"

    class Meta:
        db_table = "lnschema_txgnn_protein"
        fields = [Field()]

    class QuerySet:
        def values_list(self, field, flat=False):
            raise OperationalError("no such table: lnschema_txgnn_protein")

    class Objects:
        def filter(self, **kwargs):
            return QuerySet()

    class Protein:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", lambda _: None)
    monkeypatch.setattr(
        "manage_db.sync_parquet_nodes_to_lamindb._registry_models",
        lambda: {"lnschema_txgnn.Protein": Protein},
    )

    with pytest.raises(RuntimeError, match="Refusing --write: missing registry table"):
        sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["protein"], batch_size=1, write=True)


def test_dry_run_does_not_hide_other_operational_errors(tmp_path: Path, monkeypatch) -> None:
    from manage_db.sync_parquet_nodes_to_lamindb import OperationalError
    import pytest

    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(root, "protein", pd.DataFrame([{
        "id": "ENSP00000369497",
        "ensembl_gene_id": None,
        "uniprot_id": None,
        "refseq_protein": None,
        "pdb_ids": None,
    }]))

    class Field:
        name = "ensembl_protein_id"

    class Meta:
        db_table = "lnschema_txgnn_protein"
        fields = [Field()]

    class QuerySet:
        def values_list(self, field, flat=False):
            raise OperationalError("no such column: broken_column")

    class Objects:
        def filter(self, **kwargs):
            return QuerySet()

    class Protein:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", lambda _: None)
    monkeypatch.setattr(
        "manage_db.sync_parquet_nodes_to_lamindb._registry_models",
        lambda: {"lnschema_txgnn.Protein": Protein},
    )

    with pytest.raises(OperationalError, match="broken_column"):
        sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["protein"], batch_size=1)


def test_write_uses_bulk_create_for_custom_protein_records() -> None:
    from manage_db.sync_parquet_nodes_to_lamindb import RecordSpec, SyncSummary, _process_specs

    class Field:
        def __init__(self, name):
            self.name = name

    class Meta:
        fields = [Field("ensembl_protein_id"), Field("uniprot_id")]

    class QuerySet:
        def values_list(self, field, flat=False):
            return []

    class Objects:
        created_batches = []

        def filter(self, **kwargs):
            return QuerySet()

        def bulk_create(self, records, batch_size=None):
            self.created_batches.append((records, batch_size))
            return records

    class Protein:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    specs = [
        RecordSpec(
            "protein",
            "ENSP1",
            "lnschema_txgnn.Protein",
            "ensembl_protein_id",
            "ENSP1",
            {"ensembl_protein_id": "ENSP1", "uniprot_id": "P1", "unknown": "drop"},
        ),
        RecordSpec(
            "protein",
            "ENSP2",
            "lnschema_txgnn.Protein",
            "ensembl_protein_id",
            "ENSP2",
            {"ensembl_protein_id": "ENSP2", "uniprot_id": None},
        ),
    ]
    summary = SyncSummary("protein", "lnschema_txgnn.Protein", "ensembl_protein_id")

    _process_specs(
        specs,
        registry_models={"lnschema_txgnn.Protein": Protein},
        write=True,
        summary=summary,
        bulk_create_batch_size=17,
    )

    assert summary.created == 2
    records, batch_size = Protein.objects.created_batches[0]
    assert batch_size == 17
    assert [record.kwargs for record in records] == [
        {"ensembl_protein_id": "ENSP1", "uniprot_id": "P1"},
        {"ensembl_protein_id": "ENSP2"},
    ]



def test_write_reconciles_mutation_gnomad_id_onto_existing_rsid() -> None:
    from manage_db.sync_parquet_nodes_to_lamindb import RecordSpec, SyncSummary, _process_specs

    class Field:
        def __init__(self, name):
            self.name = name

    class Meta:
        fields = [Field("rsid"), Field("gnomad_id")]

    class Record:
        def __init__(self, rsid, gnomad_id=None):
            self.rsid = rsid
            self.gnomad_id = gnomad_id
            self.saved = []

        def save(self, update_fields=None):
            self.saved.append(update_fields)

    existing_record = Record("rs1")

    class QuerySet:
        def __init__(self, mode):
            self.mode = mode

        def values_list(self, field, flat=False):
            if self.mode == "gnomad":
                return []
            return [existing_record.rsid]

        def __iter__(self):
            return iter([existing_record] if self.mode == "rsid" else [])

    class Objects:
        created_batches = []

        def filter(self, **kwargs):
            if "gnomad_id__in" in kwargs:
                return QuerySet("gnomad")
            if "rsid__in" in kwargs:
                return QuerySet("rsid")
            return QuerySet("other")

        def bulk_create(self, records, batch_size=None):
            self.created_batches.append((records, batch_size))
            return records

    class Mutation:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    summary = SyncSummary("mutation", "lnschema_txgnn.Mutation", "gnomad_id")
    specs = [
        RecordSpec(
            "mutation",
            "1_2_A_T",
            "lnschema_txgnn.Mutation",
            "gnomad_id",
            "1_2_A_T",
            {"gnomad_id": "1_2_A_T", "rsid": "rs1"},
        )
    ]

    _process_specs(
        specs,
        registry_models={"lnschema_txgnn.Mutation": Mutation},
        write=True,
        summary=summary,
    )

    assert summary.existing == 1
    assert summary.created == 0
    assert existing_record.gnomad_id == "1_2_A_T"
    assert existing_record.saved == [["gnomad_id"]]
    assert Mutation.objects.created_batches == []

def test_write_uses_bulk_create_for_custom_paper_records() -> None:
    from manage_db.sync_parquet_nodes_to_lamindb import RecordSpec, SyncSummary, _process_specs

    class Field:
        def __init__(self, name):
            self.name = name

    class Meta:
        fields = [
            Field("pmid"),
            Field("doi"),
            Field("pmc_id"),
            Field("arxiv_id"),
            Field("title"),
            Field("year"),
            Field("journal"),
            Field("abstract"),
        ]

    class QuerySet:
        def values_list(self, field, flat=False):
            return ["2"]

    class Objects:
        created_batches = []

        def filter(self, **kwargs):
            return QuerySet()

        def bulk_create(self, records, batch_size=None):
            self.created_batches.append((records, batch_size))
            return records

    class Paper:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    specs = [
        RecordSpec(
            "paper",
            "PMID:1",
            "lnschema_txgnn.Paper",
            "pmid",
            "1",
            {"pmid": "1", "doi": "10.1/example", "pmc_id": None},
        ),
        RecordSpec(
            "paper",
            "PMID:2",
            "lnschema_txgnn.Paper",
            "pmid",
            "2",
            {"pmid": "2", "doi": "10.2/existing"},
        ),
    ]
    summary = SyncSummary("paper", "lnschema_txgnn.Paper", "pmid")

    _process_specs(
        specs,
        registry_models={"lnschema_txgnn.Paper": Paper},
        write=True,
        summary=summary,
        bulk_create_batch_size=31,
    )

    assert summary.existing == 1
    assert summary.created == 1
    records, batch_size = Paper.objects.created_batches[0]
    assert batch_size == 31
    assert [record.kwargs for record in records] == [{"pmid": "1", "doi": "10.1/example"}]


def test_disease_record_spec_normalizes_opentargets_ids() -> None:
    disease = _row_to_record_spec(
        "disease",
        {"id": "EFO_0000094", "name": "EFO_0000094", "mondo_id": "MONDO_0000001", "hp_id": "HP_0000001"},
    )
    assert disease is not None
    assert disease.node_id == "EFO:0000094"
    assert disease.key_value == "EFO:0000094"
    assert disease.create_kwargs["ontology_id"] == "EFO:0000094"
    assert disease.create_kwargs["name"] == "EFO:0000094"
    assert disease.create_kwargs["mondo_id"] == "MONDO:0000001"
    assert disease.create_kwargs["hp_id"] == "HP:0000001"


def test_disease_sync_uses_custom_registry_for_non_mondo_ids(tmp_path: Path, monkeypatch) -> None:
    root = kg_storage.open_kg_root(str(tmp_path / "kg"))
    kg_storage.write_nodes(
        root,
        "disease",
        pd.DataFrame([
            {"id": "EFO_0000094", "name": "EFO_0000094", "mondo_id": None, "omim_id": None, "doid_id": None, "icd10_code": None, "mesh_id": None, "hp_id": None},
            {"id": "MONDO_0005148", "name": "type 2 diabetes mellitus", "mondo_id": "MONDO_0005148", "omim_id": None, "doid_id": None, "icd10_code": None, "mesh_id": None, "hp_id": None},
        ]),
    )

    class Field:
        def __init__(self, name):
            self.name = name

    class Meta:
        fields = [Field("ontology_id"), Field("name"), Field("source_ontology"), Field("mondo_id"), Field("hp_id")]

    class QuerySet:
        def values_list(self, field, flat=False):
            return ["MONDO:0005148"]

    class Objects:
        def filter(self, **kwargs):
            return QuerySet()

    class Disease:
        __module__ = "lnschema_txgnn.models"
        _meta = Meta()
        objects = Objects()

    monkeypatch.setattr("manage_db.sync_parquet_nodes_to_lamindb._connect_lamin", lambda _: None)
    monkeypatch.setattr(
        "manage_db.sync_parquet_nodes_to_lamindb._registry_models",
        lambda: {"lnschema_txgnn.Disease": Disease},
    )

    summaries = sync_parquet_nodes_to_lamindb(tmp_path / "kg", node_types=["disease"], batch_size=2)

    assert summaries[0].registry == "lnschema_txgnn.Disease"
    assert summaries[0].existing == 1
    assert summaries[0].would_create == 1
    assert summaries[0].skipped == 0
    assert summaries[0].status == "ok"
