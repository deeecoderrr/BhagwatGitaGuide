"""Export field-map coercion (refund vs demand)."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.extractors import canonical as C
from apps.extractors.validators import coerce_refund_demand_field_map


class CoerceRefundDemandTests(SimpleTestCase):
    def test_zeros_spurious_demand_when_refund_matches_paid_minus_net(self) -> None:
        fm = {
            C.REFUND_AMOUNT: "15110",
            C.DEMAND_AMOUNT: "115",
            C.TAXES_PAID_TOTAL: "68282",
            C.NET_TAX_LIABILITY: "53170",
        }
        out = coerce_refund_demand_field_map(fm)
        self.assertEqual(out[C.DEMAND_AMOUNT], "0")
        self.assertEqual(out[C.REFUND_AMOUNT], "15110")

    def test_leaves_both_when_not_refund_coherent(self) -> None:
        fm = {
            C.REFUND_AMOUNT: "10000",
            C.DEMAND_AMOUNT: "5000",
            C.TAXES_PAID_TOTAL: "10000",
            C.NET_TAX_LIABILITY: "20000",
        }
        out = coerce_refund_demand_field_map(fm)
        self.assertEqual(out[C.DEMAND_AMOUNT], "5000")
