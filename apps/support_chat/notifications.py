"""Email alerts for support chat."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.marketing.lead_email import lead_notification_recipient
from apps.support_chat.models import SupportMessage, SupportThread

logger = logging.getLogger(__name__)


def notify_owner_new_user_message(message: SupportMessage) -> bool:
    thread = message.thread
    subject = f"[ITR Chat] {thread.subject} — {thread.user.get_username()}"
    body = "\n".join(
        [
            "New message on ITR Support Chat",
            "",
            f"From: {thread.user.get_username()} ({thread.user.email})",
            f"Thread: {thread.subject}",
            f"Thread ID: {thread.pk}",
            "",
            message.body,
            "",
            f"Reply in Django admin or staff inbox: thread #{thread.pk}",
        ]
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or lead_notification_recipient()
    try:
        send_mail(
            subject,
            body,
            from_email,
            [lead_notification_recipient()],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to notify owner of chat message %s", message.pk)
        return False


def notify_user_staff_reply(message: SupportMessage) -> bool:
    thread = message.thread
    user_email = (thread.user.email or "").strip()
    if not user_email:
        return False
    subject = f"Re: {thread.subject} — ITR Summary"
    body = "\n".join(
        [
            f"Hi {thread.user.get_username()},",
            "",
            "Our team replied to your support conversation:",
            "",
            message.body,
            "",
            "Sign in to continue the conversation on the website.",
            "",
            "— ITR Summary team",
        ]
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or lead_notification_recipient()
    try:
        send_mail(
            subject,
            body,
            from_email,
            [user_email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to notify user of staff reply %s", message.pk)
        return False
