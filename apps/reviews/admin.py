from django.contrib import admin

from apps.reviews.models import ReviewAction


@admin.register(ReviewAction)
class ReviewActionAdmin(admin.ModelAdmin):
    list_display = ("document", "field_name", "action_type", "created_at")
    list_filter = ("action_type",)
