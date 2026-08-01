"""Pincode-based state resolution tests."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.extractors.india_state_codes import state_name_from_code
from apps.extractors.pincode_state import (
    normalize_pincode,
    resolve_state_from_address,
    state_code_from_pincode,
)


class PincodeStateTests(SimpleTestCase):
    def test_normalize_pincode(self) -> None:
        self.assertEqual(normalize_pincode(560001), "560001")
        self.assertEqual(normalize_pincode("560001.0"), "560001")
        self.assertEqual(normalize_pincode("bad"), "")

    def test_state_code_from_pincode_bangalore(self) -> None:
        code = state_code_from_pincode("560001")
        self.assertEqual(code, "29")
        self.assertEqual(state_name_from_code(code), "Karnataka")

    def test_state_code_from_pincode_lucknow(self) -> None:
        self.assertEqual(state_code_from_pincode("226001"), "09")
        self.assertEqual(state_code_from_pincode("272182"), "09")

    def test_resolve_prefers_pincode_over_wrong_json_code(self) -> None:
        addr = {"PinCode": 560001, "StateCode": "31"}
        code, name, source = resolve_state_from_address(addr)
        self.assertEqual(source, "pincode")
        self.assertEqual(code, "29")
        self.assertEqual(name, "Karnataka")

    def test_resolve_falls_back_to_json_without_pincode(self) -> None:
        addr = {"StateCode": "09"}
        code, name, source = resolve_state_from_address(addr)
        self.assertEqual(source, "json")
        self.assertEqual(code, "09")
        self.assertEqual(name, "Uttar Pradesh")
