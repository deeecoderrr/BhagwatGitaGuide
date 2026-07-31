"""Lead bridge tests."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.marketing.models import ServiceAppointmentLead
from apps.support_chat.models import SupportThread


@override_settings(
    ITR_SUPPORT_CHAT_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LeadBridgeTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("booker", "b@test.com", "pwd1234567890123456789")
        self.client = Client()

    @patch("apps.support_chat.lead_bridge.notify_owner_new_user_message", return_value=True)
    @patch("apps.marketing.views.send_appointment_lead_email", return_value=True)
    def test_logged_in_appointment_creates_chat_thread(self, _email, _chat_notify) -> None:
        self.client.login(username="booker", password="pwd1234567890123456789")
        r = self.client.post(
            reverse("marketing:appointment_book"),
            {
                "name": "Booker",
                "phone": "9876543210",
                "email": "b@test.com",
                "service": "itr1_filing",
                "assessment_year": "2025-26",
                "income_source": "salary",
                "source_page": "home",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/chat/", r.url)
        self.assertEqual(ServiceAppointmentLead.objects.count(), 1)
        self.assertEqual(SupportThread.objects.count(), 1)
        thread = SupportThread.objects.get()
        self.assertEqual(thread.user, self.user)
        self.assertEqual(thread.messages.count(), 1)
