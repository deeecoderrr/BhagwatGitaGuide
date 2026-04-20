"""ITR PDF + upload retention (storage minimization)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def output_retention_hours() -> float:
    return float(getattr(settings, "ITR_OUTPUT_RETENTION_HOURS", 24))


def delete_input_after_export_enabled() -> bool:
    return getattr(settings, "ITR_DELETE_INPUT_AFTER_EXPORT", True)


def purge_expired_exports(now=None):
    """Remove PDF files whose retention window ended; keeps rows for expired UI."""
    now = now or timezone.now()

    # exports.ExportedSummary imported lazily to avoid circular imports in migrations
    from apps.exports.models import ExportedSummary

    qs = ExportedSummary.objects.filter(expires_at__lte=now, pdf_purged_at__isnull=True)
    purged = 0
    for exp in qs.iterator(chunk_size=50):
        try:
            with transaction.atomic():
                fresh = ExportedSummary.objects.get(pk=exp.pk)
                if fresh.pdf_purged_at is not None:
                    continue
                if fresh.pdf_file:
                    fresh.pdf_file.delete(save=False)
                fresh.pdf_purged_at = now
                fresh.save(update_fields=["pdf_file", "pdf_purged_at"])
                purged += 1
        except Exception as exc:
            logger.warning("purge export %s failed: %s", exp.pk, exc)
    return purged


def delete_document_upload_after_export(document) -> None:
    """Delete stored upload (JSON/PDF) after a successful export when enabled."""
    if not delete_input_after_export_enabled():
        return
    if not document.uploaded_file:
        return
    document.uploaded_file.delete(save=False)
    document.uploaded_file = None
    document.save(update_fields=["uploaded_file", "updated_at"])
