"""Retention / purge behavior for exported PDFs."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.documents.models import Document
from apps.exports.models import ExportedSummary
from apps.exports.retention import (
    delete_document_upload_after_export,
    purge_expired_exports,
)


class ExportRetentionTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            "u1",
            "u1@test.com",
            "password123456789012345678",
        )

    def test_can_download_until_expires_at(self) -> None:
        doc = Document.objects.create(
            user=self.user,
            uploaded_file=SimpleUploadedFile("x.json", b"{}"),
            original_filename="x.json",
            file_hash="ab",
            status=Document.STATUS_APPROVED,
        )
        future = timezone.now() + timedelta(hours=1)
        exp = ExportedSummary.objects.create(
            document=doc,
            expires_at=future,
        )
        exp.pdf_file.save(
            "ok.pdf",
            SimpleUploadedFile("ok.pdf", b"%PDF"),
            save=True,
        )
        self.assertTrue(exp.can_download())

    def test_can_download_false_after_expiry_even_before_purge(self) -> None:
        doc = Document.objects.create(
            user=self.user,
            uploaded_file=SimpleUploadedFile("y.json", b"{}"),
            original_filename="y.json",
            file_hash="cd",
            status=Document.STATUS_APPROVED,
        )
        past = timezone.now() - timedelta(minutes=1)
        exp = ExportedSummary.objects.create(
            document=doc,
            expires_at=past,
        )
        exp.pdf_file.save(
            "t.pdf",
            SimpleUploadedFile("t.pdf", b"%PDF"),
            save=True,
        )
        self.assertFalse(exp.can_download())

    def test_purge_clears_file_and_sets_pdf_purged_at(self) -> None:
        doc = Document.objects.create(
            user=self.user,
            uploaded_file=SimpleUploadedFile("z.json", b"{}"),
            original_filename="z.json",
            file_hash="ef",
            status=Document.STATUS_APPROVED,
        )
        past = timezone.now() - timedelta(hours=1)
        exp = ExportedSummary.objects.create(document=doc, expires_at=past)
        exp.pdf_file.save(
            "out.pdf",
            SimpleUploadedFile("out.pdf", b"%PDF-1"),
            save=True,
        )
        n = purge_expired_exports()
        self.assertEqual(n, 1)
        exp.refresh_from_db()
        self.assertIsNotNone(exp.pdf_purged_at)
        self.assertFalse(exp.can_download())

    @override_settings(ITR_DELETE_INPUT_AFTER_EXPORT=True)
    def test_delete_upload_clears_input_file(self) -> None:
        doc = Document.objects.create(
            user=self.user,
            uploaded_file=SimpleUploadedFile("in.json", b"{ }"),
            original_filename="in.json",
            file_hash="ff",
            status=Document.STATUS_APPROVED,
        )
        delete_document_upload_after_export(doc)
        doc.refresh_from_db()
        self.assertFalse(doc.uploaded_file)


class ItrExportTemplateTagsTests(TestCase):
    def test_itr_delete_input_after_export_matches_setting(self) -> None:
        tmpl = Template(
            "{% load itr_export %}"
            "{% itr_delete_input_after_export as x %}{% if x %}on{% else %}off{% endif %}"
        )
        with override_settings(ITR_DELETE_INPUT_AFTER_EXPORT=True):
            self.assertEqual(tmpl.render(Context({})), "on")
        with override_settings(ITR_DELETE_INPUT_AFTER_EXPORT=False):
            self.assertEqual(tmpl.render(Context({})), "off")
