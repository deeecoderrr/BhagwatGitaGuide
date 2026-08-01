"""Lazy cleanup of stale ITR JSON uploads (no cron)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_STALE_JSON_PURGE_CACHE_KEY = "itr:stale_json_purge:last_run"
_STALE_JSON_PURGE_INTERVAL_SECONDS = 86400  # at most once per calendar day


def input_retention_days() -> int:
    return int(getattr(settings, "ITR_INPUT_RETENTION_DAYS", 7))


def purge_stale_json_uploads(now=None) -> int:
    """
    Delete stored JSON files for documents older than ITR_INPUT_RETENTION_DAYS.

    Keeps Document rows and extracted fields; only removes the upload blob.
    """
    from apps.documents.models import Document

    now = now or timezone.now()
    cutoff = now - timedelta(days=input_retention_days())
    qs = Document.objects.filter(
        created_at__lt=cutoff,
        upload_source=Document.UPLOAD_JSON,
    ).exclude(uploaded_file="").exclude(uploaded_file__isnull=True)

    purged = 0
    for doc in qs.iterator(chunk_size=50):
        try:
            with transaction.atomic():
                fresh = Document.objects.get(pk=doc.pk)
                if not fresh.uploaded_file:
                    continue
                fresh.uploaded_file.delete(save=False)
                fresh.uploaded_file = None
                fresh.save(update_fields=["uploaded_file", "updated_at"])
                purged += 1
        except Exception as exc:
            logger.warning("purge stale json doc %s failed: %s", doc.pk, exc)
    return purged


def maybe_purge_stale_json_uploads_on_upload() -> int:
    """
    Run stale JSON purge when a visitor uploads, at most once per 24 hours.

    Uses cache.add so concurrent uploads do not all scan storage.
    """
    if cache.add(
        _STALE_JSON_PURGE_CACHE_KEY,
        timezone.now().isoformat(),
        timeout=_STALE_JSON_PURGE_INTERVAL_SECONDS,
    ):
        return purge_stale_json_uploads()
    return 0
