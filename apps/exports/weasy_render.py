"""CA-style computation PDF via HTML/CSS + WeasyPrint (beige section layout)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.extractors import canonical as C
from apps.extractors.utils import normalize as N
from apps.exports.formatting import format_inr
from apps.exports.tax_slabs import new_regime_slab_rows_for_display


def _d_amount(fm: dict[str, str], key: str) -> Decimal:
    raw = (fm.get(key) or "").strip()
    v = N.parse_indian_amount(raw)
    if v is not None:
        return v
    try:
        return Decimal(str(raw).replace(",", ""))
    except Exception:
        return Decimal("0")


def _fmt_iso_date_footer(iso: str) -> str:
    raw = (iso or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        y, m, d = raw[:4], raw[5:7], raw[8:10]
        months = (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        )
        mi = int(m) - 1
        if 0 <= mi < 12:
            return f"{int(d):02d}-{months[mi]}-{y}"
    return raw


def _footer_report_date_line(fm: dict[str, str]) -> str:
    fixed = getattr(settings, "COMPUTATION_PDF_REPORT_DATE", None) or ""
    if fixed.strip():
        return fixed.strip()
    fd = (fm.get(C.FILING_DATE) or "").strip()
    if fd:
        return _fmt_iso_date_footer(fd)
    return timezone.now().strftime("%d-%b-%Y")


def _pick_primary_bank(banks) -> object | None:
    """Prefer the account marked for refund (after normalization: typically last Yes)."""
    rows = list(banks)
    for b in reversed(rows):
        nom = (getattr(b, "nominate_for_refund", None) or "").strip().lower()
        if nom in ("yes", "y"):
            return b
    return rows[0] if rows else None


def augment_weasy_context(base: dict) -> dict:
    """Add slab table, firm header, primary bank, footer date for the WeasyPrint template."""
    ctx = dict(base)
    fm = ctx.get("fields") or {}
    ti = _d_amount(fm, C.TOTAL_INCOME)
    raw_rows = new_regime_slab_rows_for_display(ti, use_rounded_income=True)
    ctx["slab_rows"] = []
    for r in raw_rows:
        tax_amt = r["tax"]
        tax_disp = "Nil" if tax_amt == 0 else format_inr(tax_amt)
        ctx["slab_rows"].append(
            {
                "rate_pct": r["rate_pct"],
                "slab_income_inr": format_inr(r["slab_income"]),
                "tax_disp": tax_disp,
            }
        )
    firm = getattr(settings, "COMPUTATION_PDF_FIRM_NAME", None) or ""
    ctx["computation_firm_name"] = firm.strip()
    ctx["computation_footer_brand"] = getattr(
        settings, "COMPUTATION_PDF_FOOTER_BRAND", ""
    )
    ctx["footer_report_date"] = _footer_report_date_line(fm)
    ctx["primary_bank"] = _pick_primary_bank(ctx.get("bank_rows") or [])
    ctx["weasy_show_validation"] = getattr(
        settings, "WEASY_PRINT_SHOW_VALIDATION", False
    )
    pre_raw = (fm.get(C.REFUND_PRE_288B) or "").strip()
    if pre_raw:
        ctx["refund_display_pre"] = format_inr(pre_raw)
    else:
        paid = _d_amount(fm, C.TAXES_PAID_TOTAL)
        net = _d_amount(fm, C.NET_TAX_LIABILITY)
        if net == 0:
            net = _d_amount(fm, C.GROSS_TAX_LIABILITY)
        ctx["refund_display_pre"] = format_inr(max(paid - net, Decimal("0")))
    ctx["refund_display_rounded"] = format_inr(fm.get(C.ROUNDED_REFUND_AMOUNT))
    ga = ctx.get("generated_at")
    if isinstance(ga, datetime):
        ctx["generated_at_short"] = ga.strftime("%d-%b-%Y %H:%M")
    else:
        ctx["generated_at_short"] = ""
    return ctx


def render_computation_weasy_pdf(context: dict) -> bytes:
    ctx = augment_weasy_context(context)
    html = render_to_string("exports/ca_computation_weasy.html", ctx)
    buf = BytesIO()
    HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(
        buf,
        presentational_hints=True,
    )
    return buf.getvalue()
