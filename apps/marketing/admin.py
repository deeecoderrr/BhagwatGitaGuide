from django.contrib import admin

from apps.marketing.models import ServiceAppointmentLead


@admin.register(ServiceAppointmentLead)
class ServiceAppointmentLeadAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "name",
        "phone",
        "service_label",
        "status",
        "email_sent",
    )
    list_filter = ("status", "service_key", "email_sent", "created_at")
    search_fields = ("name", "phone", "email", "notes")
    readonly_fields = ("created_at",)
    list_editable = ("status",)
