from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ServiceAppointmentLead",
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
                ("name", models.CharField(max_length=120)),
                ("phone", models.CharField(max_length=20)),
                ("email", models.EmailField(max_length=254)),
                ("service_key", models.CharField(db_index=True, max_length=40)),
                ("service_label", models.CharField(max_length=160)),
                ("notes", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("closed", "Closed"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=16,
                    ),
                ),
                ("source_page", models.CharField(default="home", max_length=64)),
                ("visitor_id", models.CharField(blank=True, max_length=64)),
                ("email_sent", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
