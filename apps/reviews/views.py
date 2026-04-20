from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.documents.access import document_for_request
from apps.documents.models import Document, ExtractedField
from apps.extractors import canonical as C
from apps.reviews.field_labels import label_for
from apps.reviews.models import ReviewAction


def _grouped_fields(document: Document) -> list[tuple[str, list[ExtractedField]]]:
    fields = list(document.extracted_fields.all().order_by("field_name"))
    order = [
        ("Return header", C.HEADER_FIELDS),
        ("Personal details", C.PERSONAL_FIELDS),
        ("Income", C.INCOME_FIELDS),
        ("Tax", C.TAX_FIELDS),
    ]
    by_name = {f.field_name: f for f in fields}
    groups: list[tuple[str, list[ExtractedField]]] = []
    used: set[str] = set()
    for title, keys in order:
        row: list[ExtractedField] = []
        for k in keys:
            if k in by_name:
                row.append(by_name[k])
                used.add(k)
        if row:
            groups.append((title, row))
    rest = [f for f in fields if f.field_name not in used]
    if rest:
        groups.append(("Other", rest))
    return groups


@require_http_methods(["GET", "POST"])
def review_document(request, pk: int):
    document = document_for_request(request, pk)
    if document.status == Document.STATUS_FAILED:
        messages.warning(request, "Document processing failed; re-upload or reprocess.")
    if request.method == "POST":
        action = request.POST.get("action", "save")
        with transaction.atomic():
            for ef in document.extracted_fields.all():
                key = f"field_{ef.field_name}"
                if key not in request.POST:
                    continue
                new_val = request.POST.get(key, "").strip()
                old = ef.normalized_value or ""
                if new_val != old:
                    ReviewAction.objects.create(
                        document=document,
                        field_name=ef.field_name,
                        old_value=old,
                        new_value=new_val,
                        action_type=ReviewAction.ACTION_EDIT,
                        note="",
                    )
                    ef.normalized_value = new_val
                    ef.is_approved = True
                    ef.save(update_fields=["normalized_value", "is_approved"])
            if action == "approve":
                document.review_completed = True
                document.status = Document.STATUS_APPROVED
                document.save(update_fields=["review_completed", "status", "updated_at"])
                messages.success(
                    request,
                    "Review marked complete. Open the document page to generate the summary PDF.",
                )
                return redirect("documents:detail", pk=document.pk)
            messages.success(request, "Saved changes.")
        return redirect("reviews:review", pk=document.pk)

    grouped = _grouped_fields(document)
    return render(
        request,
        "reviews/review.html",
        {
            "document": document,
            "grouped_fields": grouped,
            "labels": {f.field_name: label_for(f.field_name) for f in document.extracted_fields.all()},
        },
    )
