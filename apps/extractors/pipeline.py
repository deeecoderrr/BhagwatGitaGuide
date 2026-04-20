"""Import pipeline: filed ITR JSON only."""
from __future__ import annotations

from pathlib import Path

from apps.documents.models import Document
from apps.extractors.json_pipeline import process_json_document_file


def process_document_file(document: Document) -> None:
    """Parse uploaded JSON via ``process_json_document_file``. PDF uploads are not supported."""
    path = Path(document.uploaded_file.path)
    if path.suffix.lower() != ".json":
        document.status = Document.STATUS_FAILED
        document.error_message = (
            "Only filed ITR JSON (.json) is supported. Upload the acknowledgment / utility JSON export."
        )
        document.save(update_fields=["status", "error_message", "updated_at"])
        return
    process_json_document_file(document)
