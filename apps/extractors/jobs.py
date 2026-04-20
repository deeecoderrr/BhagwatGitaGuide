"""RQ worker jobs — must stay at module scope for pickling."""
from __future__ import annotations


def process_document_job(document_id: int) -> None:
    """Run JSON import pipeline for a document (async worker)."""
    from apps.documents.models import Document
    from apps.extractors.pipeline import process_document_file

    doc = Document.objects.get(pk=document_id)
    process_document_file(doc)
