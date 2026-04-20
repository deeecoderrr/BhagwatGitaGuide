from __future__ import annotations

from django.db import models


class ReviewAction(models.Model):
    """Audit trail for approve/edit on extracted values."""

    ACTION_APPROVE = "approve"
    ACTION_EDIT = "edit"
    ACTION_REJECT = "reject"

    ACTION_CHOICES = [
        (ACTION_APPROVE, "Approve"),
        (ACTION_EDIT, "Edit"),
        (ACTION_REJECT, "Reject"),
    ]

    document = models.ForeignKey(
        "documents.Document", on_delete=models.CASCADE, related_name="review_actions"
    )
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    action_type = models.CharField(max_length=32, choices=ACTION_CHOICES)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action_type} {self.field_name}"
