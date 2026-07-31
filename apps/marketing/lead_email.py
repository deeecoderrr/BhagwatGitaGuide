"""Email notifications for CA service appointment leads."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.marketing.forms import INCOME_SOURCE_CHOICES, AppointmentLeadForm
from apps.marketing.models import ServiceAppointmentLead
from apps.marketing.services_catalog import CA_SERVICE_BY_KEY

logger = logging.getLogger(__name__)


def lead_notification_recipient() -> str:
    return (
        getattr(settings, "ITR_LEAD_NOTIFICATION_EMAIL", "").strip()
        or getattr(settings, "ITR_CONTACT_EMAIL", "").strip()
        or getattr(settings, "SUPPORT_EMAIL", "").strip()
        or "askbhagwatgitasupport@gmail.com"
    )


def _income_source_label(key: str) -> str:
    for k, label in INCOME_SOURCE_CHOICES:
        if k == key:
            return label
    return key or "—"


def send_appointment_lead_email(
    lead: ServiceAppointmentLead,
    form: AppointmentLeadForm | None = None,
) -> bool:
    svc = CA_SERVICE_BY_KEY.get(lead.service_key)
    price = svc.price_display if svc else "—"
    subject = f"[ITR Lead] {lead.service_label} — {lead.name}"
    income = _income_source_label(lead.income_source)
    body = "\n".join(
        [
            "New appointment / service enquiry from ITR Summary",
            "",
            f"Name: {lead.name}",
            f"Phone: {lead.phone}",
            f"Email: {lead.email}",
            f"Service: {lead.service_label}",
            f"Listed price: {price}",
            f"Assessment year: {lead.assessment_year or '—'}",
            f"Income source: {income}",
            f"Source page: {lead.source_page or 'home'}",
            "",
            "Notes:",
            lead.notes.strip() or "—",
            "",
            f"Lead ID: {lead.pk}",
            f"Submitted: {lead.created_at:%d %b %Y, %I:%M %p %Z}",
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
        logger.exception("Failed to send appointment lead email for lead %s", lead.pk)
        return False
