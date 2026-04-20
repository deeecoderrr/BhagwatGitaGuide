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
    EVENT_CHOICES = [
        (EVENT_PAGE_VIEW, "Page view"),
        (EVENT_PRICING_VIEW, "Pricing view"),
        (EVENT_SIGNUP_START, "Signup page"),
    ]

    visitor_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES)
    path = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.visitor_id[:8]}"
