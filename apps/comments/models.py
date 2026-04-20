from __future__ import annotations

from django.conf import settings
from django.db import models


class Comment(models.Model):
    """Threaded comments on marketing pages (e.g. home)."""

    PAGE_HOME = "home"

    page_slug = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="page_comments",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["page_slug", "parent", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.page_slug}:{self.pk}"
