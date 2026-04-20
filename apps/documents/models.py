from __future__ import annotations

from django.conf import settings
from django.db import models


class Document(models.Model):
    """Uploaded filed ITR JSON and processing lifecycle."""

    STATUS_UPLOADED = "uploaded"
    STATUS_QUEUED = "queued"
    STATUS_CLASSIFYING = "classifying"
    STATUS_EXTRACTING = "extracting"
    STATUS_REVIEW_REQUIRED = "review_required"
    STATUS_APPROVED = "approved"
    STATUS_EXPORTED = "exported"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_CLASSIFYING, "Classifying"),
        (STATUS_EXTRACTING, "Extracting"),
        (STATUS_REVIEW_REQUIRED, "Review Required"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_EXPORTED, "Exported"),
        (STATUS_FAILED, "Failed"),
    ]

    TYPE_ITR1 = "ITR1"
    TYPE_ITR3 = "ITR3"
    TYPE_ITR4 = "ITR4"
    TYPE_UNKNOWN = "UNKNOWN"

    TYPE_CHOICES = [
        (TYPE_ITR1, "ITR-1"),
        (TYPE_ITR3, "ITR-3"),
        (TYPE_ITR4, "ITR-4"),
        (TYPE_UNKNOWN, "Unknown"),
    ]

    UPLOAD_PDF = "pdf"
    UPLOAD_JSON = "json"
    UPLOAD_SOURCE_CHOICES = [
        (UPLOAD_PDF, "PDF"),
        (UPLOAD_JSON, "JSON"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    uploaded_file = models.FileField(
        upload_to="itr_uploads/",
        blank=True,
        null=True,
        max_length=500,
    )
    upload_source = models.CharField(
        max_length=10,
        choices=UPLOAD_SOURCE_CHOICES,
        default=UPLOAD_JSON,
    )
    original_filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, db_index=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    detected_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default=TYPE_UNKNOWN, blank=True
    )
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default=STATUS_UPLOADED
    )
    error_message = models.TextField(blank=True)
    review_completed = models.BooleanField(default=False)
    native_text_char_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For JSON imports: UTF-8 source length in characters.",
    )
    used_ocr_fallback = models.BooleanField(
        default=False,
        help_text="Legacy: was OCR used on a PDF upload (retained for old rows).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_status_display()})"


class ExtractedField(models.Model):
    """Single canonical field with lineage for audit."""

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="extracted_fields"
    )
    field_name = models.CharField(max_length=100, db_index=True)
    raw_value = models.TextField(blank=True, null=True)
    normalized_value = models.TextField(blank=True, null=True)
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    page_number = models.PositiveIntegerField(null=True, blank=True)
    source_text = models.TextField(blank=True, null=True)
    source_bbox = models.JSONField(null=True, blank=True)
    extraction_method = models.CharField(max_length=64, blank=True, null=True)
    requires_review = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document", "field_name"],
                name="uniq_document_field_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.field_name}={self.normalized_value}"


class BankDetail(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="bank_details"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    ifsc = models.CharField(max_length=20, blank=True, null=True)
    account_number = models.CharField(max_length=64, blank=True, null=True)
    account_type = models.CharField(max_length=64, blank=True, null=True)
    nominate_for_refund = models.CharField(
        max_length=16,
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["sort_order", "id"]


class TDSDetail(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="tds_details"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    deductor_name = models.CharField(max_length=255, blank=True, null=True)
    tan_pan = models.CharField(max_length=32, blank=True, null=True)
    section = models.CharField(max_length=32, blank=True, null=True)
    amount_paid = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    total_tax_deducted = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    amount_claimed_this_year = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    carry_forward = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    head_of_income = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="e.g. Income from Other Sources (Schedule TDS2).",
    )

    class Meta:
        ordering = ["sort_order", "id"]
