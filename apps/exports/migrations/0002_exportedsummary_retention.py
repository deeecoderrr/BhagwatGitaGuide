# Generated manually for ITR PDF retention.

import datetime

from django.db import migrations, models


def backfill_expires_at(apps, schema_editor):
    ExportedSummary = apps.get_model("exports", "ExportedSummary")
    for row in ExportedSummary.objects.all().iterator(chunk_size=100):
        if row.expires_at is None:
            row.expires_at = row.created_at + datetime.timedelta(hours=24)
            row.save(update_fields=["expires_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("exports", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="exportedsummary",
            name="expires_at",
            field=models.DateTimeField(
                db_index=True,
                help_text="PDF download allowed until this time.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="exportedsummary",
            name="pdf_purged_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the PDF blob was deleted from storage.",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_expires_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="exportedsummary",
            name="expires_at",
            field=models.DateTimeField(
                db_index=True,
                help_text=(
                    "PDF download allowed until this time; "
                    "file removed shortly after."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="exportedsummary",
            name="pdf_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                upload_to="itr_exports/",
            ),
        ),
    ]
