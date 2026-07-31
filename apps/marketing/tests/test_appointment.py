"""Appointment lead booking tests."""
from __future__ import annotations

from unittest.mock import patch

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.marketing.forms import AppointmentLeadForm
from apps.marketing.models import ServiceAppointmentLead


class AppointmentLeadFormTests(TestCase):
    def test_valid_submission(self) -> None:
        form = AppointmentLeadForm(
            data={
                "name": "Rahul Sharma",
                "phone": "9876543210",
                "email": "rahul@example.com",
                "service": "itr2_filing",
                "assessment_year": "2025-26",
                "income_source": "capital_gains",
                "notes": "Need filing help",
                "company": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_preselects_service(self) -> None:
        form = AppointmentLeadForm(service_key="itr4_filing")
        self.assertEqual(form.fields["service"].initial, "itr4_filing")

    def test_rejects_short_phone(self) -> None:
        form = AppointmentLeadForm(
            data={
                "name": "Test",
                "phone": "123",
                "email": "t@example.com",
                "service": "itr1_filing",
                "assessment_year": "2025-26",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_honeypot_blocks_bots(self) -> None:
        form = AppointmentLeadForm(
            data={
                "name": "Bot",
                "phone": "9876543210",
                "email": "bot@example.com",
                "service": "itr1_filing",
                "assessment_year": "2025-26",
                "company": "Acme Corp",
            }
        )
        self.assertFalse(form.is_valid())


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ITR_LEAD_NOTIFICATION_EMAIL="leads@test.com",
)
class AppointmentBookViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.url = reverse("marketing:appointment_book")

    def test_home_shows_plan_cards_and_form(self) -> None:
        r = self.client.get(reverse("marketing:home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="book-appointment"')
        self.assertContains(r, "ITR-2 filing")
        self.assertContains(r, "Request callback")
        self.assertContains(r, "What happens after you book")

    def test_service_page_renders(self) -> None:
        r = self.client.get(reverse("marketing:service_page", kwargs={"slug": "itr-2-filing"}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "ITR-2 filing")
        self.assertContains(r, "Capital gains")

    def test_service_page_unknown_slug_404(self) -> None:
        r = self.client.get(reverse("marketing:service_page", kwargs={"slug": "nope"}))
        self.assertEqual(r.status_code, 404)

    @patch("apps.marketing.views.send_appointment_lead_email", return_value=True)
    def test_post_from_service_page_redirects_back(self, mock_send) -> None:
        r = self.client.post(
            self.url,
            {
                "name": "Priya",
                "phone": "9123456789",
                "email": "priya@example.com",
                "service": "gst_registration",
                "assessment_year": "2025-26",
                "source_page": "gst-registration",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("gst-registration", r.url)
        self.assertIn("#book-appointment", r.url)
        mock_send.assert_called_once()

    @patch("apps.marketing.views.send_appointment_lead_email", return_value=True)
    def test_post_creates_lead_with_new_fields(self, mock_send) -> None:
        self.client.post(
            self.url,
            {
                "name": "Priya",
                "phone": "9123456789",
                "email": "priya@example.com",
                "service": "itr2_filing",
                "assessment_year": "2025-26",
                "income_source": "salary",
                "source_page": "home",
            },
        )
        lead = ServiceAppointmentLead.objects.get()
        self.assertEqual(lead.assessment_year, "2025-26")
        self.assertEqual(lead.income_source, "salary")

    def test_post_sends_email(self) -> None:
        self.client.post(
            self.url,
            {
                "name": "Amit",
                "phone": "9988776655",
                "email": "amit@example.com",
                "service": "itr3_filing",
                "assessment_year": "2025-26",
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ITR-3 filing", mail.outbox[0].subject)
        self.assertIn("2025-26", mail.outbox[0].body)

    def test_invalid_post_rerendered_with_errors(self) -> None:
        r = self.client.post(
            self.url,
            {
                "name": "",
                "phone": "bad",
                "email": "not-an-email",
                "service": "",
                "assessment_year": "2025-26",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, "book-appointment", status_code=400)
        self.assertEqual(ServiceAppointmentLead.objects.count(), 0)

    def test_query_param_preselects_service_on_home(self) -> None:
        r = self.client.get(reverse("marketing:home") + "?service=itr1_filing")
        self.assertContains(r, 'value="itr1_filing" selected')
