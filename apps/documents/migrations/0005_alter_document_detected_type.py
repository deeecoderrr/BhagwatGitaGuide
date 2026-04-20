# Generated manually to add ITR-3 as a classified document type.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0004_tdsdetail_head_of_income"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="detected_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ITR1", "ITR-1"),
                    ("ITR3", "ITR-3"),
                    ("ITR4", "ITR-4"),
                    ("UNKNOWN", "Unknown"),
                ],
                default="UNKNOWN",
                max_length=20,
            ),
        ),
    ]

