"""Custom LaminDB registries for the TxGNN biomedical knowledge graph.

Install and mount in a LaminDB instance::

    lamin init --storage ./mydb --modules bionty,lnschema_txgnn

Import and create records::

    import lnschema_txgnn as txs
    paper = txs.Paper(pmid="12345678", title="TxGNN paper").save()

Registries:

.. autosummary::
   :toctree: .

   KGEdge
   KGEdgeEvidence
   Gene
   Molecule
   Pathway
   Tissue
   CellType
   Paper
   Transcript
   Protein
   Disease
   Enhancer
   Dataset
   Mutation

"""

__version__ = "0.1.0"

# Django registers model classes by (app_label, model_name), not by Python import
# path. This schema package is installed as top-level ``lnschema_txgnn`` for
# LaminDB, while the source tree also makes it reachable as
# ``manage_db.lnschema_txgnn``. Loading models through both names creates two
# distinct Python classes for the same Django app/model labels and crashes with
# a duplicate-model RuntimeError. Keep the top-level Lamin schema module as the
# only canonical namespace and alias any package-path import before importing
# ``.models``.
if __name__ != "lnschema_txgnn":
    import importlib
    import sys

    _canonical = importlib.import_module("lnschema_txgnn")
    sys.modules[__name__] = _canonical
    sys.modules[f"{__name__}.models"] = importlib.import_module("lnschema_txgnn.models")
else:
    from lamindb_setup import _check_instance_setup

    _check_instance_setup(from_module="lnschema_txgnn")

    from .models import (
        CellType,
        Dataset,
        Disease,
        Enhancer,
        Gene,
        KGEdge,
        KGEdgeEvidence,
        Molecule,
        Mutation,
        Paper,
        Pathway,
        Protein,
        Tissue,
        Transcript,
    )

    __all__ = [
        "CellType",
        "Dataset",
        "Disease",
        "Enhancer",
        "Gene",
        "KGEdge",
        "KGEdgeEvidence",
        "Molecule",
        "Mutation",
        "Paper",
        "Pathway",
        "Protein",
        "Tissue",
        "Transcript",
    ]
