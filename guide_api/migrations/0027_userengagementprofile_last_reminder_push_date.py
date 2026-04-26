# Generated manually for push reminder deduplication.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide_api", "0026_alter_billingrecord_payment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="userengagementprofile",
            name="last_reminder_push_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
