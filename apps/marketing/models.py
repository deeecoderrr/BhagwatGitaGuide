from __future__ import annotations

from django.db import models


class ServiceAppointmentLead(models.Model):
    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_CLOSED, "Closed"),
    ]

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    service_key = models.CharField(max_length=40, db_index=True)
    service_label = models.CharField(max_length=160)
    assessment_year = models.CharField(max_length=16, blank=True)
    income_source = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
    )
    source_page = models.CharField(max_length=64, default="home")
    visitor_id = models.CharField(max_length=64, blank=True)
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} — {self.service_label}"
