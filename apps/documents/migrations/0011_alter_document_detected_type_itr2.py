from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0010_document_upload_optional"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="detected_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ITR1", "ITR-1"),
                    ("ITR2", "ITR-2"),
                    ("ITR3", "ITR-3"),
                    ("ITR4", "ITR-4"),
                    ("UNKNOWN", "Unknown"),
                ],
                default="UNKNOWN",
                max_length=20,
            ),
        ),
    ]
