# Allow clearing upload after export (input file deleted from storage).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0009_document_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="uploaded_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to="itr_uploads/",
            ),
        ),
    ]
