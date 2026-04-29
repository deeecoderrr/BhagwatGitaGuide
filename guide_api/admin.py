"""Admin configuration for browsing verses, chats, and feedback."""

import csv
from datetime import timedelta

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone

from guide_api.models import (
    AskEvent,
    BillingRecord,
    CommunityPost,
    Conversation,
    DailyAskUsage,
    EngagementEvent,
    FollowUpEvent,
    GrowthEvent,
    Message,
    PracticeTag,
    PracticeWorkflow,
    PracticeWorkflowEnrollment,
    PracticeWorkflowStep,
    RequestQuotaSettings,
    ResponseFeedback,
    SadhanaDay,
    SadhanaDayCompletion,
    SadhanaEnrollment,
    SadhanaProgram,
    SadhanaStep,
    SavedReflection,
    SharedAnswer,
    SupportTicket,
    UserEngagementProfile,
    UserGitaSequenceJourney,
    UserSubscription,
    Verse,
    WebAudienceProfile,
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


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    """Moderate public path threads."""

    list_display = (
        "id",
        "author",
        "parent",
        "body_preview",
        "created_at",
        "deleted_at",
    )
    list_filter = ("deleted_at",)
    search_fields = ("body", "author__username")
    raw_id_fields = ("author", "parent")
    readonly_fields = ("created_at", "updated_at", "edited_at")

    def body_preview(self, obj: CommunityPost) -> str:
        """Truncate body for compact admin rows."""
        text = (obj.body or "").strip().replace("\n", " ")
        return text[:80] + ("…" if len(text) > 80 else "")


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


@admin.action(description="Export selected billing rows as CSV")
def export_billing_records_csv(modeladmin, request, queryset):
    """Download an invoice-friendly CSV from selected billing rows."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="billing-records-export.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "created_at",
            "updated_at",
            "billing_name",
            "billing_email",
            "business_name",
            "gstin",
            "billing_country_code",
            "billing_country_name",
            "billing_state",
            "billing_city",
            "billing_postal_code",
            "billing_address",
            "plan",
            "tax_treatment",
            "payment_status",
            "is_international",
            "currency",
            "amount_minor",
            "amount_major",
            "razorpay_order_id",
            "razorpay_payment_id",
            "payment_method",
            "invoice_reference",
            "verified_at",
            "paid_at",
            "user_id",
            "username",
        ]
    )
    for record in queryset.order_by("-created_at"):
        writer.writerow(
            [
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                record.billing_name,
                record.billing_email,
                record.business_name,
                record.gstin,
                record.billing_country_code,
                record.billing_country_name,
                record.billing_state,
                record.billing_city,
                record.billing_postal_code,
                record.billing_address,
                record.plan,
                record.tax_treatment,
                record.payment_status,
                "yes" if record.is_international else "no",
                record.currency,
                record.amount_minor,
                record.amount_major,
                record.razorpay_order_id,
                record.razorpay_payment_id,
                record.payment_method,
                record.invoice_reference,
                record.verified_at.isoformat() if record.verified_at else "",
                record.paid_at.isoformat() if record.paid_at else "",
                record.user_id or "",
                record.user.username if record.user else "",
            ]
        )
    return response


@admin.register(BillingRecord)
class BillingRecordAdmin(admin.ModelAdmin):
    """Invoice export ledger for domestic and export SaaS payments."""

    list_display = (
        "created_at",
        "billing_name",
        "billing_email",
        "plan",
        "tax_treatment",
        "payment_status",
        "currency",
        "amount_major",
        "billing_country_code",
        "razorpay_order_id",
    )
    list_filter = (
        "payment_status",
        "plan",
        "tax_treatment",
        "currency",
        "billing_country_code",
    )
    search_fields = (
        "billing_name",
        "billing_email",
        "business_name",
        "gstin",
        "razorpay_order_id",
        "razorpay_payment_id",
        "user__username",
        "user__email",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "verified_at",
        "paid_at",
        "raw_order_payload",
        "raw_payment_payload",
        "metadata",
    )
    actions = [export_billing_records_csv]


@admin.register(DailyAskUsage)
class DailyAskUsageAdmin(admin.ModelAdmin):
    """Daily ask counters for quota monitoring."""

    list_display = ("user", "date", "ask_count")
    list_filter = ("date",)
    search_fields = ("user__username",)


@admin.register(RequestQuotaSettings)
class RequestQuotaSettingsAdmin(admin.ModelAdmin):
    """Manage all plan quota controls from a single admin screen."""

    list_display = (
        "guest_limit_enabled",
        "guest_ask_limit",
        "free_limit_enabled",
        "free_daily_ask_limit",
        "free_monthly_ask_limit",
        "free_deep_mode_enabled",
        "plus_limit_enabled",
        "plus_daily_ask_limit",
        "plus_monthly_ask_limit",
        "plus_deep_monthly_limit",
        "pro_limit_enabled",
        "pro_daily_ask_limit",
        "pro_monthly_ask_limit",
        "pro_deep_monthly_limit",
        "updated_at",
    )
    fieldsets = (
        (
            "Guest",
            {
                "fields": (
                    "guest_limit_enabled",
                    "guest_ask_limit",
                ),
            },
        ),
        (
            "Free",
            {
                "fields": (
                    "free_limit_enabled",
                    "free_daily_ask_limit",
                    "free_monthly_ask_limit",
                    "free_deep_mode_enabled",
                ),
            },
        ),
        (
            "Plus",
            {
                "fields": (
                    "plus_limit_enabled",
                    "plus_daily_ask_limit",
                    "plus_monthly_ask_limit",
                    "plus_deep_monthly_limit",
                ),
                "description": "Set plus_limit_enabled=False for unlimited daily plus asks.",
            },
        ),
        (
            "Pro",
            {
                "fields": (
                    "pro_limit_enabled",
                    "pro_daily_ask_limit",
                    "pro_monthly_ask_limit",
                    "pro_deep_monthly_limit",
                ),
                "description": "Set pro_limit_enabled=False for unlimited daily pro asks.",
            },
        ),
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
        served_all = qs.filter(outcome=AskEvent.OUTCOME_SERVED)
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
        growth_7d = GrowthEvent.objects.filter(created_at__gte=window_7d)
        landing_7d = growth_7d.filter(
            event_type=GrowthEvent.EVENT_LANDING_VIEW,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        starter_7d = growth_7d.filter(
            event_type=GrowthEvent.EVENT_STARTER_CLICK,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        share_7d = growth_7d.filter(
            event_type=GrowthEvent.EVENT_SHARE_CLICK,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        ask_submit_7d = growth_7d.filter(
            event_type=GrowthEvent.EVENT_ASK_SUBMIT,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()

        source_counts = {}
        for profile in WebAudienceProfile.objects.exclude(first_utm_source=""):
            source = profile.first_utm_source
            source_counts[source] = source_counts.get(source, 0) + 1
        top_sources = [
            {"source": source, "count": count}
            for source, count in sorted(
                source_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ]

        context = {
            "analytics_summary": {
                "unique_visitors_total": WebAudienceProfile.objects.count(),
                "unique_users_used_total": served_all.values(
                    "user_id"
                ).distinct().count(),
                "queries_fired_total": qs.count(),
                "queries_served_total": served_all.count(),
                "asks_today": qs.filter(
                    created_at__date=today,
                    outcome=AskEvent.OUTCOME_SERVED,
                ).count(),
                "asks_7d": served_7d_count,
                "fallback_rate_7d": round(fallback_rate_7d, 1),
                "helpful_rate_7d": round(helpful_rate_7d, 1),
                "quota_blocks_7d": quota_blocks_7d,
                "landing_views_7d": landing_7d,
                "starter_clicks_7d": starter_7d,
                "share_clicks_7d": share_7d,
                "ask_submits_7d": ask_submit_7d,
                "starter_click_rate_7d": round(
                    (starter_7d / landing_7d * 100)
                    if landing_7d
                    else 0.0,
                    1,
                ),
                "ask_submit_rate_7d": round(
                    (ask_submit_7d / landing_7d * 100)
                    if landing_7d
                    else 0.0,
                    1,
                ),
                "top_sources": top_sources,
            }
        }
        if extra_context:
            context.update(extra_context)
        return super().changelist_view(request, extra_context=context)


@admin.register(GrowthEvent)
class GrowthEventAdmin(admin.ModelAdmin):
    """Inspect frontend funnel events for conversion analysis."""

    list_display = (
        "created_at",
        "event_type",
        "source",
        "audience_id",
        "path",
    )
    list_filter = ("event_type", "source", "created_at")
    search_fields = ("audience_id", "path")


@admin.register(WebAudienceProfile)
class WebAudienceProfileAdmin(admin.ModelAdmin):
    """Track unique web audience and revisit heartbeat in admin."""

    list_display = (
        "audience_id",
        "is_authenticated",
        "visit_count",
        "first_source",
        "last_source",
        "first_utm_source",
        "last_seen_at",
    )
    list_filter = (
        "is_authenticated",
        "first_source",
        "last_source",
        "first_utm_source",
        "last_seen_at",
    )
    search_fields = ("audience_id", "last_path", "first_utm_source")


@admin.register(SavedReflection)
class SavedReflectionAdmin(admin.ModelAdmin):
    """Manage saved reflections/bookmarks for retention workflows."""

    list_display = ("id", "user", "conversation", "created_at")
    search_fields = ("user__username", "message", "guidance", "note")
    list_filter = ("created_at",)


@admin.register(SharedAnswer)
class SharedAnswerAdmin(admin.ModelAdmin):
    """Inspect shareable answer cards generated from chat responses."""

    list_display = ("share_id", "language", "user_id", "created_at")
    search_fields = ("question", "guidance", "user_id")
    list_filter = ("language", "created_at")
    readonly_fields = ("share_id", "created_at")


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
        "last_reminder_push_date",
    )
    list_filter = ("reminder_enabled", "preferred_channel", "timezone")
    search_fields = ("user__username", "user__email")


@admin.register(EngagementEvent)
class EngagementEventAdmin(admin.ModelAdmin):
    """Review streak/reminder change analytics stream."""

    list_display = ("created_at", "user", "event_type")
    list_filter = ("event_type",)
    search_fields = ("user__username",)


@admin.action(description="Mark selected tickets as In Progress")
def mark_tickets_in_progress(modeladmin, request, queryset):
    queryset.update(status="in_progress")


@admin.action(description="Mark selected tickets as Resolved")
def mark_tickets_resolved(modeladmin, request, queryset):
    queryset.update(status="resolved")


@admin.action(description="Mark selected tickets as Closed")
def mark_tickets_closed(modeladmin, request, queryset):
    queryset.update(status="closed")


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
    date_hierarchy = "created_at"
    actions = [mark_tickets_in_progress, mark_tickets_resolved, mark_tickets_closed]


class SadhanaStepInline(admin.TabularInline):
    model = SadhanaStep
    extra = 0
    fields = (
        "sequence",
        "step_type",
        "title",
        "duration_minutes",
        "safety_tier",
        "requires_standing",
        "audio_url",
        "video_url",
    )
    show_change_link = True


class SadhanaDayInline(admin.TabularInline):
    model = SadhanaDay
    extra = 0
    show_change_link = True


@admin.register(PracticeTag)
class PracticeTagAdmin(admin.ModelAdmin):
    list_display = ("label", "slug", "category", "sort_order")
    list_filter = ("category",)
    search_fields = ("slug", "label")
    ordering = ("sort_order", "slug")
    prepopulated_fields = {"slug": ("label",)}


class PracticeWorkflowStepInline(admin.TabularInline):
    model = PracticeWorkflowStep
    extra = 0
    autocomplete_fields = ("tags",)
    fields = (
        "sequence",
        "step_type",
        "title",
        "duration_minutes",
        "safety_tier",
        "requires_standing",
        "audio_url",
        "video_url",
        "tags",
    )
    show_change_link = True


@admin.register(PracticeWorkflow)
class PracticeWorkflowAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "access_mode",
        "is_featured",
        "is_published",
        "purchase_price_minor_inr",
        "purchase_price_minor_usd",
        "sort_order",
    )
    list_filter = ("access_mode", "is_published", "is_featured")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("sort_order", "title")
    inlines = [PracticeWorkflowStepInline]


@admin.register(PracticeWorkflowStep)
class PracticeWorkflowStepAdmin(admin.ModelAdmin):
    list_display = ("workflow", "sequence", "step_type", "title", "duration_minutes")
    list_filter = ("step_type", "safety_tier")
    search_fields = ("title", "instructions", "workflow__slug")
    ordering = ("workflow", "sequence")
    raw_id_fields = ("workflow",)
    autocomplete_fields = ("tags",)


@admin.register(PracticeWorkflowEnrollment)
class PracticeWorkflowEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "workflow", "access_starts_at", "access_ends_at", "billing_record")
    list_filter = ("workflow",)
    search_fields = ("user__username", "workflow__slug")
    raw_id_fields = ("user", "workflow", "billing_record")


@admin.register(SadhanaProgram)
class SadhanaProgramAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "duration_days", "is_published", "sort_order")
    list_filter = ("is_published",)
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SadhanaDayInline]


@admin.register(SadhanaDay)
class SadhanaDayAdmin(admin.ModelAdmin):
    list_display = ("program", "day_number", "title")
    list_filter = ("program",)
    search_fields = ("title", "summary")
    ordering = ("program", "day_number")
    inlines = [SadhanaStepInline]


@admin.register(SadhanaStep)
class SadhanaStepAdmin(admin.ModelAdmin):
    list_display = ("day", "sequence", "step_type", "title", "duration_minutes", "safety_tier")
    list_filter = ("step_type", "safety_tier")
    search_fields = ("title", "instructions")
    ordering = ("day", "sequence")
    raw_id_fields = ("day",)
    fieldsets = (
        (None, {"fields": ("day", "sequence", "step_type", "title", "instructions")}),
        ("Media", {"fields": ("audio_url", "video_url", "duration_minutes", "primary_media_readonly")}),
        ("Follow-along", {"fields": ("subtitle_tracks", "timed_cues")}),
        ("Safety / UX", {"fields": ("safety_tier", "requires_standing")}),
    )
    readonly_fields = ("primary_media_readonly",)

    @admin.display(description="Primary media (computed)")
    def primary_media_readonly(self, obj: SadhanaStep) -> str:
        a = bool((obj.audio_url or "").strip())
        v = bool((obj.video_url or "").strip())
        if a and v:
            return "both"
        if v:
            return "video"
        if a:
            return "audio"
        return "none"


@admin.register(SadhanaEnrollment)
class SadhanaEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "program", "access_starts_at", "access_ends_at", "renewal_count")
    list_filter = ("program",)
    search_fields = ("user__username", "program__slug")
    raw_id_fields = ("user", "billing_record")


@admin.register(SadhanaDayCompletion)
class SadhanaDayCompletionAdmin(admin.ModelAdmin):
    list_display = ("day", "enrollment", "user", "completed_at")
    raw_id_fields = ("enrollment", "user", "day")


@admin.register(UserGitaSequenceJourney)
class UserGitaSequenceJourneyAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "next_chapter", "next_verse", "started_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("user__username", "intention_text")
    raw_id_fields = ("user",)
