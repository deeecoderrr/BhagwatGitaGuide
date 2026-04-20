"""Normalize PAN, amounts, assessment years, and dates from raw strings."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

_PAN_RE = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
_AY_RE = re.compile(r"20\d{2}[-–]?\d{2}")


def normalize_pan(text: str | None) -> Optional[str]:
    if not text:
        return None
    m = _PAN_RE.search(text.upper().replace(" ", ""))
    if m:
        return m.group(1)
    m2 = _PAN_RE.search(text.upper())
    return m2.group(1) if m2 else None


def normalize_assessment_year(text: str | None) -> Optional[str]:
    if not text:
        return None
    m = _AY_RE.search(text.replace(" ", ""))
    if not m:
        return None
    s = m.group(0).replace("–", "-")
    if len(s) == 9 and s[4] == "-":
        return s
    return None


def parse_indian_amount(raw: str | None) -> Optional[Decimal]:
    """Parse amounts like '10,07,503' or '1007503' or '10,07503' (best effort)."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    s = s.replace(",", "").replace(" ", "")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    try:
        d = Decimal(s)
        return -d if neg else d
    except (InvalidOperation, ValueError):
        return None


def normalize_decimal_string(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return format(value, "f")


def first_amount_after_label(text: str, label_variants: list[str]) -> Optional[Decimal]:
    """Find label (case-insensitive) and take first number-like token on same or next lines."""
    lower = text.lower()
    for lab in label_variants:
        idx = lower.find(lab.lower())
        if idx == -1:
            continue
        window = text[idx : idx + 800]
        nums = re.findall(
            r"[\(]?[\-]?[\d,]+(?:\.\d+)?[\)]?",
            window.replace("\n", " "),
        )
        for n in nums:
            d = parse_indian_amount(n)
            if d is not None:
                return d
    return None
