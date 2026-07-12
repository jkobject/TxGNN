# Generated manually 2026-06-23 for Kanban t_3bad8f56
#
# Adds generic exact-ID KG edge and edge-evidence registries. This migration is
# schema-only: it does not sync canonical KG rows and does not write to GCS.

import django.db.models.deletion
import django.db.models.functions.datetime
import lamindb.base.fields
import lamindb.base.uids
import lamindb.base.users
import lamindb.models.run
from django.db import migrations, models


def base_fields():
    return [
        ("is_locked", lamindb.base.fields.BooleanField(blank=True, db_default=False, default=False)),
        ("_aux", lamindb.base.fields.JSONField(blank=True, db_default=None, default=None, null=True)),
        ("created_at", lamindb.base.fields.DateTimeField(blank=True, db_default=django.db.models.functions.datetime.Now(), db_index=True, editable=False)),
        ("updated_at", lamindb.base.fields.DateTimeField(blank=True, db_default=django.db.models.functions.datetime.Now(), db_index=True, editable=False)),
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("uid", lamindb.base.fields.CharField(blank=True, db_index=True, default=lamindb.base.uids.base62_12, editable=False, max_length=12, unique=True)),
    ]


def tracking_fields():
    return [
        ("branch", lamindb.base.fields.ForeignKey(blank=True, db_default=1, default=1, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="lamindb.branch")),
        ("created_on", lamindb.base.fields.ForeignKey(blank=True, db_default=1, default=1, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="lamindb.branch")),
        ("created_by", lamindb.base.fields.ForeignKey(blank=True, default=lamindb.base.users.current_user_id, editable=False, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="lamindb.user")),
        ("run", lamindb.base.fields.ForeignKey(blank=True, default=lamindb.models.run.current_run, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="lamindb.run")),
        ("space", lamindb.base.fields.ForeignKey(blank=True, db_default=1, default=1, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="lamindb.space")),
    ]


def char_field(max_length, *, unique=False):
    return lamindb.base.fields.CharField(db_index=True, max_length=max_length, unique=unique)


def nullable_char_field(max_length):
    return lamindb.base.fields.CharField(blank=True, db_index=True, default=None, max_length=max_length, null=True)


def nullable_json_field():
    return lamindb.base.fields.JSONField(blank=True, db_default=None, default=None, null=True)


def nullable_int_field():
    return lamindb.base.fields.IntegerField(blank=True, db_index=True, default=None, null=True)


def nullable_float_field():
    return lamindb.base.fields.FloatField(blank=True, db_index=True, default=None, null=True)


class Migration(migrations.Migration):
    dependencies = [("lamindb", "0183_squashed"), ("lnschema_txgnn", "0006_custom_exact_id_gap_registries")]

    operations = [
        migrations.CreateModel(name="KGEdge", fields=base_fields() + [
            ("edge_key", char_field(255, unique=True)), ("x_id", char_field(128)),
            ("x_type", char_field(32)), ("y_id", char_field(128)),
            ("y_type", char_field(32)), ("relation", char_field(96)),
            ("display_relation", nullable_char_field(128)), ("source", nullable_char_field(128)),
            ("credibility", nullable_int_field()), ("metadata", nullable_json_field()),
        ] + tracking_fields(), options={"abstract": False}, bases=(models.Model,)),
        migrations.CreateModel(name="KGEdgeEvidence", fields=base_fields() + [
            ("evidence_key", char_field(255, unique=True)), ("edge_key", char_field(255)),
            ("relation", char_field(96)), ("x_id", char_field(128)), ("x_type", char_field(32)),
            ("y_id", char_field(128)), ("y_type", char_field(32)),
            ("evidence_type", nullable_char_field(96)), ("source", nullable_char_field(128)),
            ("source_dataset", nullable_char_field(128)), ("source_record_id", nullable_char_field(255)),
            ("paper_id", nullable_char_field(64)), ("dataset_id", nullable_char_field(128)),
            ("study_id", nullable_char_field(255)), ("evidence_score", nullable_float_field()),
            ("predicate", nullable_char_field(128)), ("direction", nullable_char_field(64)),
            ("metadata", nullable_json_field()),
        ] + tracking_fields(), options={"abstract": False}, bases=(models.Model,)),
        migrations.AddIndex(model_name="kgedge", index=models.Index(fields=["relation", "x_id"], name="txgnn_edge_rel_x_idx")),
        migrations.AddIndex(model_name="kgedge", index=models.Index(fields=["relation", "y_id"], name="txgnn_edge_rel_y_idx")),
        migrations.AddIndex(model_name="kgedge", index=models.Index(fields=["x_type", "x_id"], name="txgnn_edge_x_idx")),
        migrations.AddIndex(model_name="kgedge", index=models.Index(fields=["y_type", "y_id"], name="txgnn_edge_y_idx")),
        migrations.AddIndex(model_name="kgedge", index=models.Index(fields=["relation", "x_type", "y_type"], name="txgnn_edge_rel_types_idx")),
        migrations.AddIndex(model_name="kgedge", index=models.Index(fields=["source", "relation"], name="txgnn_edge_source_rel_idx")),
        migrations.AddIndex(model_name="kgedgeevidence", index=models.Index(fields=["edge_key"], name="txgnn_ev_edge_key_idx")),
        migrations.AddIndex(model_name="kgedgeevidence", index=models.Index(fields=["relation", "x_id"], name="txgnn_ev_rel_x_idx")),
        migrations.AddIndex(model_name="kgedgeevidence", index=models.Index(fields=["relation", "y_id"], name="txgnn_ev_rel_y_idx")),
        migrations.AddIndex(model_name="kgedgeevidence", index=models.Index(fields=["source", "source_dataset"], name="txgnn_ev_source_idx")),
    ]
