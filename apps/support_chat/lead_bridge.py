"""Bridge appointment leads to support chat threads."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from apps.marketing.forms import INCOME_SOURCE_CHOICES
from apps.marketing.models import ServiceAppointmentLead
from apps.support_chat.models import SupportMessage, SupportThread
from apps.support_chat.notifications import notify_owner_new_user_message


def _income_source_label(key: str) -> str:
    for k, label in INCOME_SOURCE_CHOICES:
        if k == key:
            return label
    return key or "—"


def _lead_message_body(lead: ServiceAppointmentLead) -> str:
    lines = [
        "Appointment request submitted via website form",
        "",
        f"Service: {lead.service_label}",
        f"Assessment year: {lead.assessment_year or '—'}",
        f"Income source: {_income_source_label(lead.income_source)}",
        f"Phone: {lead.phone}",
        f"Email: {lead.email}",
        "",
        "Notes:",
        lead.notes.strip() or "—",
        "",
        f"Lead ID: {lead.pk}",
    ]
    return "\n".join(lines)


def create_thread_from_lead(
    user: AbstractBaseUser,
    lead: ServiceAppointmentLead,
) -> SupportThread | None:
    if not getattr(settings, "ITR_SUPPORT_CHAT_ENABLED", False):
        return None

    subject = lead.service_label
    if lead.assessment_year:
        subject = f"{lead.service_label} ({lead.assessment_year})"

    thread = SupportThread.objects.create(
        user=user,
        subject=subject[:200],
        service_key=lead.service_key,
        lead=lead,
        status=SupportThread.STATUS_WAITING_STAFF,
        last_message_at=timezone.now(),
    )
    msg = SupportMessage.objects.create(
        thread=thread,
        sender=user,
        body=_lead_message_body(lead),
        is_staff=False,
    )
    thread.last_message_at = msg.created_at
    thread.save(update_fields=["last_message_at", "updated_at"])
    notify_owner_new_user_message(msg)
    return thread
