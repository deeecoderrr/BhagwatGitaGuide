"""Migration to add StreakFreeze model."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("guide_api", "0038_mood_checkin_gratitude_entry"),
    ]

    operations = [
        migrations.CreateModel(
            name="StreakFreeze",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="streak_freezes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("used_on_date", models.DateField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-used_on_date"],
            },
        ),
        migrations.AddIndex(
            model_name="streakfreeze",
            index=models.Index(fields=["user", "used_on_date"], name="sf_user_date_idx"),
        ),
        migrations.AddConstraint(
            model_name="streakfreeze",
            constraint=models.UniqueConstraint(fields=["user", "used_on_date"], name="unique_sf_user_date"),
        ),
    ]
