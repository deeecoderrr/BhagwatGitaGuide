from django.contrib import admin

from apps.exports.models import ExportedSummary


@admin.register(ExportedSummary)
class ExportedSummaryAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "created_at", "expires_at", "pdf_purged_at")
