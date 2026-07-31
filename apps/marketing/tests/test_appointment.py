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
                "notes": "AY 2025-26",
                "company": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_short_phone(self) -> None:
        form = AppointmentLeadForm(
            data={
                "name": "Test",
                "phone": "123",
                "email": "t@example.com",
                "service": "itr1_filing",
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

    def test_home_shows_services_and_form(self) -> None:
        r = self.client.get(reverse("marketing:home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="book-appointment"')
        self.assertContains(r, "ITR-2 filing")
        self.assertContains(r, "Request callback")

    @patch("apps.marketing.views.send_appointment_lead_email", return_value=True)
    def test_post_creates_lead_and_redirects(self, mock_send) -> None:
        r = self.client.post(
            self.url,
            {
                "name": "Priya",
                "phone": "9123456789",
                "email": "priya@example.com",
                "service": "gst_registration",
                "notes": "Need GST for new shop",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.endswith("#book-appointment"))
        lead = ServiceAppointmentLead.objects.get()
        self.assertEqual(lead.name, "Priya")
        self.assertEqual(lead.service_key, "gst_registration")
        self.assertTrue(lead.email_sent)
        mock_send.assert_called_once()

    def test_post_sends_email(self) -> None:
        self.client.post(
            self.url,
            {
                "name": "Amit",
                "phone": "9988776655",
                "email": "amit@example.com",
                "service": "itr3_filing",
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ITR-3 filing", mail.outbox[0].subject)
        self.assertIn("amit@example.com", mail.outbox[0].body)

    def test_invalid_post_rerendered_with_errors(self) -> None:
        r = self.client.post(
            self.url,
            {
                "name": "",
                "phone": "bad",
                "email": "not-an-email",
                "service": "",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, "book-appointment", status_code=400)
        self.assertEqual(ServiceAppointmentLead.objects.count(), 0)
