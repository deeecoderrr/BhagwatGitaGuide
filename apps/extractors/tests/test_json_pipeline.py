"""Filed ITR JSON import."""
from __future__ import annotations

import json
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.documents.models import Document
from apps.extractors import canonical as C
from apps.extractors.json_pipeline import process_json_document_file
from apps.exports.tax_slabs import new_regime_tax_at_normal_rates

_FIX = Path(__file__).resolve().parent / "fixtures" / "min_itr3_ack.json"
_FIX_ITR1 = Path(__file__).resolve().parent / "fixtures" / "min_itr1_ack.json"
_FIX_ITR4 = Path(__file__).resolve().parent / "fixtures" / "min_itr4_ack.json"


class JsonPipelineTests(TestCase):
    def test_import_min_itr1_json(self) -> None:
        raw = _FIX_ITR1.read_bytes()
        doc = Document.objects.create(
            uploaded_file=SimpleUploadedFile("itr1_ack.json", raw),
            original_filename="itr1_ack.json",
            file_hash="pending",
            status=Document.STATUS_UPLOADED,
            upload_source=Document.UPLOAD_JSON,
        )
        process_json_document_file(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.STATUS_REVIEW_REQUIRED)
        self.assertEqual(doc.detected_type, Document.TYPE_ITR1)
        fm = {f.field_name: f.normalized_value for f in doc.extracted_fields.all()}
        self.assertEqual(fm.get(C.PAN), "ABCDE1234F")
        self.assertEqual(fm.get(C.REGIME), "New Regime")
        self.assertEqual(fm.get(C.TOTAL_INCOME), "247500")
        self.assertEqual(fm.get(C.REFUND_AMOUNT), "1500")
        self.assertEqual(fm.get(C.VERIFICATION_PLACE), "Lucknow")
        self.assertEqual(fm.get(C.SALARY_GROSS), "320000")
        self.assertEqual(fm.get(C.BALANCE_AFTER_CYLA), "315000")
        self.assertEqual(fm.get(C.OS_INTEREST_TERM_DEPOSIT), "12500")
        self.assertEqual(doc.bank_details.count(), 1)
        self.assertEqual(doc.tds_details.count(), 1)

    def test_import_min_itr4_json(self) -> None:
        raw = _FIX_ITR4.read_bytes()
        doc = Document.objects.create(
            uploaded_file=SimpleUploadedFile("itr4_ack.json", raw),
            original_filename="itr4_ack.json",
            file_hash="pending",
            status=Document.STATUS_UPLOADED,
            upload_source=Document.UPLOAD_JSON,
        )
        process_json_document_file(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.STATUS_REVIEW_REQUIRED)
        self.assertEqual(doc.detected_type, Document.TYPE_ITR4)
        fm = {f.field_name: f.normalized_value for f in doc.extracted_fields.all()}
        self.assertEqual(fm.get(C.PAN), "AFKPH4065D")
        self.assertEqual(fm.get(C.ITR_TYPE), "ITR-4")
        self.assertEqual(fm.get(C.INCOME_BUSINESS_PROFESSION), "250200")
        self.assertEqual(fm.get(C.BP_PRESUMPTIVE_44AD), "250200")
        self.assertEqual(fm.get(C.OS_INTEREST_SAVINGS), "321")
        self.assertEqual(fm.get(C.OS_INTEREST_TERM_DEPOSIT), "1650")
        self.assertEqual(fm.get(C.BUSINESS_NAME), "ALAM VASTRALAYA")

    def test_import_min_itr3_json(self) -> None:
        raw = _FIX.read_bytes()
        doc = Document.objects.create(
            uploaded_file=SimpleUploadedFile("ack.json", raw),
            original_filename="ack.json",
            file_hash="pending",
            status=Document.STATUS_UPLOADED,
            upload_source=Document.UPLOAD_JSON,
        )
        process_json_document_file(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.STATUS_REVIEW_REQUIRED)
        self.assertEqual(doc.detected_type, Document.TYPE_ITR3)
        fm = {f.field_name: f.normalized_value for f in doc.extracted_fields.all()}
        self.assertEqual(fm.get(C.PAN), "ABCDE1234F")
        self.assertEqual(fm.get(C.TOTAL_INCOME), "600000")
        self.assertEqual(fm.get(C.VERIFICATION_PLACE), "City")
        self.assertEqual(fm.get(C.FILING_DUE_DATE), "2025-07-31")
        self.assertEqual(fm.get(C.SEVENTH_PROVISO_139), "N")
        self.assertEqual(fm.get(C.REGIME), "New Regime")
        self.assertEqual(fm.get(C.INCOME_SALARY), "0")
        self.assertEqual(fm.get(C.INCOME_HOUSE_PROPERTY), "0")
        self.assertEqual(fm.get(C.DEMAND_AMOUNT), "0")
        self.assertEqual(fm.get(C.TDS_OTHER_THAN_SALARY), "0")
        self.assertEqual(fm.get(C.TDS_FROM_SALARY), "0")
        self.assertEqual(fm.get(C.TOTAL_TAX_PLUS_INTEREST), "15600")
        self.assertIn("Uttar Pradesh", fm.get(C.ADDRESS, ""))
        self.assertEqual(doc.bank_details.count(), 1)
        self.assertEqual(doc.tds_details.count(), 0)

    def test_import_itr3_schedule_tds1_salary_employer(self) -> None:
        """Schedule TDS1 — employer / Form-16 style TDS on salary."""
        data = json.loads(_FIX.read_bytes().decode())
        itr3 = data["ITR"]["ITR3"]
        itr3["ScheduleTDS1"] = {
            "TDSSalaryDtls": [
                {
                    "EmployerOrDeductorOrCollectDetl": {
                        "TAN": "DELT12345E",
                        "EmployerOrDeductorOrCollecterName": "Acme Employer Pvt Ltd",
                    },
                    "TDSSection": "192",
                    "AmtForTaxDeduct": 800000,
                    "TotTDSOnAmtPaid": 80000,
                    "ClaimOutOfTotTDSOnAmtPaid": 80000,
                }
            ],
            "TotalTDSonSalary": 80000,
        }
        tp = itr3["PartB_TTI"]["TaxPaid"]["TaxesPaid"]
        tp["TDS"] = 80000
        tp["TotalTaxesPaid"] = 80000
        raw = json.dumps(data).encode()
        doc = Document.objects.create(
            uploaded_file=SimpleUploadedFile("itr3_salary.json", raw),
            original_filename="itr3_salary.json",
            file_hash="pending",
            status=Document.STATUS_UPLOADED,
            upload_source=Document.UPLOAD_JSON,
        )
        process_json_document_file(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.detected_type, Document.TYPE_ITR3)
        fm = {f.field_name: f.normalized_value for f in doc.extracted_fields.all()}
        self.assertEqual(fm.get(C.TDS_FROM_SALARY), "80000")
        self.assertEqual(doc.tds_details.count(), 1)
        t0 = doc.tds_details.first()
        assert t0 is not None
        self.assertEqual(t0.deductor_name, "Acme Employer Pvt Ltd")
        self.assertEqual(t0.tan_pan, "DELT12345E")
        self.assertEqual(t0.head_of_income, "Salary")
        self.assertEqual(t0.amount_claimed_this_year, 80000)

    def test_new_regime_tax_matches_fixture(self) -> None:
        data = json.loads(_FIX.read_bytes())
        ti = data["ITR"]["ITR3"]["PartB-TI"]["TotalIncome"]
        tax_json = data["ITR"]["ITR3"]["PartB_TTI"]["ComputationOfTaxLiability"]["TaxPayableOnTI"][
            "TaxAtNormalRatesOnAggrInc"
        ]
        from decimal import Decimal

        self.assertEqual(new_regime_tax_at_normal_rates(Decimal(str(ti))), Decimal(str(tax_json)))
