from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0003_growth_event_itr_funnel"),
    ]

    operations = [
        migrations.AlterField(
            model_name="growthevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("page_view", "Page view"),
                    ("pricing_view", "Pricing view"),
                    ("signup_start", "Signup page"),
                    ("itr_upload", "ITR upload"),
                    ("itr_preview", "ITR preview viewed"),
                    ("itr_pay_click", "Pay button clicked"),
                    ("itr_checkout_init", "Checkout initiated"),
                    ("itr_payment_success", "Payment success"),
                    ("itr_pdf_export", "PDF exported"),
                    ("appointment_lead", "Appointment lead"),
                ],
                max_length=32,
            ),
        ),
    ]
