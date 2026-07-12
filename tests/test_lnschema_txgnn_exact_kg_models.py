"""Read-only live regression for activated TxGNN KG edge registries.

Set ``TXGNN_LIVE_LAMIN_READ_ONLY_PROBE=1`` only on txgnn-worker. The test
connects to the exact Lamin instance and inspects its Django registry/table
metadata; it does not instantiate, save, sync, or count model records.
"""

from __future__ import annotations

import os

import pytest


_INSTANCE = "jkobject/jouvencekb"
_REQUIRED_PROJECT = "jkobject-1549353370965"
_REQUIRED_MODELS = {
    "KGEdge": "lnschema_txgnn_kgedge",
    "KGEdgeEvidence": "lnschema_txgnn_kgedgeevidence",
}


def test_requester_pays_exact_instance_resolves_kg_models_read_only() -> None:
    if os.environ.get("TXGNN_LIVE_LAMIN_READ_ONLY_PROBE") != "1":
        pytest.skip("set TXGNN_LIVE_LAMIN_READ_ONLY_PROBE=1 on txgnn-worker")

    assert os.environ.get("FSSPEC_GS_REQUESTER_PAYS") == _REQUIRED_PROJECT
    assert os.environ.get("FSSPEC_GS_PROJECT") == _REQUIRED_PROJECT

    import lamindb as ln
    from django.apps import apps
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder
    from lamindb_setup import settings

    ln.connect(_INSTANCE)
    assert settings.instance.slug == _INSTANCE
    assert settings.instance.owner == "jkobject"
    assert ("lnschema_txgnn", "0007_generic_kg_edge_evidence") in MigrationRecorder(
        connection
    ).applied_migrations()

    import lnschema_txgnn as txs

    table_names = set(connection.introspection.table_names())
    for name, table_name in _REQUIRED_MODELS.items():
        exported = getattr(txs, name)
        registered = apps.get_model("lnschema_txgnn", name)
        assert registered is exported
        assert exported._meta.app_label == "lnschema_txgnn"
        assert exported._meta.db_table == table_name
        assert table_name in table_names
