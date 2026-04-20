# Generated manually to align migration state with model help_text.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0005_alter_document_detected_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tdsdetail",
            name="head_of_income",
            field=models.CharField(
                blank=True,
                help_text=(
                    "e.g. Income from Other Sources "
                    "(Schedule TDS2)."
                ),
                max_length=255,
                null=True,
            ),
        ),
    ]

