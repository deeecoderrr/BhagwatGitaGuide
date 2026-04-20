"""New regime slab breakdown (individual) for display — verify against filed figures."""
from __future__ import annotations

from decimal import Decimal


# A.Y. 2025-26 / FY 2024-25 — new tax regime slabs (normal rates, before cess).
_SLAB_META: tuple[tuple[Decimal, Decimal, str], ...] = (
    (Decimal("300000"), Decimal("0"), "0"),
    (Decimal("400000"), Decimal("0.05"), "5"),
    (Decimal("300000"), Decimal("0.10"), "10"),
    (Decimal("300000"), Decimal("0.15"), "15"),
    (Decimal("300000"), Decimal("0.20"), "20"),
    (Decimal("300000"), Decimal("0.25"), "25"),
)


def round_total_income_288a(value: Decimal) -> Decimal:
    """Round off total income to nearest multiple of ten (illustrative u/s 288A style)."""
    v = value.quantize(Decimal("1"))
    return (v / Decimal("10")).quantize(Decimal("1"), rounding="ROUND_HALF_UP") * Decimal("10")


def round_refund_288b(value: Decimal) -> Decimal:
    """Round off refund to nearest multiple of ten (illustrative u/s 288B style)."""
    v = value.quantize(Decimal("1"))
    return (v / Decimal("10")).quantize(Decimal("1"), rounding="ROUND_HALF_UP") * Decimal("10")


def new_regime_tax_at_normal_rates(total_income: Decimal) -> Decimal:
    """
    Tax on income at normal rates (new regime), excluding cess and rebate.
    Uses the same slab walk as the department utility for typical cases.
    """
    ti = total_income
    if ti <= 0:
        return Decimal("0")
    tax = Decimal("0")
    remaining = ti
    for slab_width, rate, _pct in _SLAB_META:
        if remaining <= 0:
            break
        chunk = min(remaining, slab_width)
        tax += (chunk * rate).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
        remaining -= chunk
    if remaining > 0:
        tax += (remaining * Decimal("0.30")).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
    return tax


def new_regime_slab_rows_for_display(total_income: Decimal, *, use_rounded_income: bool = True):
    """
    Rows for CA-style slab table. When use_rounded_income, walks slabs on TI rounded to
    nearest ₹10 (288A-style) so slab "income" columns match common CA PDFs.
    Each row: {rate_pct_str, slab_income, tax_amount}
    """
    base = round_total_income_288a(total_income) if use_rounded_income else total_income
    remaining = max(base, Decimal("0"))
    rows: list[dict[str, Decimal | str]] = []
    for slab_width, rate, pct in _SLAB_META:
        if remaining <= 0:
            break
        chunk = min(remaining, slab_width)
        tax = (chunk * rate).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
        rows.append({"rate_pct": pct, "slab_income": chunk, "tax": tax})
        remaining -= chunk
    if remaining > 0:
        tax = (remaining * Decimal("0.30")).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
        rows.append({"rate_pct": "30", "slab_income": remaining, "tax": tax})
    return rows
