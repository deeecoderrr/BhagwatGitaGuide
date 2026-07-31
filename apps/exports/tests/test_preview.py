"""Tests for HTML computation preview context."""
from __future__ import annotations

from django.test import TestCase

from apps.documents.models import Document, ExtractedField
from apps.exports.formatting import mask_aadhaar, mask_pan
from apps.exports.preview import build_computation_preview_context
from apps.extractors import canonical as C


class MaskingTests(TestCase):
    def test_mask_pan(self) -> None:
        self.assertEqual(mask_pan("ABCDE1234F"), "AB*******F")

    def test_mask_aadhaar(self) -> None:
        self.assertEqual(mask_aadhaar("1234 5678 9012"), "XXXX XXXX 9012")


class PreviewContextTests(TestCase):
    def test_builds_for_review_required_document(self) -> None:
        doc = Document.objects.create(
            original_filename="sample.json",
            detected_type=Document.TYPE_ITR2,
            status=Document.STATUS_REVIEW_REQUIRED,
        )
        fields = {
            C.ASSESSEE_NAME: "Preview User",
            C.PAN: "ABCDE1234F",
            C.AADHAAR: "123456789012",
            C.ASSESSMENT_YEAR: "2024-25",
            C.GROSS_TOTAL_INCOME: "500000",
            C.TOTAL_INCOME: "500000",
            C.GROSS_TAX_LIABILITY: "0",
            C.NET_TAX_LIABILITY: "0",
            C.TAXES_PAID_TOTAL: "5000",
            C.TDS_TOTAL: "5000",
            C.REFUND_AMOUNT: "5000",
            C.ROUNDED_REFUND_AMOUNT: "5000",
        }
        for name, value in fields.items():
            ExtractedField.objects.create(
                document=doc,
                field_name=name,
                normalized_value=value,
            )

        ctx = build_computation_preview_context(doc)
        self.assertIsNotNone(ctx)
        assert ctx is not None
        self.assertTrue(ctx["preview_mode"])
        self.assertEqual(ctx["fields"][C.PAN], mask_pan("ABCDE1234F"))
        self.assertEqual(ctx["fields"][C.AADHAAR], mask_aadhaar("123456789012"))
        self.assertIn("slab_rows", ctx)
        self.assertIn("refund_display_rounded", ctx)

    def test_skips_uploaded_status(self) -> None:
        doc = Document.objects.create(
            original_filename="pending.json",
            status=Document.STATUS_UPLOADED,
        )
        self.assertIsNone(build_computation_preview_context(doc))
