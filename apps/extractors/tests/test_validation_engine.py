"""Computation validation engine."""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.documents.models import BankDetail, Document, TDSDetail
from apps.extractors import canonical as C
from apps.extractors.validation_engine import Severity, run_computation_validation


class ValidationEngineTests(SimpleTestCase):
    def test_i1_gti_matches_heads(self) -> None:
        fm = {
            C.ASSESSEE_NAME: "Test",
            C.PAN: "ABCDE1234F",
            C.ASSESSMENT_YEAR: "2022-23",
            C.ITR_TYPE: "ITR-4",
            C.INCOME_SALARY: "0",
            C.INCOME_HOUSE_PROPERTY: "0",
            C.INCOME_BUSINESS_PROFESSION: "190000",
            C.INCOME_OTHER_SOURCES: "6",
            C.GROSS_TOTAL_INCOME: "190006",
            C.TOTAL_DEDUCTIONS: "0",
            C.TOTAL_INCOME: "190006",
        }
        out = run_computation_validation(fm, [], [], Document.TYPE_ITR4)
        codes = {x.rule: x.status for x in out}
        self.assertEqual(codes.get("I1"), Severity.PASS)

    def test_i1_itr3_uses_part_b_ti_line6_when_present(self) -> None:
        """ITR-3 GTI can exceed salary+HP+biz+OS (e.g. capital gains); reconcile to line 6."""
        fm = {
            C.ASSESSEE_NAME: "Test",
            C.PAN: "ABCDE1234F",
            C.ASSESSMENT_YEAR: "2025-26",
            C.ITR_TYPE: "ITR-3",
            C.INCOME_SALARY: "0",
            C.INCOME_HOUSE_PROPERTY: "0",
            C.INCOME_BUSINESS_PROFESSION: "100000",
            C.INCOME_OTHER_SOURCES: "5000",
            C.TOTAL_HEAD_WISE_INCOME: "200000",
            C.GROSS_TOTAL_INCOME: "200000",
            C.TOTAL_DEDUCTIONS: "0",
            C.TOTAL_INCOME: "200000",
        }
        out = run_computation_validation(fm, [], [], Document.TYPE_ITR3)
        i1 = [x for x in out if x.rule == "I1"]
        self.assertTrue(i1)
        self.assertEqual(i1[0].status, Severity.PASS)

    def test_tds_fail_when_d15_positive_no_rows(self) -> None:
        fm = {
            C.ASSESSEE_NAME: "Test",
            C.PAN: "ABCDE1234F",
            C.ASSESSMENT_YEAR: "2022-23",
            C.ITR_TYPE: "ITR-4",
            C.TDS_TOTAL: "89",
        }
        out = run_computation_validation(fm, [], [], Document.TYPE_ITR4)
        tds2 = [x for x in out if x.rule == "TDS2"]
        self.assertTrue(tds2)
        self.assertEqual(tds2[0].status, Severity.FAIL)

    def test_tax6_refund_rounding_tolerance(self) -> None:
        """Filed refund may differ by ₹1–2 from paid − net tax (rounding u/s 288B)."""
        fm = {
            C.ASSESSEE_NAME: "Test",
            C.PAN: "ABCDE1234F",
            C.ASSESSMENT_YEAR: "2022-23",
            C.ITR_TYPE: "ITR-4",
            C.NET_TAX_LIABILITY: "0",
            C.TAXES_PAID_TOTAL: "89",
            C.REFUND_AMOUNT: "90",
            C.DEMAND_AMOUNT: "0",
        }
        out = run_computation_validation(fm, [], [], Document.TYPE_ITR4)
        tax6 = [x for x in out if x.rule == "TAX6"]
        self.assertTrue(tax6)
        self.assertEqual(tax6[0].status, Severity.PASS)

    def test_i4_rounded_total_matches_288a(self) -> None:
        fm = {
            C.ASSESSEE_NAME: "Test",
            C.PAN: "ABCDE1234F",
            C.ASSESSMENT_YEAR: "2022-23",
            C.ITR_TYPE: "ITR-4",
            C.TOTAL_INCOME: "190006",
            C.ROUNDED_TOTAL_INCOME: "190010",
        }
        out = run_computation_validation(fm, [], [], Document.TYPE_ITR1)
        i4 = [x for x in out if x.rule == "I4"]
        self.assertTrue(i4)
        self.assertEqual(i4[0].status, Severity.PASS)
