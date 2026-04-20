from django.contrib import admin

from apps.accounts.models import QuotaSettings, UserProfile


@admin.register(QuotaSettings)
class QuotaSettingsAdmin(admin.ModelAdmin):
    list_display = ("free_exports_per_month",)

    def has_add_permission(self, request):
        return not QuotaSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "subscription_until", "exports_this_month")
    list_filter = ("plan",)
    raw_id_fields = ("user",)
