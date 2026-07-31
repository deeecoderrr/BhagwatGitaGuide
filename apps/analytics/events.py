"""ITR funnel event logging (server-side)."""
from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest

from apps.analytics.middleware import AUDIENCE_COOKIE

logger = logging.getLogger(__name__)

# Funnel steps (ordered)
EVENT_ITR_UPLOAD = "itr_upload"
EVENT_ITR_PREVIEW = "itr_preview"
EVENT_ITR_PAY_CLICK = "itr_pay_click"
EVENT_ITR_CHECKOUT_INIT = "itr_checkout_init"
EVENT_ITR_PAYMENT_SUCCESS = "itr_payment_success"
EVENT_ITR_PDF_EXPORT = "itr_pdf_export"
EVENT_APPOINTMENT_LEAD = "appointment_lead"


def visitor_id_for_request(request: HttpRequest) -> str:
    vid = getattr(request, "audience_id", "") or ""
    if not vid:
        vid = request.COOKIES.get(AUDIENCE_COOKIE, "").strip()[:64]
    return vid


def log_itr_funnel_event(
    request: HttpRequest,
    event_type: str,
    *,
    path: str = "",
    document_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a funnel event; failures are logged and swallowed."""
    vid = visitor_id_for_request(request)
    if not vid:
        return
    meta = dict(metadata or {})
    if document_id is not None:
        meta["document_id"] = document_id
    if request.user.is_authenticated:
        meta["user_id"] = request.user.pk
    try:
        from apps.analytics.models import GrowthEvent

        GrowthEvent.objects.create(
            visitor_id=vid,
            event_type=event_type,
            path=(path or request.path)[:255],
            metadata=meta,
        )
    except Exception:
        logger.exception("ITR funnel event failed: %s", event_type)
