"""Admin configuration for browsing verses, chats, and feedback."""

from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from guide_api.models import (
    AskEvent,
    Conversation,
    DailyAskUsage,
    EngagementEvent,
    FollowUpEvent,
    Message,
    RequestQuotaSettings,
    ResponseFeedback,
    SavedReflection,
    SupportTicket,
    UserEngagementProfile,
    UserSubscription,
    Verse,
)


@admin.register(Verse)
class VerseAdmin(admin.ModelAdmin):
    """Verse list and search tools in Django admin."""

    list_display = ("chapter", "verse")
    search_fields = ("chapter", "verse", "translation")


class MessageInline(admin.TabularInline):
    """Read-only inline messages under each conversation."""

    model = Message
    extra = 0
    readonly_fields = ("role", "content", "created_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Conversation list with nested message timeline."""

    list_display = ("id", "user_id", "created_at", "updated_at")
    search_fields = ("user_id",)
    inlines = [MessageInline]


@admin.register(ResponseFeedback)
class ResponseFeedbackAdmin(admin.ModelAdmin):
    """Feedback dashboard for response quality signals."""

    list_display = ("id", "user_id", "helpful", "response_mode", "created_at")
    list_filter = ("helpful", "response_mode", "mode")
    search_fields = ("user_id", "message", "note")


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    """Subscription plan management and entitlement checks."""

    list_display = ("user", "plan", "is_active", "updated_at")
    list_filter = ("plan", "is_active")
    search_fields = ("user__username", "user__email")


@admin.register(DailyAskUsage)
class DailyAskUsageAdmin(admin.ModelAdmin):
    """Daily ask counters for quota monitoring."""

    list_display = ("user", "date", "ask_count")
    list_filter = ("date",)
    search_fields = ("user__username",)


@admin.register(RequestQuotaSettings)
class RequestQuotaSettingsAdmin(admin.ModelAdmin):
    """Manage guest/free/pro limits and enable/disable toggles."""

    list_display = (
        "guest_limit_enabled",
        "guest_ask_limit",
        "free_limit_enabled",
        "free_daily_ask_limit",
        "pro_limit_enabled",
        "pro_daily_ask_limit",
        "updated_at",
    )

    def has_add_permission(self, request):
        """Keep this model singleton by allowing only one row."""
        if RequestQuotaSettings.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(AskEvent)
class AskEventAdmin(admin.ModelAdmin):
    """Ask event logs with lightweight conversion/quality summaries."""

    list_display = (
        "created_at",
        "user_id",
        "source",
        "mode",
        "outcome",
        "response_mode",
        "plan",
    )
    list_filter = ("source", "mode", "outcome", "response_mode", "plan")
    search_fields = ("user_id",)

    def changelist_view(self, request, extra_context=None):
        """Inject dashboard counters above ask event list."""
        now = timezone.now()
        today = timezone.localdate()
        window_7d = now - timedelta(days=7)
        qs = AskEvent.objects.all()
        served_7d = qs.filter(
            created_at__gte=window_7d,
            outcome=AskEvent.OUTCOME_SERVED,
        )
        served_7d_count = served_7d.count()
        fallback_7d_count = served_7d.filter(
            response_mode=AskEvent.RESPONSE_MODE_FALLBACK
        ).count()
        fallback_rate_7d = (
            (fallback_7d_count / served_7d_count) * 100
            if served_7d_count
            else 0.0
        )
        feedback_7d = ResponseFeedback.objects.filter(
            created_at__gte=window_7d
        )
        feedback_7d_count = feedback_7d.count()
        helpful_7d_count = feedback_7d.filter(helpful=True).count()
        helpful_rate_7d = (
            (helpful_7d_count / feedback_7d_count) * 100
            if feedback_7d_count
            else 0.0
        )
        quota_blocks_7d = qs.filter(
            created_at__gte=window_7d,
            outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
        ).count()
        context = {
            "analytics_summary": {
                "asks_today": qs.filter(
                    created_at__date=today,
                    outcome=AskEvent.OUTCOME_SERVED,
                ).count(),
                "asks_7d": served_7d_count,
                "fallback_rate_7d": round(fallback_rate_7d, 1),
                "helpful_rate_7d": round(helpful_rate_7d, 1),
                "quota_blocks_7d": quota_blocks_7d,
            }
        }
        if extra_context:
            context.update(extra_context)
        return super().changelist_view(request, extra_context=context)


@admin.register(SavedReflection)
class SavedReflectionAdmin(admin.ModelAdmin):
    """Manage saved reflections/bookmarks for retention workflows."""

    list_display = ("id", "user", "conversation", "created_at")
    search_fields = ("user__username", "message", "guidance", "note")
    list_filter = ("created_at",)


@admin.register(FollowUpEvent)
class FollowUpEventAdmin(admin.ModelAdmin):
    """Inspect follow-up prompt shown/clicked event stream."""

    list_display = (
        "created_at",
        "user_id",
        "source",
        "event_type",
        "intent",
        "mode",
    )
    list_filter = ("source", "event_type", "intent", "mode")
    search_fields = ("user_id", "prompt")


@admin.register(UserEngagementProfile)
class UserEngagementProfileAdmin(admin.ModelAdmin):
    """Inspect streak and reminder preferences by user."""

    list_display = (
        "user",
        "daily_streak",
        "last_active_date",
        "reminder_enabled",
        "preferred_channel",
        "timezone",
    )
    list_filter = ("reminder_enabled", "preferred_channel", "timezone")
    search_fields = ("user__username", "user__email")


@admin.register(EngagementEvent)
class EngagementEventAdmin(admin.ModelAdmin):
    """Review streak/reminder change analytics stream."""

    list_display = ("created_at", "user", "event_type")
    list_filter = ("event_type",)
    search_fields = ("user__username",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """Support request queue for payment/account/user issue handling."""

    list_display = (
        "id",
        "issue_type",
        "name",
        "email",
        "status",
        "created_at",
    )
    list_filter = ("issue_type", "status", "created_at")
    search_fields = ("name", "email", "requester_id", "message")
