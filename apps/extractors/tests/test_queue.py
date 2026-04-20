from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.documents.models import Document
from apps.extractors.queue import schedule_document_processing


class ScheduleDocumentProcessingTests(TestCase):
    def setUp(self) -> None:
        uploaded = SimpleUploadedFile("x.json", b"{}", content_type="application/json")
        self.doc = Document.objects.create(
            uploaded_file=uploaded,
            original_filename="x.json",
            file_hash="ab" * 32,
            upload_source=Document.UPLOAD_JSON,
        )

    @override_settings(ITR_ASYNC_EXTRACTION=False)
    @patch("apps.extractors.queue.process_document_file")
    def test_sync_when_async_disabled(self, mock_process: MagicMock) -> None:
        queued = schedule_document_processing(self.doc)
        self.assertFalse(queued)
        mock_process.assert_called_once()

    @override_settings(ITR_ASYNC_EXTRACTION=True)
    @patch("django_rq.get_queue")
    @patch("apps.extractors.queue.process_document_file")
    def test_queues_when_async_and_rq_ok(
        self, mock_process: MagicMock, mock_get_queue: MagicMock
    ) -> None:
        q = MagicMock()
        mock_get_queue.return_value = q
        queued = schedule_document_processing(self.doc)
        self.assertTrue(queued)
        q.enqueue.assert_called_once()
        mock_process.assert_not_called()
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.STATUS_QUEUED)

    @override_settings(ITR_ASYNC_EXTRACTION=True)
    @patch("django_rq.get_queue", side_effect=ConnectionError("no redis"))
    @patch("apps.extractors.queue.process_document_file")
    def test_fallback_sync_on_enqueue_failure(
        self, mock_process: MagicMock, _mock_get_queue: MagicMock
    ) -> None:
        queued = schedule_document_processing(self.doc)
        self.assertFalse(queued)
        mock_process.assert_called_once()
