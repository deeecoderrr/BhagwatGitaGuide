"""Ownership checks for uploaded documents."""
from __future__ import annotations

from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404

from apps.documents.models import Document
from apps.documents.session_docs import owns_anonymous_document


def document_for_user(user, pk: int) -> Document:
    doc = get_object_or_404(Document, pk=pk)
    if user.is_superuser:
        return doc
    if doc.user_id is None:
        raise Http404("Document not found.")
    if doc.user_id != user.id:
        raise Http404("Document not found.")
    return doc


def document_for_request(request: HttpRequest, pk: int) -> Document:
    """
    Resolve a document for the current session.

    - Logged-in users see their own rows; superuser sees any.
    - Anonymous users may only access ``user_id`` is None documents whose id
      was stored in session when created (beta try flow).
    - Logged-in users may access a session-bound anonymous doc (same browser)
      so the flow continues if they do not refresh before export.
    """
    doc = get_object_or_404(Document, pk=pk)
    user = request.user

    if user.is_authenticated:
        if getattr(user, "is_superuser", False):
            return doc
        if doc.user_id is not None and doc.user_id == user.id:
            return doc
        if doc.user_id is None and owns_anonymous_document(
            request.session, doc.pk
        ):
            return doc
        raise Http404("Document not found.")

    if doc.user_id is not None:
        raise Http404("Document not found.")
    if owns_anonymous_document(request.session, doc.pk):
        return doc
    raise Http404("Document not found.")
