"""INR display formatting for PDF export."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from apps.extractors.utils.normalize import parse_indian_amount


def _digits_only(s: str) -> str:
    return re.sub(r"[^\d.\-]", "", s)


def format_indian_int(n: int) -> str:
    if n == 0:
        return "0"
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return sign + s
    last3 = s[-3:]
    rest = s[:-3]
    parts: list[str] = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    body = ",".join(parts) + "," + last3
    return sign + body


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    d = parse_indian_amount(raw)
    if d is not None:
        return d
    try:
        return Decimal(_digits_only(raw))
    except (InvalidOperation, ValueError):
        return None


def amount_nonzero_for_pdf(value) -> bool:
    """Whether to show a detail line in the computation PDF (hide pure zeros).

    Non-numeric or unparseable values return True so we do not hide possibly
    meaningful text. Losses (negative amounts) count as nonzero.
    """
    if value is None:
        return False
    raw = str(value).strip()
    if raw == "":
        return False
    d = _to_decimal(value)
    if d is None:
        return True
    return d != 0


def format_inr(value) -> str:
    """Indian-style grouping; empty → em dash."""
    if value is None:
        return "—"
    raw_in = str(value).strip()
    if raw_in == "":
        return "—"
    d = _to_decimal(value)
    if d is None:
        return raw_in
    sign = "-" if d < 0 else ""
    d = abs(d)
    s = format(d, "f")
    if "." in s:
        ip, fp = s.split(".", 1)
        fp = fp.rstrip("0")[:2]
        int_part = int(Decimal(ip))
        int_fmt = format_indian_int(int_part)
        if fp:
            return sign + int_fmt + "." + fp
        return sign + int_fmt
    int_part = int(d)
    return sign + format_indian_int(int_part)


def format_inr_pair(refund, demand) -> str:
    a = format_inr(refund)
    b = format_inr(demand)
    if a == "—" and b == "—":
        return "— / —"
    return f"{a} / {b}"


def format_inr_tax_zero(value) -> str:
    """Tax lines: treat missing as zero (standard sheet style)."""
    s = format_inr(value)
    return "0" if s == "—" else s


def mask_account_number(raw: str | None, last: int = 4) -> str:
    """Show only last N digits for external-facing display."""
    if not raw:
        return "—"
    s = re.sub(r"\s+", "", str(raw).strip())
    if len(s) <= last:
        return s
    return "*" * max(0, len(s) - last) + s[-last:]
