from django.contrib import admin

from apps.comments.models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "page_slug", "user", "parent_id", "created_at")
    list_filter = ("page_slug",)
    search_fields = ("body", "user__username")
    raw_id_fields = ("user", "parent")
