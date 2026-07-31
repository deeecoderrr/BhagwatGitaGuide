from __future__ import annotations

from django.conf import settings
from django.db import models


class VisitorProfile(models.Model):
    """Stable browser cookie identity + first-touch UTM + visit counts."""

    visitor_id = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="visitor_profiles",
    )
    visit_count = models.PositiveIntegerField(default=0)
    first_utm_source = models.CharField(max_length=64, blank=True)
    first_utm_medium = models.CharField(max_length=64, blank=True)
    first_utm_campaign = models.CharField(max_length=64, blank=True)
    first_utm_term = models.CharField(max_length=64, blank=True)
    first_utm_content = models.CharField(max_length=64, blank=True)
    last_utm_source = models.CharField(max_length=64, blank=True)
    last_utm_medium = models.CharField(max_length=64, blank=True)
    last_utm_campaign = models.CharField(max_length=64, blank=True)
    last_utm_term = models.CharField(max_length=64, blank=True)
    last_utm_content = models.CharField(max_length=64, blank=True)
    last_path = models.CharField(max_length=255, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        return self.visitor_id[:16]


class GrowthEvent(models.Model):
    """Lightweight funnel events (landing, pricing, signup intent)."""

    EVENT_PAGE_VIEW = "page_view"
    EVENT_PRICING_VIEW = "pricing_view"
    EVENT_SIGNUP_START = "signup_start"
    EVENT_ITR_UPLOAD = "itr_upload"
    EVENT_ITR_PREVIEW = "itr_preview"
    EVENT_ITR_PAY_CLICK = "itr_pay_click"
    EVENT_ITR_CHECKOUT_INIT = "itr_checkout_init"
    EVENT_ITR_PAYMENT_SUCCESS = "itr_payment_success"
    EVENT_ITR_PDF_EXPORT = "itr_pdf_export"
    EVENT_APPOINTMENT_LEAD = "appointment_lead"
    EVENT_SUPPORT_CHAT_OPEN = "support_chat_open"
    EVENT_SUPPORT_CHAT_MESSAGE = "support_chat_message"
    EVENT_CHOICES = [
        (EVENT_PAGE_VIEW, "Page view"),
        (EVENT_PRICING_VIEW, "Pricing view"),
        (EVENT_SIGNUP_START, "Signup page"),
        (EVENT_ITR_UPLOAD, "ITR upload"),
        (EVENT_ITR_PREVIEW, "ITR preview viewed"),
        (EVENT_ITR_PAY_CLICK, "Pay button clicked"),
        (EVENT_ITR_CHECKOUT_INIT, "Checkout initiated"),
        (EVENT_ITR_PAYMENT_SUCCESS, "Payment success"),
        (EVENT_ITR_PDF_EXPORT, "PDF exported"),
        (EVENT_APPOINTMENT_LEAD, "Appointment lead"),
        (EVENT_SUPPORT_CHAT_OPEN, "Support chat opened"),
        (EVENT_SUPPORT_CHAT_MESSAGE, "Support chat message"),
    ]

    visitor_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    path = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.visitor_id[:8]}"
