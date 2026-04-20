from django.contrib import admin

from apps.billing.models import RazorpayOrder


@admin.register(RazorpayOrder)
class RazorpayOrderAdmin(admin.ModelAdmin):
    list_display = ("razorpay_order_id", "user", "status", "amount_paise", "created_at")
    list_filter = ("status", "currency")
    raw_id_fields = ("user",)
    readonly_fields = ("raw_payload", "created_at")
