from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.documents.access import document_for_request, document_for_user
from apps.documents.forms import DocumentReprocessForm, ItrUploadForm
from apps.documents.models import Document
from apps.exports.models import ExportedSummary
from apps.exports.retention import purge_expired_exports
from apps.documents.session_docs import (
    anonymous_document_count,
    register_anonymous_document,
)
from apps.extractors.queue import schedule_document_processing


def _should_poll_status(document: Document) -> bool:
    return document.status in (
        Document.STATUS_QUEUED,
        Document.STATUS_CLASSIFYING,
        Document.STATUS_EXTRACTING,
    )


def _document_queryset(request):
    qs = Document.objects.all().order_by("-created_at")
    if request.user.is_superuser:
        return qs[:100]
    return qs.filter(user=request.user)[:100]


@login_required
@require_http_methods(["GET", "POST"])
def document_list(request):
    purge_expired_exports()
    qs = _document_queryset(request)
    docs = qs.prefetch_related(
        Prefetch(
            "exports",
            queryset=ExportedSummary.objects.order_by("-created_at"),
        ),
    )
    return render(request, "documents/list.html", {"documents": docs})


@login_required
@require_http_methods(["GET", "POST"])
def document_upload(request):
    form = ItrUploadForm()
    max_bytes = getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 25 * 1024 * 1024)

    if request.method == "POST":
        form = ItrUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["file"]
            if hasattr(f, "size") and f.size and f.size > max_bytes:
                form.add_error("file", "File too large.")
            else:
                doc = Document(
                    user=request.user,
                    uploaded_file=f,
                    original_filename=getattr(f, "name", "upload.json"),
                    file_hash="pending",
                    status=Document.STATUS_UPLOADED,
                    upload_source=Document.UPLOAD_JSON,
                )
                doc.save()
                queued = schedule_document_processing(doc)
                if queued:
                    messages.info(
                        request,
                        "JSON uploaded. Import is running in the background; this page will update when ready.",
                    )
                return redirect("documents:detail", pk=doc.pk)

    return render(request, "documents/upload.html", {"form": form})


@require_http_methods(["GET"])
def document_detail(request, pk: int):
    doc = document_for_request(request, pk)
    reprocess = DocumentReprocessForm()
    return render(
        request,
        "documents/detail.html",
        {
            "document": doc,
            "reprocess_form": reprocess,
            "poll_status": _should_poll_status(doc),
        },
    )


@require_http_methods(["GET"])
def document_status(request: HttpRequest, pk: int) -> HttpResponse:
    """HTMX fragment: refreshed status while import runs."""
    doc = document_for_request(request, pk)
    if request.headers.get("HX-Request") != "true":
        raise Http404()
    return render(
        request,
        "documents/_doc_status.html",
        {
            "document": doc,
            "poll_status": _should_poll_status(doc),
        },
    )


@require_http_methods(["POST"])
def document_reprocess(request, pk: int):
    doc = document_for_request(request, pk)
    if not doc.uploaded_file:
        messages.error(
            request,
            "Original upload was removed after export. Upload the JSON again to re-import.",
        )
        return redirect("documents:detail", pk=pk)
    form = DocumentReprocessForm(request.POST)
    if form.is_valid():
        doc.status = Document.STATUS_UPLOADED
        doc.save(update_fields=["status", "updated_at"])
        queued = schedule_document_processing(doc)
        if queued:
            messages.info(request, "Re-import queued; refresh or wait for status updates.")
        else:
            messages.success(request, "Re-import finished.")
    return redirect("documents:detail", pk=pk)


@require_http_methods(["GET", "POST"])
def beta_try_upload(request: HttpRequest) -> HttpResponse:
    """
    Beta-only: anonymous upload from marketing home → import → review → export.

    Binds the new document to this browser session (no account).
    """
    if not getattr(settings, "ITR_BETA_RELEASE", False):
        raise Http404()
    beta_home = reverse("marketing:home") + "#beta-try"

    if request.method == "GET":
        return redirect(beta_home)

    form = ItrUploadForm(request.POST, request.FILES)
    max_bytes = getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 25 * 1024 * 1024)
    max_anon = getattr(settings, "ITR_ANONYMOUS_MAX_DOCS_PER_SESSION", 8)

    if not form.is_valid():
        for _field, errs in form.errors.items():
            for err in errs:
                messages.error(request, str(err))
        return redirect(beta_home)

    upload = form.cleaned_data["file"]
    if hasattr(upload, "size") and upload.size and upload.size > max_bytes:
        messages.error(request, "File too large.")
        return redirect(beta_home)

    if anonymous_document_count(request.session) >= max_anon:
        messages.error(
            request,
            f"Too many open tries in this browser (limit {max_anon}). "
            "Create a free account for a workspace, or clear old sessions.",
        )
        return redirect(beta_home)

    doc = Document(
        user=None,
        uploaded_file=upload,
        original_filename=getattr(upload, "name", "upload.json"),
        file_hash="pending",
        status=Document.STATUS_UPLOADED,
        upload_source=Document.UPLOAD_JSON,
    )
    doc.save()
    register_anonymous_document(request.session, doc.pk)

    queued = schedule_document_processing(doc)
    if queued:
        messages.info(
            request,
            "JSON received. Import is running in the background—this page updates when ready. "
            "Then review fields and approve before generating the PDF.",
        )
    else:
        messages.info(
            request,
            "JSON imported. Review the extracted fields and approve before generating the PDF.",
        )
    return redirect("documents:detail", pk=doc.pk)
