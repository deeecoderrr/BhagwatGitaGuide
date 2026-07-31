from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketing", "0001_serviceappointmentlead"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceappointmentlead",
            name="assessment_year",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="serviceappointmentlead",
            name="income_source",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
