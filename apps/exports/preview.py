"""HTML computation preview context for document detail (pre-payment)."""
from __future__ import annotations

from apps.documents.models import Document
from apps.exports.formatting import mask_aadhaar, mask_pan
from apps.exports.views import _build_export_context, _field_map
from apps.exports.weasy_render import augment_weasy_context
from apps.extractors import canonical as C
from apps.extractors.validators import coerce_refund_demand_field_map

_PREVIEW_READY_STATUSES = frozenset(
    {
        Document.STATUS_REVIEW_REQUIRED,
        Document.STATUS_APPROVED,
        Document.STATUS_EXPORTED,
    }
)


def build_computation_preview_context(document: Document) -> dict | None:
    """Build augmented export context with masked identifiers for on-page preview."""
    if document.status not in _PREVIEW_READY_STATUSES:
        return None
    if not document.extracted_fields.exists():
        return None

    fm = coerce_refund_demand_field_map(_field_map(document))
    ctx = augment_weasy_context(_build_export_context(document, fm))
    fields = dict(ctx.get("fields") or {})
    if fields.get(C.PAN):
        fields[C.PAN] = mask_pan(fields[C.PAN])
    if fields.get(C.AADHAAR):
        fields[C.AADHAAR] = mask_aadhaar(fields[C.AADHAAR])
    ctx["fields"] = fields
    ctx["preview_mode"] = True

    tds_rows = list(ctx.get("tds_rows") or [])
    ctx["tds_preview_rows"] = tds_rows[:2]
    ctx["tds_rows_hidden_count"] = max(0, len(tds_rows) - 2)
    bank_rows = list(ctx.get("bank_rows") or [])
    ctx["bank_rows_hidden_count"] = max(0, len(bank_rows) - 1)
    return ctx
