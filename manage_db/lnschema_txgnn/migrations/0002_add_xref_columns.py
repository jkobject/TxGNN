# Generated manually 2026-03-06
#
# Adds xref columns that exist in models.py but were missing from
# the initial migration (0001_initial.py was created before these
# fields were added):
#
#   Paper      : pmc_id, arxiv_id
#   Transcript : refseq_mrna, ccds_id
#   Enhancer   : ensembl_regulatory_id, encode_experiment_id
#   Mutation   : clinvar_id, gnomad_id

import lamindb.base.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("lnschema_txgnn", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # Paper — pmc_id, arxiv_id                                            #
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="paper",
            name="pmc_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="paper",
            name="arxiv_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=64,
                null=True,
            ),
        ),
        # ------------------------------------------------------------------ #
        # Transcript — refseq_mrna, ccds_id                                   #
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="transcript",
            name="refseq_mrna",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transcript",
            name="ccds_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=32,
                null=True,
            ),
        ),
        # ------------------------------------------------------------------ #
        # Enhancer — ensembl_regulatory_id, encode_experiment_id              #
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="enhancer",
            name="ensembl_regulatory_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="enhancer",
            name="encode_experiment_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=64,
                null=True,
            ),
        ),
        # ------------------------------------------------------------------ #
        # Mutation — clinvar_id, gnomad_id                                    #
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="mutation",
            name="clinvar_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mutation",
            name="gnomad_id",
            field=lamindb.base.fields.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=64,
                null=True,
            ),
        ),
    ]
