"""Schedule JSON import: Redis/RQ when enabled, synchronous fallback otherwise."""
from __future__ import annotations

import logging

from django.conf import settings

from apps.documents.models import Document
from apps.extractors.jobs import process_document_job
from apps.extractors.pipeline import process_document_file

logger = logging.getLogger(__name__)


def schedule_document_processing(document: Document) -> bool:
    """
    Run import either in the background (django-rq) or inline.

    Returns True if a background job was queued, False if processing ran synchronously.
    """
    if not getattr(settings, "ITR_ASYNC_EXTRACTION", False):
        process_document_file(document)
        return False

    try:
        from django_rq import get_queue
    except ImportError:
        logger.warning("django_rq not available; running import synchronously")
        process_document_file(document)
        return False

    try:
        document.status = Document.STATUS_QUEUED
        document.save(update_fields=["status", "updated_at"])
        queue = get_queue("default")
        queue.enqueue(process_document_job, document.pk)
        return True
    except Exception as exc:
        logger.warning("RQ enqueue failed (%s); falling back to synchronous import", exc)
        document.refresh_from_db()
        if document.status == Document.STATUS_QUEUED:
            document.status = Document.STATUS_UPLOADED
            document.save(update_fields=["status", "updated_at"])
        process_document_file(document)
        return False
