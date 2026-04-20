from __future__ import annotations

from django.db import models
from django.utils import timezone


class ExportedSummary(models.Model):
    document = models.ForeignKey(
        "documents.Document", on_delete=models.CASCADE, related_name="exports"
    )
    pdf_file = models.FileField(
        upload_to="itr_exports/",
        blank=True,
        max_length=500,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="PDF download allowed until this time; file removed shortly after.",
    )
    pdf_purged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the PDF blob was deleted from storage.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Exported summaries"

    def __str__(self) -> str:
        return f"Export {self.pk} for doc {self.document_id}"

    def can_download(self, now=None) -> bool:
        """True only while within retention and file still on disk."""
        now = now or timezone.now()
        if self.pdf_purged_at is not None:
            return False
        if not self.pdf_file:
            return False
        return now < self.expires_at

