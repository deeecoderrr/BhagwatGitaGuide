from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide_api", "0013_supportticket"),
    ]

    operations = [
        migrations.CreateModel(
            name="RequestQuotaSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "singleton",
                    models.BooleanField(default=True, editable=False, unique=True),
                ),
                ("guest_limit_enabled", models.BooleanField(default=True)),
                ("guest_ask_limit", models.PositiveIntegerField(default=3)),
                ("free_limit_enabled", models.BooleanField(default=True)),
                ("free_daily_ask_limit", models.PositiveIntegerField(default=5)),
                ("pro_limit_enabled", models.BooleanField(default=True)),
                ("pro_daily_ask_limit", models.PositiveIntegerField(default=10000)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Request quota settings",
                "verbose_name_plural": "Request quota settings",
            },
        ),
    ]
