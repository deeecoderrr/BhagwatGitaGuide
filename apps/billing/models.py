from __future__ import annotations

from django.conf import settings
from django.db import models


class RazorpayOrder(models.Model):
    """Recorded Razorpay orders for Pro subscription (audit)."""

    STATUS_CREATED = "created"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="razorpay_orders",
    )
    razorpay_order_id = models.CharField(max_length=64, db_index=True)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="INR")
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_CREATED
    )
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.razorpay_order_id} ({self.status})"
