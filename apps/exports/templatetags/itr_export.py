"""Template filters for export HTML/PDF."""
from __future__ import annotations

from django import template
from django.conf import settings

from apps.exports.formatting import (
    amount_nonzero_for_pdf,
    format_inr,
    mask_account_number,
    mask_aadhaar as mask_aadhaar_value,
    mask_pan as mask_pan_value,
)

register = template.Library()


@register.filter
def inr(value):
    return format_inr(value)


@register.filter(name="nz")
def nz_amount(value):
    """True if amount is non-zero detail (suppress ₹0 clutter)."""
    return amount_nonzero_for_pdf(value)


@register.filter
def mask_pan(value):
    return mask_pan_value(value)


@register.filter
def mask_aadhaar(value):
    return mask_aadhaar_value(value)


@register.filter
def mask_account(value):
    return mask_account_number(value)


@register.simple_tag
def itr_output_retention_hours():
    """Hours PDF exports stay downloadable (``ITR_OUTPUT_RETENTION_HOURS``)."""
    raw = getattr(settings, "ITR_OUTPUT_RETENTION_HOURS", 24)
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 24


@register.simple_tag
def itr_delete_input_after_export():
    """Upload removed after export (``ITR_DELETE_INPUT_AFTER_EXPORT``)."""
    return bool(getattr(settings, "ITR_DELETE_INPUT_AFTER_EXPORT", True))


@register.simple_tag
def itr_payg_intro_inr():
    """First-export intro price in INR (``ITR_FIRST_EXPORT_AMOUNT_PAISE``)."""
    return int(getattr(settings, "ITR_FIRST_EXPORT_AMOUNT_PAISE", 4900)) // 100


@register.simple_tag
def itr_payg_list_inr():
    """Standard single-export price in INR (``ITR_PAYG_AMOUNT_PAISE``)."""
    return int(getattr(settings, "ITR_PAYG_AMOUNT_PAISE", 9900)) // 100


@register.simple_tag
def itr_ca_fee_anchor_inr():
    return int(getattr(settings, "ITR_CA_FEE_ANCHOR_INR", 499))
