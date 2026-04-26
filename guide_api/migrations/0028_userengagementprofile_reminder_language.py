from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guide_api", "0027_userengagementprofile_last_reminder_push_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="userengagementprofile",
            name="reminder_language",
            field=models.CharField(
                default="en",
                max_length=4,
                help_text="Language for daily reminder push copy (en|hi); mirrors app UI language.",
            ),
        ),
    ]
