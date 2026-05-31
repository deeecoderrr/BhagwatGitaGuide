from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Avg
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserProfile
from apps.accounts.services import (
    can_export_pdf,
    can_export_pdf_anonymous,
    get_plan_status,
    record_export,
    record_export_anonymous,
)
from apps.documents.access import document_for_request
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


def _validate_guest_token(token: str, pk: int):
    """Return the unused GuestOrder if the token is valid and for this doc, else None."""
    from django.core import signing
    from apps.billing.models import GuestOrder
    try:
        data = signing.loads(token, salt="itr-guest-export", max_age=86400)
        if str(data.get("doc")) != str(pk):
            return None
        return GuestOrder.objects.filter(
            pk=data.get("go"),
            status=GuestOrder.STATUS_PAID,
            export_used=False,
        ).first()
    except Exception:
        return None


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


@require_http_methods(["GET", "POST"])
def export_pdf(request, pk: int):
    purge_expired_exports()
    document = document_for_request(request, pk)
    fm = coerce_refund_demand_field_map(_field_map(document))
    issues = validate_document_for_export(
        document, fm, document.detected_type or Document.TYPE_UNKNOWN
    )
    blocks = blocking_issues(issues)
    profile = None
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        allowed_export, export_reason = can_export_pdf(profile)
    else:
        allowed_export, export_reason = can_export_pdf_anonymous(request)

    # Guest token: valid signed URL grants access for 24 h regardless of session.
    guest_token = request.GET.get("guest_token", "") or request.POST.get("guest_token", "")
    guest_order_from_token = None
    if not allowed_export and not request.user.is_authenticated and guest_token:
        go = _validate_guest_token(guest_token, pk)
        if go:
            guest_order_from_token = go
            allowed_export = True
            export_reason = ""

    if request.method == "POST":
        if blocks:
            for b in blocks:
                messages.error(request, b.message)
            return redirect("documents:detail", pk=pk)
        if not allowed_export:
            messages.error(request, export_reason)
            if request.user.is_authenticated:
                return redirect("marketing:pricing")
            return redirect("documents:detail", pk=pk)
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
        if profile is not None:
            record_export(profile)
        else:
            record_export_anonymous(request)
            # If access was granted via a signed token, mark the order as used.
            if guest_order_from_token:
                guest_order_from_token.export_used = True
                guest_order_from_token.save(update_fields=["export_used"])
        delete_document_upload_after_export(document)
        # Serve PDF bytes directly — avoids cross-machine FileNotFoundError
        # (Fly.io round-robin can route the redirect to a different machine).
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    plan_status = None
    if profile is not None:
        plan_status = get_plan_status(profile)

    from apps.billing.views import _razorpay_client
    from django.urls import reverse
    razorpay_available = _razorpay_client() is not None
    user_email = request.user.email if request.user.is_authenticated else ""

    # Auto-export: if arriving from payment success with auto=1 and valid token,
    # skip the confirmation page and immediately generate the PDF.
    auto_export = request.GET.get("auto") == "1"
    if auto_export and allowed_export and not blocks:
        # Simulate POST to generate PDF immediately
        try:
            ctx = _build_export_context(document, fm)
            try:
                from apps.exports.weasy_render import render_computation_weasy_pdf
            except (ImportError, OSError) as exc:
                messages.error(
                    request,
                    f"WeasyPrint is not available: {exc}",
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
        if profile is not None:
            record_export(profile)
        else:
            record_export_anonymous(request)
            if guest_order_from_token:
                guest_order_from_token.export_used = True
                guest_order_from_token.save(update_fields=["export_used"])
        delete_document_upload_after_export(document)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    return render(
        request,
        "exports/export_confirm.html",
        {
            "document": document,
            "blocking": blocks,
            "warnings": [i for i in issues if i not in blocks],
            "export_blocked": not allowed_export,
            "export_block_reason": export_reason,
            "plan_status": plan_status,
            "contact_email": getattr(
                __import__("django.conf", fromlist=["settings"]).settings,
                "ITR_CONTACT_EMAIL",
                "support@askbhagavadgita.in",
            ),
            "razorpay_available": razorpay_available,
            "user_email": user_email,
            "guest_token": request.GET.get("guest_token", ""),
            "guest_init_url": reverse("billing:guest_checkout_init"),
            "guest_success_url": reverse("billing:guest_payment_success"),
            "auth_init_url": reverse("billing:checkout_bundle_init", kwargs={"bundle": "payg"}),
            "auth_success_url": reverse("billing:payment_success"),
        },
    )


@require_http_methods(["GET"])
def download_export(request, pk: int, export_id: int):
    purge_expired_exports()
    document = document_for_request(request, pk)
    exp = get_object_or_404(ExportedSummary, pk=export_id, document=document)
    if not exp.can_download():
        messages.error(
            request,
            "This export has expired or was removed. Generate a new PDF if needed.",
        )
        return redirect("documents:detail", pk=pk)
    if not exp.pdf_file:
        messages.error(request, "File missing. Please generate a new PDF.")
        return redirect("documents:detail", pk=pk)
    try:
        file_obj = exp.pdf_file.open("rb")
    except (FileNotFoundError, OSError):
        messages.error(
            request,
            "PDF file no longer available on the server (this can happen after a server restart). "
            "Please generate a new PDF.",
        )
        return redirect("exports:create", pk=pk)
    return FileResponse(
        file_obj,
        as_attachment=True,
        filename=exp.pdf_file.name.split("/")[-1],
    )
