from django.contrib import admin

from apps.analytics.models import GrowthEvent, VisitorProfile


@admin.register(VisitorProfile)
class VisitorProfileAdmin(admin.ModelAdmin):
    list_display = ("visitor_id", "user", "visit_count", "first_utm_source", "last_seen_at")
    list_filter = ("first_utm_source",)
    search_fields = ("visitor_id", "first_utm_campaign")
    raw_id_fields = ("user",)
    readonly_fields = ("first_seen_at", "last_seen_at")


@admin.register(GrowthEvent)
class GrowthEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "visitor_id", "path", "created_at")
    list_filter = ("event_type",)
    search_fields = ("visitor_id", "path")
    readonly_fields = ("metadata", "created_at")
