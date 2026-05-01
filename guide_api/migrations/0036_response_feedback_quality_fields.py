from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide_api", "0034_user_gita_sequence_journey"),
    ]

    operations = [
        migrations.AddField(
            model_name="responsefeedback",
            name="surface",
            field=models.CharField(
                choices=[
                    ("api", "API"),
                    ("mobile_ask", "Mobile Ask"),
                    ("web_chat_ui", "Web Chat UI"),
                ],
                default="api",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="responsefeedback",
            name="response_preview",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="responsefeedback",
            name="primary_verse_ref",
            field=models.CharField(blank=True, db_index=True, max_length=16),
        ),
        migrations.AddField(
            model_name="responsefeedback",
            name="issue_bucket",
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
        migrations.AddField(
            model_name="responsefeedback",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("reviewed", "Reviewed"),
                    ("actioned", "Actioned"),
                    ("ignored", "Ignored"),
                ],
                db_index=True,
                default="new",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="responsefeedback",
            name="response_context",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
