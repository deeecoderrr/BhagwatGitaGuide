# Generated manually for TDS2 annexure columns.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_alter_document_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="tdsdetail",
            name="head_of_income",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
