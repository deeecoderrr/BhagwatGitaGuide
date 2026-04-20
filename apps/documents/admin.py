from django.contrib import admin

from apps.documents.models import BankDetail, Document, ExtractedField, TDSDetail


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_filename",
        "upload_source",
        "detected_type",
        "status",
        "used_ocr_fallback",
        "native_text_char_count",
        "created_at",
    )
    list_filter = ("status", "detected_type", "upload_source", "used_ocr_fallback")
    search_fields = ("original_filename", "file_hash")


@admin.register(ExtractedField)
class ExtractedFieldAdmin(admin.ModelAdmin):
    list_display = ("document", "field_name", "normalized_value", "confidence_score")
    search_fields = ("field_name", "normalized_value")


@admin.register(BankDetail)
class BankDetailAdmin(admin.ModelAdmin):
    list_display = ("document", "bank_name", "ifsc", "account_number")


@admin.register(TDSDetail)
class TDSDetailAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "deductor_name",
        "tan_pan",
        "section",
        "head_of_income",
        "total_tax_deducted",
    )
