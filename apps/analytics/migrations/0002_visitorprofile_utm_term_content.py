from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="visitorprofile",
            name="first_utm_content",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="visitorprofile",
            name="first_utm_term",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="visitorprofile",
            name="last_utm_content",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="visitorprofile",
            name="last_utm_term",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
