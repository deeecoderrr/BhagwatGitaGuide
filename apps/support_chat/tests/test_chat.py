"""Support chat tests."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.support_chat.models import SupportMessage, SupportThread


@override_settings(ITR_SUPPORT_CHAT_ENABLED=True)
class SupportChatTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("customer", "c@test.com", "pwd1234567890123456789")
        self.staff = User.objects.create_user(
            "owner",
            "owner@test.com",
            "pwd1234567890123456789",
            is_staff=True,
        )
        self.client = Client()

    def test_anonymous_redirected_from_chat_list(self) -> None:
        r = self.client.get(reverse("support_chat:list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    def test_user_creates_thread(self) -> None:
        self.client.login(username="customer", password="pwd1234567890123456789")
        with patch("apps.support_chat.views.notify_owner_new_user_message", return_value=True):
            r = self.client.post(
                reverse("support_chat:new"),
                {
                    "subject": "ITR-2 help",
                    "service": "itr2_filing",
                    "body": "Need filing support please",
                },
            )
        self.assertEqual(r.status_code, 302)
        thread = SupportThread.objects.get()
        self.assertEqual(thread.user, self.user)
        self.assertEqual(thread.messages.count(), 1)
        self.assertFalse(thread.messages.first().is_staff)

    @patch("apps.support_chat.views.notify_owner_new_user_message", return_value=True)
    def test_user_reply_on_thread(self, _mock) -> None:
        thread = SupportThread.objects.create(
            user=self.user,
            subject="Help",
            status=SupportThread.STATUS_OPEN,
        )
        SupportMessage.objects.create(
            thread=thread,
            sender=self.user,
            body="Hello",
            is_staff=False,
        )
        self.client.login(username="customer", password="pwd1234567890123456789")
        self.client.post(
            reverse("support_chat:thread", kwargs={"pk": thread.pk}),
            {"body": "Follow up message"},
        )
        self.assertEqual(thread.messages.count(), 2)

    @patch("apps.support_chat.views.notify_user_staff_reply", return_value=True)
    def test_staff_reply(self, _mock) -> None:
        thread = SupportThread.objects.create(
            user=self.user,
            subject="Help",
            status=SupportThread.STATUS_WAITING_STAFF,
        )
        SupportMessage.objects.create(
            thread=thread,
            sender=self.user,
            body="Need help",
            is_staff=False,
        )
        self.client.login(username="owner", password="pwd1234567890123456789")
        r = self.client.post(
            reverse("support_chat:staff_thread", kwargs={"pk": thread.pk}),
            {"body": "We can help — please share Form 16"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(thread.messages.filter(is_staff=True).exists())
        thread.refresh_from_db()
        self.assertEqual(thread.status, SupportThread.STATUS_WAITING_USER)

    def test_user_cannot_view_other_thread(self) -> None:
        other = User.objects.create_user("other", "o@test.com", "pwd1234567890123456789")
        thread = SupportThread.objects.create(user=other, subject="Private")
        self.client.login(username="customer", password="pwd1234567890123456789")
        r = self.client.get(reverse("support_chat:thread", kwargs={"pk": thread.pk}))
        self.assertEqual(r.status_code, 404)

    def test_poll_requires_login(self) -> None:
        thread = SupportThread.objects.create(user=self.user, subject="T")
        r = self.client.get(reverse("support_chat:thread_poll", kwargs={"pk": thread.pk}))
        self.assertEqual(r.status_code, 302)

    @override_settings(ITR_SUPPORT_CHAT_ENABLED=False)
    def test_disabled_returns_404(self) -> None:
        self.client.login(username="customer", password="pwd1234567890123456789")
        r = self.client.get(reverse("support_chat:list"))
        self.assertEqual(r.status_code, 404)
