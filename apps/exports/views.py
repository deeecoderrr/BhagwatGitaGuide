from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Avg
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserProfile
from apps.accounts.services import can_export_pdf, record_export
from apps.documents.access import document_for_user
from apps.documents.models import Document
from apps.exports.models import ExportedSummary
from apps.exports.retention import (
    delete_document_upload_after_export,
    output_retention_hours,
    purge_expired_exports,
)
from apps.extractors import canonical as C
from apps.extractors.validation_engine import run_computation_validation
from apps.extractors.validators import (
    blocking_issues,
    coerce_refund_demand_field_map,
    validate_document_for_export,
)
from apps.reviews.field_labels import FIELD_LABELS


def _field_map(document: Document) -> dict[str, str]:
    return {
        f.field_name: (f.normalized_value or "").strip()
        for f in document.extracted_fields.all()
    }


def _single_line(s: str) -> str:
    """Collapse internal newlines/tabs so PDF cells don’t break names across lines."""
    return " ".join(s.split())


def _build_export_context(document: Document, fm: dict[str, str] | None = None) -> dict:
    fm = dict(fm if fm is not None else _field_map(document))
    if fm.get(C.ASSESSEE_NAME):
        fm[C.ASSESSEE_NAME] = _single_line(fm[C.ASSESSEE_NAME])
    for key in (C.REFUND_AMOUNT, C.DEMAND_AMOUNT):
        if key in fm:
            fm[key] = _single_line(fm[key])
    banks = list(document.bank_details.all())
    tds = list(document.tds_details.all())
    findings = run_computation_validation(
        fm,
        banks,
        tds,
        document.detected_type or "",
    )
    avg_conf = document.extracted_fields.filter(
        confidence_score__isnull=False
    ).aggregate(avg=Avg("confidence_score"))["avg"]
    ay = fm.get(C.ASSESSMENT_YEAR, "")
    title = f"Income & Tax Computation — A.Y. {ay}" if ay else "Income & Tax Computation"
    return {
        "document": document,
        "title": title,
        "fields": fm,
        "labels": FIELD_LABELS,
        "bank_rows": banks,
        "tds_rows": tds,
        "validation_findings": findings,
        "generated_at": timezone.now(),
        "extraction_confidence_avg": avg_conf,
    }


@login_required
@require_http_methods(["GET", "POST"])
def export_pdf(request, pk: int):
    purge_expired_exports()
    document = document_for_user(request.user, pk)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    fm = coerce_refund_demand_field_map(_field_map(document))
    issues = validate_document_for_export(
        document, fm, document.detected_type or Document.TYPE_UNKNOWN
    )
    blocks = blocking_issues(issues)
    allowed_export, export_reason = can_export_pdf(profile)

    if request.method == "POST":
        if blocks:
            for b in blocks:
                messages.error(request, b.message)
            return redirect("documents:detail", pk=pk)
        if not allowed_export:
            messages.error(request, export_reason)
            return redirect("marketing:pricing")
        try:
            ctx = _build_export_context(document, fm)
            try:
                from apps.exports.weasy_render import render_computation_weasy_pdf
            except (ImportError, OSError) as exc:
                messages.error(
                    request,
                    "WeasyPrint is not available (install OS libraries: Pango, cairo, GObject — "
                    f"see WeasyPrint docs). Details: {exc}",
                )
                return redirect("documents:detail", pk=pk)
            pdf_bytes = render_computation_weasy_pdf(ctx)
        except Exception as exc:
            messages.error(request, f"PDF failed: {exc}")
            return redirect("documents:detail", pk=pk)

        name = f"itr-summary-{document.pk}.pdf"
        exp = ExportedSummary.objects.create(
            document=document,
            expires_at=timezone.now()
            + timedelta(hours=output_retention_hours()),
        )
        exp.pdf_file.save(name, ContentFile(pdf_bytes), save=True)
        document.status = Document.STATUS_EXPORTED
        document.save(update_fields=["status", "updated_at"])
        record_export(profile)
        delete_document_upload_after_export(document)
        messages.success(request, "Summary PDF generated (WeasyPrint layout).")
        return redirect("exports:download", pk=document.pk, export_id=exp.pk)

    return render(
        request,
        "exports/export_confirm.html",
        {
            "document": document,
            "blocking": blocks,
            "warnings": [i for i in issues if i not in blocks],
            "export_blocked": not allowed_export,
            "export_block_reason": export_reason,
        },
    )


@login_required
@require_http_methods(["GET"])
def download_export(request, pk: int, export_id: int):
    purge_expired_exports()
    document = document_for_user(request.user, pk)
    exp = get_object_or_404(ExportedSummary, pk=export_id, document=document)
    if not exp.can_download():
        messages.error(
            request,
            "This export has expired or was removed. Generate a new PDF if needed.",
        )
        return redirect("documents:detail", pk=pk)
    if not exp.pdf_file:
        messages.error(request, "File missing.")
        return redirect("documents:detail", pk=pk)
    return FileResponse(
        exp.pdf_file.open("rb"),
        as_attachment=True,
        filename=exp.pdf_file.name.split("/")[-1],
    )
