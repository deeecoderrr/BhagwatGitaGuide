from __future__ import annotations

from django.conf import settings
from django.db import models


class RazorpayOrder(models.Model):
    """Recorded Razorpay orders for ITR export credit bundle purchases (audit)."""

    STATUS_CREATED = "created"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
    ]

    # ITR credit bundle keys
    BUNDLE_PAYG = "payg"
    BUNDLE_ESSENTIALS = "essentials"
    BUNDLE_PROFESSIONAL = "professional"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="razorpay_orders",
    )
    razorpay_order_id = models.CharField(max_length=64, db_index=True)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="INR")
    bundle_key = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="ITR credit bundle: payg / essentials / professional",
    )
    credits_granted = models.PositiveIntegerField(
        default=0,
        help_text="Number of export credits added on payment success.",
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_CREATED
    )
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.razorpay_order_id} [{self.bundle_key}] ({self.status})"


class GuestOrder(models.Model):
    """Razorpay PAYG ₹50 order for a guest (unauthenticated) user.

    Credits are session-based; this model is the audit trail.
    """

    STATUS_CREATED = "created"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
    ]

    guest_name = models.CharField(max_length=120)
    guest_email = models.EmailField(db_index=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    razorpay_order_id = models.CharField(max_length=64, db_index=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    amount_paise = models.PositiveIntegerField(default=500)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_CREATED)
    credits_granted = models.PositiveIntegerField(default=1)
    export_used = models.BooleanField(default=False)
    raw_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.razorpay_order_id} [guest:{self.guest_email}] ({self.status})"
