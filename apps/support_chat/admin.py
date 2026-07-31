from django.contrib import admin
from django.utils.html import format_html

from apps.support_chat.models import SupportMessage, SupportThread


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ("sender", "is_staff", "body", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(SupportThread)
class SupportThreadAdmin(admin.ModelAdmin):
    list_display = (
        "last_message_at",
        "subject",
        "user",
        "status",
        "service_key",
        "created_at",
    )
    list_filter = ("status", "service_key", "created_at")
    search_fields = ("subject", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "last_message_at")
    list_editable = ("status",)
    inlines = [SupportMessageInline]
    raw_id_fields = ("user", "lead")

    @admin.display(description="Open in staff inbox")
    def staff_link(self, obj: SupportThread) -> str:
        from django.urls import reverse

        url = reverse("support_chat:staff_thread", kwargs={"pk": obj.pk})
        return format_html('<a href="{}">Reply in inbox</a>', url)


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "thread", "is_staff", "sender", "body_preview")
    list_filter = ("is_staff", "created_at")
    search_fields = ("body", "thread__subject", "sender__username")
    readonly_fields = ("created_at",)

    @admin.display(description="Message")
    def body_preview(self, obj: SupportMessage) -> str:
        return obj.body[:80]
