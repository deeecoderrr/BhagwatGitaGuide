"""Pincode → ITR StateCode lookup (India Post data, not JSON StateCode)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.extractors.india_state_codes import (
    normalize_state_code,
    state_code_from_postal_name,
    state_name_from_code,
)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "pincode_state_map.json"


def normalize_pincode(pin: str | int | float | None) -> str:
    if pin is None:
        return ""
    raw = str(pin).strip()
    if not raw or raw.lower() == "none":
        return ""
    if "." in raw:
        raw = raw.split(".", 1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        return ""
    return digits


@lru_cache(maxsize=1)
def _pincode_map() -> dict[str, str]:
    if not _DATA_PATH.is_file():
        return {}
    try:
        payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    mapping = payload.get("pincode_to_state_code")
    if not isinstance(mapping, dict):
        return {}
    out: dict[str, str] = {}
    for pin, code in mapping.items():
        pin_s = normalize_pincode(pin)
        code_s = normalize_state_code(code)
        if pin_s and code_s:
            out[pin_s] = code_s
    return out


def state_code_from_pincode(pin: str | int | float | None) -> str:
    """Return ITR StateCode for a 6-digit Indian pincode, or empty string."""
    pin_s = normalize_pincode(pin)
    if not pin_s:
        return ""
    return _pincode_map().get(pin_s, "")


def resolve_state_from_address(addr: dict[str, Any] | None) -> tuple[str, str, str]:
    """
    Resolve (state_code, state_name, source) for an ITR Address block.

    Prefers pincode lookup over JSON StateCode because filed JSON often has wrong codes.
    """
    if not addr:
        return "", "", ""

    json_code = normalize_state_code(addr.get("StateCode"))
    pin_code = state_code_from_pincode(addr.get("PinCode"))
    if pin_code:
        return pin_code, state_name_from_code(pin_code), "pincode"
    if json_code:
        return json_code, state_name_from_code(json_code), "json"
    return "", "", ""
