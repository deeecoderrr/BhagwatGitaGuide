"""PDF formatting and render smoke tests."""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from apps.exports.formatting import amount_nonzero_for_pdf, format_inr, format_inr_pair
from apps.exports.weasy_render import render_computation_weasy_pdf
from apps.exports.pdf_render import render_computation_summary_pdf
from apps.extractors import canonical as C


class AmountNonzeroPdfTests(SimpleTestCase):
    def test_zero_empty_suppressed(self) -> None:
        self.assertFalse(amount_nonzero_for_pdf(None))
        self.assertFalse(amount_nonzero_for_pdf(""))
        self.assertFalse(amount_nonzero_for_pdf("0"))

    def test_positive_negative_shown(self) -> None:
        self.assertTrue(amount_nonzero_for_pdf("1"))
        self.assertTrue(amount_nonzero_for_pdf(Decimal("-4000")))
        self.assertTrue(amount_nonzero_for_pdf("1,50,000"))

    def test_unparseable_kept(self) -> None:
        """Do not hide lines that failed numeric parse (might be explanatory text)."""
        self.assertTrue(amount_nonzero_for_pdf("See schedule"))


class InrFormattingTests(SimpleTestCase):
    def test_groups_lakhs(self) -> None:
        self.assertEqual(format_inr("190000"), "1,90,000")
        self.assertEqual(format_inr(Decimal("89")), "89")

    def test_pair(self) -> None:
        self.assertIn("90", format_inr_pair("90", "0"))


class PdfRenderSmokeTests(SimpleTestCase):
    def test_produces_non_empty_pdf(self) -> None:
        raw = render_computation_summary_pdf(
            {
                "title": "Income & Tax Computation — A.Y. 2022-23",
                "fields": {
                    C.ASSESSEE_NAME: "Test User",
                    C.PAN: "ABCDE1234F",
                    C.ASSESSMENT_YEAR: "2022-23",
                    C.ITR_TYPE: "ITR-4",
                    C.INCOME_SALARY: "0",
                    C.INCOME_HOUSE_PROPERTY: "0",
                    C.INCOME_BUSINESS_PROFESSION: "190000",
                    C.INCOME_OTHER_SOURCES: "6",
                    C.GROSS_TOTAL_INCOME: "190006",
                    C.TOTAL_DEDUCTIONS: "0",
                    C.TOTAL_INCOME: "190010",
                    C.GROSS_TAX_LIABILITY: "0",
                    C.NET_TAX_LIABILITY: "0",
                    C.TAXES_PAID_TOTAL: "89",
                    C.TDS_TOTAL: "89",
                    C.REFUND_AMOUNT: "90",
                    C.DEMAND_AMOUNT: "0",
                },
                "bank_rows": [],
                "tds_rows": [],
                "validation_findings": [],
                "labels": {},
                "generated_at": timezone.now(),
            }
        )
        self.assertGreater(len(raw), 800)
        self.assertEqual(raw[:4], b"%PDF")


class WeasyComputationPdfTests(SimpleTestCase):
    def test_weasy_pdf_smoke_zero_heavy_fields(self) -> None:
        """Zero-suppressed template must still render valid PDF."""
        raw = render_computation_weasy_pdf(
            {
                "fields": {
                    C.ASSESSEE_NAME: "Zero Case",
                    C.PAN: "ABCDE1234F",
                    C.ASSESSMENT_YEAR: "2025-26",
                    C.ITR_TYPE: "ITR-4",
                    C.INCOME_SALARY: "0",
                    C.INCOME_HOUSE_PROPERTY: "0",
                    C.INCOME_BUSINESS_PROFESSION: "50000",
                    C.INCOME_OTHER_SOURCES: "0",
                    C.GROSS_TOTAL_INCOME: "50000",
                    C.TOTAL_HEAD_WISE_INCOME: "50000",
                    C.TOTAL_DEDUCTIONS: "0",
                    C.TOTAL_INCOME: "50000",
                    C.ROUNDED_TOTAL_INCOME: "50000",
                    C.TAX_NORMAL_RATES: "0",
                    C.REBATE_87A: "0",
                    C.TAX_PAYABLE_ON_TOTAL_INCOME: "0",
                    C.CESS: "0",
                    C.GROSS_TAX_LIABILITY: "0",
                    C.NET_TAX_LIABILITY: "0",
                    C.TAXES_PAID_TOTAL: "0",
                    C.TDS_TOTAL: "0",
                    C.REFUND_AMOUNT: "0",
                    C.DEDUCTION_80C: "0",
                    C.DEDUCTION_80D: "0",
                },
                "bank_rows": [],
                "tds_rows": [],
                "validation_findings": [],
            }
        )
        self.assertGreater(len(raw), 800)
        self.assertEqual(raw[:4], b"%PDF")
