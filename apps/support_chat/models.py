from __future__ import annotations

from django.conf import settings
from django.db import models


class SupportThread(models.Model):
    STATUS_OPEN = "open"
    STATUS_WAITING_USER = "waiting_user"
    STATUS_WAITING_STAFF = "waiting_staff"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_WAITING_USER, "Waiting for user"),
        (STATUS_WAITING_STAFF, "Waiting for staff"),
        (STATUS_CLOSED, "Closed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_threads",
    )
    subject = models.CharField(max_length=200)
    service_key = models.CharField(max_length=40, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    lead = models.ForeignKey(
        "marketing.ServiceAppointmentLead",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_threads",
    )
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.subject} ({self.user})"


class SupportMessage(models.Model):
    thread = models.ForeignKey(
        SupportThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_messages_sent",
    )
    is_staff = models.BooleanField(default=False, db_index=True)
    body = models.TextField(max_length=4000)
    read_by_user_at = models.DateTimeField(null=True, blank=True)
    read_by_staff_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        who = "Staff" if self.is_staff else "User"
        return f"{who}: {self.body[:40]}"
