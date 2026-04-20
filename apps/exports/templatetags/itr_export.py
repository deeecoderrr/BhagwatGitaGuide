"""Template filters for export HTML/PDF."""
from __future__ import annotations

from django import template
from django.conf import settings

from apps.exports.formatting import amount_nonzero_for_pdf, format_inr

register = template.Library()


@register.filter
def inr(value):
    return format_inr(value)


@register.filter(name="nz")
def nz_amount(value):
    """True if amount is non-zero detail (suppress ₹0 clutter)."""
    return amount_nonzero_for_pdf(value)


@register.simple_tag
def itr_output_retention_hours():
    """Hours PDF exports stay downloadable (``ITR_OUTPUT_RETENTION_HOURS``)."""
    raw = getattr(settings, "ITR_OUTPUT_RETENTION_HOURS", 24)
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 24
