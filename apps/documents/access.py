"""Ownership checks for uploaded documents."""
from __future__ import annotations

from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.documents.models import Document


def document_for_user(user, pk: int) -> Document:
    doc = get_object_or_404(Document, pk=pk)
    if user.is_superuser:
        return doc
    if doc.user_id is None:
        raise Http404("Document not found.")
    if doc.user_id != user.id:
        raise Http404("Document not found.")
    return doc
