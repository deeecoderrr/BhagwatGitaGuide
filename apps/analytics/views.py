"""Client-side funnel beacons (pay click, etc.)."""
from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from apps.analytics.events import (
    EVENT_ITR_PAY_CLICK,
    EVENT_ITR_PREVIEW,
    log_itr_funnel_event,
)


@require_POST
def record_event(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    event_type = str(payload.get("event_type", "")).strip()[:32]
    allowed = {EVENT_ITR_PAY_CLICK, EVENT_ITR_PREVIEW}
    if event_type not in allowed:
        return JsonResponse({"error": "Unknown event."}, status=400)

    doc_raw = payload.get("document_id")
    document_id = None
    if doc_raw is not None:
        try:
            document_id = int(doc_raw)
        except (TypeError, ValueError):
            pass

    log_itr_funnel_event(
        request,
        event_type,
        document_id=document_id,
        metadata={"source": "beacon"},
    )
    return JsonResponse({"ok": True})
