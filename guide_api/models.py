"""Core database models for verses, chats, and feedback."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Verse(models.Model):
    """A Bhagavad Gita verse with optional themes and embedding vector."""

    chapter = models.PositiveIntegerField()
    verse = models.PositiveIntegerField()
    translation = models.TextField()
    commentary = models.TextField(blank=True)
    themes = models.JSONField(default=list, blank=True)
    embedding = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["chapter", "verse"]
        constraints = [
            models.UniqueConstraint(
                fields=["chapter", "verse"],
                name="unique_chapter_verse",
            )
        ]

    def __str__(self) -> str:
        """Human-friendly reference shown in admin and logs."""
        return f"{self.chapter}.{self.verse}"


class VerseSynthesis(models.Model):
    """Cached multilingual synthesis for a verse across meanings and commentaries."""

    SOURCE_LLM = "llm"
    SOURCE_FALLBACK = "fallback"
    SOURCE_CHOICES = (
        (SOURCE_LLM, "LLM"),
        (SOURCE_FALLBACK, "Fallback"),
    )

    verse = models.OneToOneField(
        Verse,
        on_delete=models.CASCADE,
        related_name="synthesis",
    )
    source_hash = models.CharField(max_length=64, blank=True, db_index=True)
    generation_source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_FALLBACK,
    )
    overview_en = models.TextField(blank=True)
    overview_hi = models.TextField(blank=True)
    commentary_consensus_en = models.TextField(blank=True)
    commentary_consensus_hi = models.TextField(blank=True)
    life_application_en = models.TextField(blank=True)
    life_application_hi = models.TextField(blank=True)
    key_points_en = models.JSONField(default=list, blank=True)
    key_points_hi = models.JSONField(default=list, blank=True)
    embedding = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["verse__chapter", "verse__verse"]

    def __str__(self) -> str:
        """Human-friendly verse synthesis reference."""
        return f"Synthesis {self.verse.chapter}.{self.verse.verse}"


class Conversation(models.Model):
    """Logical chat session grouped by external user identifier."""

    user_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class GuestChatIdentity(models.Model):
    """Persistent browser-linked guest identity used for temporary chat caps."""

    guest_id = models.CharField(max_length=64, unique=True, db_index=True)
    conversations_started = models.PositiveIntegerField(default=0)
    total_asks = models.PositiveIntegerField(default=0)
    daily_asks_used = models.PositiveIntegerField(default=0)
    daily_asks_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        """Readable guest identity reference for admin/debug output."""
        return f"Guest {self.guest_id}"


class Message(models.Model):
    """Individual user/assistant message linked to a conversation."""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = (
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ResponseFeedback(models.Model):
    """Feedback event captured after a generated response is shown."""

    MODE_SIMPLE = "simple"
    MODE_DEEP = "deep"
    MODE_CHOICES = (
        (MODE_SIMPLE, "Simple"),
        (MODE_DEEP, "Deep"),
    )

    RESPONSE_MODE_LLM = "llm"
    RESPONSE_MODE_FALLBACK = "fallback"
    RESPONSE_MODE_CHOICES = (
        (RESPONSE_MODE_LLM, "LLM"),
        (RESPONSE_MODE_FALLBACK, "Fallback"),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_entries",
    )
    user_id = models.CharField(max_length=64, db_index=True)
    message = models.TextField()
    mode = models.CharField(
        max_length=16,
        choices=MODE_CHOICES,
        default=MODE_SIMPLE,
    )
    response_mode = models.CharField(
        max_length=16,
        choices=RESPONSE_MODE_CHOICES,
        default=RESPONSE_MODE_FALLBACK,
    )
    helpful = models.BooleanField()
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class UserSubscription(models.Model):
    """Per-user plan record used for ask quota and monetization gates."""

    PLAN_FREE = "free"
    PLAN_PLUS = "plus"
    PLAN_PRO = "pro"
    PLAN_CHOICES = (
        (PLAN_FREE, "Free"),
        (PLAN_PLUS, "Plus"),
        (PLAN_PRO, "Pro"),
    )

    CURRENCY_INR = "INR"
    CURRENCY_USD = "USD"
    CURRENCY_CHOICES = (
        (CURRENCY_INR, "Indian Rupee"),
        (CURRENCY_USD, "US Dollar"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.CharField(
        max_length=16,
        choices=PLAN_CHOICES,
        default=PLAN_FREE,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Razorpay payment fields
    razorpay_customer_id = models.CharField(max_length=64, blank=True, null=True)
    razorpay_subscription_id = models.CharField(max_length=64, blank=True, null=True)
    razorpay_order_id = models.CharField(max_length=64, blank=True, null=True)
    payment_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        blank=True,
        null=True,
    )
    subscription_end_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]


class BillingRecord(models.Model):
    """Single invoice-ready ledger row per Razorpay order/payment."""

    TAX_DOMESTIC = "domestic_taxable"
    TAX_EXPORT_LUT = "export_lut"
    TAX_UNKNOWN = "unknown"
    TAX_TREATMENT_CHOICES = (
        (TAX_DOMESTIC, "Domestic taxable"),
        (TAX_EXPORT_LUT, "Export under LUT"),
        (TAX_UNKNOWN, "Unknown"),
    )

    STATUS_CREATED = "created"
    STATUS_VERIFIED = "verified"
    STATUS_CAPTURED = "captured"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (STATUS_CREATED, "Created"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_CAPTURED, "Captured"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="billing_records",
        blank=True,
        null=True,
    )
    subscription = models.ForeignKey(
        "UserSubscription",
        on_delete=models.SET_NULL,
        related_name="billing_records",
        blank=True,
        null=True,
    )
    plan = models.CharField(
        max_length=16,
        choices=UserSubscription.PLAN_CHOICES,
        default=UserSubscription.PLAN_FREE,
    )
    payment_status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED,
    )
    tax_treatment = models.CharField(
        max_length=24,
        choices=TAX_TREATMENT_CHOICES,
        default=TAX_UNKNOWN,
    )
    is_international = models.BooleanField(default=False)

    billing_name = models.CharField(max_length=120, blank=True)
    billing_email = models.EmailField(blank=True)
    business_name = models.CharField(max_length=160, blank=True)
    gstin = models.CharField(max_length=20, blank=True)
    billing_country_code = models.CharField(max_length=2, blank=True)
    billing_country_name = models.CharField(max_length=80, blank=True)
    billing_state = models.CharField(max_length=80, blank=True)
    billing_city = models.CharField(max_length=80, blank=True)
    billing_postal_code = models.CharField(max_length=20, blank=True)
    billing_address = models.TextField(blank=True)

    currency = models.CharField(
        max_length=3,
        choices=UserSubscription.CURRENCY_CHOICES,
        blank=True,
    )
    amount_minor = models.PositiveIntegerField(default=0)
    amount_major = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    razorpay_order_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
    )
    razorpay_payment_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    payment_method = models.CharField(max_length=40, blank=True)
    invoice_reference = models.CharField(max_length=64, blank=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    raw_order_payload = models.JSONField(default=dict, blank=True)
    raw_payment_payload = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Readable billing row reference for admin/export."""
        return f"{self.razorpay_order_id} ({self.plan})"


class DailyAskUsage(models.Model):
    """Daily ask usage counter for authenticated users."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_ask_usage",
    )
    date = models.DateField(db_index=True)
    ask_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                name="unique_daily_ask_usage_user_date",
            ),
        ]
        ordering = ["-date"]


class RequestQuotaSettings(models.Model):
    """Singleton quota controls for all guest/free/plus/pro ask limits."""

    singleton = models.BooleanField(default=True, unique=True, editable=False)

    guest_limit_enabled = models.BooleanField(default=True)
    guest_ask_limit = models.PositiveIntegerField(default=3)

    free_limit_enabled = models.BooleanField(default=True)
    free_daily_ask_limit = models.PositiveIntegerField(default=5)
    free_monthly_ask_limit = models.PositiveIntegerField(default=100)
    free_deep_mode_enabled = models.BooleanField(default=False)

    plus_limit_enabled = models.BooleanField(default=False)
    plus_daily_ask_limit = models.PositiveIntegerField(default=0)
    plus_monthly_ask_limit = models.PositiveIntegerField(default=200)
    plus_deep_monthly_limit = models.PositiveIntegerField(default=40)

    pro_limit_enabled = models.BooleanField(default=True)
    pro_daily_ask_limit = models.PositiveIntegerField(default=100)
    pro_monthly_ask_limit = models.PositiveIntegerField(default=500)
    pro_deep_monthly_limit = models.PositiveIntegerField(default=180)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Request quota settings"
        verbose_name_plural = "Request quota settings"

    def __str__(self) -> str:
        """Readable singleton label in admin list."""
        return "Request quota settings"


class AskEvent(models.Model):
    """Telemetry row for each ask attempt and delivery outcome."""

    SOURCE_API = "api"
    SOURCE_CHAT_UI = "chat_ui"
    SOURCE_CHOICES = (
        (SOURCE_API, "API"),
        (SOURCE_CHAT_UI, "Chat UI"),
    )

    OUTCOME_SERVED = "served"
    OUTCOME_BLOCKED_SAFETY = "blocked_safety"
    OUTCOME_BLOCKED_QUOTA = "blocked_quota"
    OUTCOME_CHOICES = (
        (OUTCOME_SERVED, "Served"),
        (OUTCOME_BLOCKED_SAFETY, "Blocked by safety"),
        (OUTCOME_BLOCKED_QUOTA, "Blocked by quota"),
    )

    MODE_SIMPLE = "simple"
    MODE_DEEP = "deep"
    MODE_CHOICES = (
        (MODE_SIMPLE, "Simple"),
        (MODE_DEEP, "Deep"),
    )

    RESPONSE_MODE_LLM = "llm"
    RESPONSE_MODE_FALLBACK = "fallback"
    RESPONSE_MODE_CHOICES = (
        (RESPONSE_MODE_LLM, "LLM"),
        (RESPONSE_MODE_FALLBACK, "Fallback"),
    )

    user_id = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES)
    outcome = models.CharField(max_length=32, choices=OUTCOME_CHOICES)
    response_mode = models.CharField(
        max_length=16,
        choices=RESPONSE_MODE_CHOICES,
        blank=True,
    )
    retrieval_mode = models.CharField(max_length=32, blank=True)
    plan = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class WebAudienceProfile(models.Model):
    """Durable web-visitor identity and visit counters for growth analytics."""

    SOURCE_CHAT_UI = "chat_ui"
    SOURCE_SEO_INDEX = "seo_index"
    SOURCE_SEO_TOPIC = "seo_topic"
    SOURCE_CHOICES = (
        (SOURCE_CHAT_UI, "Chat UI"),
        (SOURCE_SEO_INDEX, "SEO Index"),
        (SOURCE_SEO_TOPIC, "SEO Topic"),
    )

    audience_id = models.CharField(max_length=64, unique=True, db_index=True)
    is_authenticated = models.BooleanField(default=False)
    visit_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    first_source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        blank=True,
    )
    last_source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
    )
    first_utm_source = models.CharField(max_length=64, blank=True)
    first_utm_medium = models.CharField(max_length=64, blank=True)
    first_utm_campaign = models.CharField(max_length=64, blank=True)
    last_utm_source = models.CharField(max_length=64, blank=True)
    last_utm_medium = models.CharField(max_length=64, blank=True)
    last_utm_campaign = models.CharField(max_length=64, blank=True)
    last_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        """Readable profile reference for admin listings."""
        return self.audience_id


class GrowthEvent(models.Model):
    """Frontend growth-funnel events for virality and conversion tracking."""

    EVENT_LANDING_VIEW = "landing_view"
    EVENT_STARTER_CLICK = "starter_click"
    EVENT_SHARE_CLICK = "share_click"
    EVENT_COPY_LINK_CLICK = "copy_link_click"
    EVENT_ASK_SUBMIT = "ask_submit"
    EVENT_CHOICES = (
        (EVENT_LANDING_VIEW, "Landing View"),
        (EVENT_STARTER_CLICK, "Starter Click"),
        (EVENT_SHARE_CLICK, "Share Click"),
        (EVENT_COPY_LINK_CLICK, "Copy Link Click"),
        (EVENT_ASK_SUBMIT, "Ask Submit"),
    )

    SOURCE_CHAT_UI = "chat_ui"
    SOURCE_SEO_INDEX = "seo_index"
    SOURCE_SEO_TOPIC = "seo_topic"
    SOURCE_CHOICES = (
        (SOURCE_CHAT_UI, "Chat UI"),
        (SOURCE_SEO_INDEX, "SEO Index"),
        (SOURCE_SEO_TOPIC, "SEO Topic"),
    )

    audience_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    path = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Readable growth-event label in admin."""
        return f"{self.event_type}:{self.audience_id}"


class SavedReflection(models.Model):
    """User-saved guidance entry for retention and revisit flows."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_reflections",
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_reflections",
    )
    message = models.TextField()
    guidance = models.TextField()
    meaning = models.TextField(blank=True)
    actions = models.JSONField(default=list, blank=True)
    reflection = models.TextField(blank=True)
    verse_references = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class FollowUpEvent(models.Model):
    """Analytics event for contextual follow-up prompt lifecycle."""

    SOURCE_API = "api"
    SOURCE_CHAT_UI = "chat_ui"
    SOURCE_CHOICES = (
        (SOURCE_API, "API"),
        (SOURCE_CHAT_UI, "Chat UI"),
    )

    EVENT_SHOWN = "shown"
    EVENT_CLICKED = "clicked"
    EVENT_CHOICES = (
        (EVENT_SHOWN, "Shown"),
        (EVENT_CLICKED, "Clicked"),
    )

    user_id = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    event_type = models.CharField(max_length=16, choices=EVENT_CHOICES)
    intent = models.CharField(max_length=32)
    prompt = models.CharField(max_length=255)
    mode = models.CharField(max_length=16, default="simple")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class UserEngagementProfile(models.Model):
    """Per-user engagement state for streaks and reminder preferences."""

    CHANNEL_PUSH = "push"
    CHANNEL_EMAIL = "email"
    CHANNEL_NONE = "none"
    CHANNEL_CHOICES = (
        (CHANNEL_PUSH, "Push"),
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_NONE, "None"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="engagement_profile",
    )
    daily_streak = models.PositiveIntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    reminder_enabled = models.BooleanField(default=False)
    reminder_time = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    preferred_channel = models.CharField(
        max_length=16,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_NONE,
    )
    # User-local calendar date (in their reminder timezone) when we last sent a push reminder.
    last_reminder_push_date = models.DateField(null=True, blank=True)
    reminder_language = models.CharField(
        max_length=4,
        default="en",
        help_text="Language for daily reminder push copy (en|hi); mirrors app UI language.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class EngagementEvent(models.Model):
    """Analytics events for streak changes and reminder preference edits."""

    EVENT_STREAK_UPDATED = "streak_updated"
    EVENT_REMINDER_PREF_UPDATED = "reminder_pref_updated"
    EVENT_CHOICES = (
        (EVENT_STREAK_UPDATED, "Streak updated"),
        (EVENT_REMINDER_PREF_UPDATED, "Reminder preference updated"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="engagement_events",
    )
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class SupportTicket(models.Model):
    """Support request submitted by guest or authenticated users."""

    ISSUE_PAYMENT = "payment"
    ISSUE_ACCOUNT = "account"
    ISSUE_BUG = "bug"
    ISSUE_OTHER = "other"
    ISSUE_CHOICES = (
        (ISSUE_PAYMENT, "Payment"),
        (ISSUE_ACCOUNT, "Account"),
        (ISSUE_BUG, "Bug"),
        (ISSUE_OTHER, "Other"),
    )

    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = (
        (STATUS_OPEN, "Open"),
        (STATUS_RESOLVED, "Resolved"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    requester_id = models.CharField(max_length=64, blank=True, db_index=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    issue_type = models.CharField(
        max_length=16,
        choices=ISSUE_CHOICES,
        default=ISSUE_OTHER,
    )
    message = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Readable support ticket title for admin list."""
        return f"Support {self.issue_type} ({self.email})"


class NotificationDevice(models.Model):
    """Push device token registered by users for reminder delivery."""

    PLATFORM_ANDROID = "android"
    PLATFORM_IOS = "ios"
    PLATFORM_WEB = "web"
    PLATFORM_CHOICES = (
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_WEB, "Web"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_devices",
    )
    token = models.CharField(max_length=512, unique=True, db_index=True)
    platform = models.CharField(
        max_length=16,
        choices=PLATFORM_CHOICES,
        default=PLATFORM_ANDROID,
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        """Readable device label for admin lists."""
        return f"{self.user_id}:{self.platform}:{self.id}"


class QuoteArt(models.Model):
    """User-generated shareable quote art from Gita verses."""

    STYLE_DIVINE = "divine"
    STYLE_MINIMAL = "minimal"
    STYLE_NATURE = "nature"
    STYLE_COSMIC = "cosmic"
    STYLE_CHOICES = (
        (STYLE_DIVINE, "Divine - golden temple aesthetic"),
        (STYLE_MINIMAL, "Minimal - clean modern design"),
        (STYLE_NATURE, "Nature - forest and lotus imagery"),
        (STYLE_COSMIC, "Cosmic - stars and universe theme"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quote_arts",
        null=True,
        blank=True,
    )
    verse_reference = models.CharField(max_length=16)
    quote_text = models.TextField()
    quote_language = models.CharField(max_length=8, default="en")
    style = models.CharField(
        max_length=16,
        choices=STYLE_CHOICES,
        default=STYLE_DIVINE,
    )
    background_color = models.CharField(max_length=16, default="#1a1a2e")
    text_color = models.CharField(max_length=16, default="#ffd700")
    font_style = models.CharField(max_length=32, default="serif")
    share_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"QuoteArt {self.verse_reference}"


class CommunityPost(models.Model):
    """Scoped public thread: top-level posts and a single reply level."""

    MAX_BODY_CHARS = 4000

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_posts",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    body = models.TextField(max_length=MAX_BODY_CHARS)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["parent", "-created_at"]),
        ]

    def __str__(self) -> str:
        """Short label for admin lists."""
        kind = "reply" if self.parent_id else "post"
        return f"{kind} #{self.pk}"


class SharedAnswer(models.Model):
    """Persisted share card for a single guidance response."""

    share_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    question = models.TextField()
    guidance = models.TextField()
    meaning = models.TextField(blank=True)
    actions = models.JSONField(default=list)
    reflection = models.TextField(blank=True)
    verse_references = models.JSONField(default=list)
    language = models.CharField(max_length=4, default="en")
    user_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"SharedAnswer {self.share_id}"


class SadhanaProgram(models.Model):
    """A guided multi-day sadhana track (mantra, prānāyāma, yoga, etc.)."""

    slug = models.SlugField(max_length=96, unique=True)
    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    philosophy_blurb = models.TextField(
        blank=True,
        help_text="Optional wellness / non-medical disclaimer shown with the program.",
    )
    duration_days = models.PositiveSmallIntegerField(default=30)
    estimated_minutes_per_day = models.PositiveSmallIntegerField(default=15)
    is_published = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    free_sample_day_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day index (1-based) available without purchase for preview.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self) -> str:
        return self.title


class SadhanaDay(models.Model):
    """Single day inside a sadhana program."""

    program = models.ForeignKey(
        SadhanaProgram,
        on_delete=models.CASCADE,
        related_name="days",
    )
    day_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    summary = models.TextField(blank=True)
    intention = models.TextField(
        blank=True,
        help_text="Closing intention / living-the-mantra cue for the day.",
    )

    class Meta:
        ordering = ["day_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "day_number"],
                name="unique_sadhana_program_day_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.program.slug} day {self.day_number}"


class SadhanaStep(models.Model):
    """Ordered step within a day — supports media, captions, and extended modalities."""

    STEP_WARMUP_YOGA = "warmup_yoga"
    STEP_YOGA_FLOW = "yoga_flow"
    STEP_PRANAYAMA = "pranayama"
    STEP_BREATH_AWARENESS = "breath_awareness"
    STEP_BHAKTI = "bhakti"
    STEP_MANTRA = "mantra"
    STEP_NAAM_JAPA_GUIDED = "naam_japa_guided"
    STEP_KIRTAN_LISTEN = "kirtan_listen"
    STEP_BHAJAN_LISTEN = "bhajan_listen"
    STEP_SILENT_SIT = "silent_sit"
    STEP_SOUNDSCAPE = "soundscape"
    STEP_AFFIRMATION_SANKALPA = "affirmation_sankalpa"
    STEP_TEACHING_DHARMA = "teaching_dharma"
    STEP_SUBTLE_BODY_GUIDED = "subtle_body_guided"
    STEP_INTEGRATION = "integration"
    STEP_CHOICES = (
        (STEP_WARMUP_YOGA, "Warm-up yoga"),
        (STEP_YOGA_FLOW, "Yoga flow"),
        (STEP_PRANAYAMA, "Prānāyāma"),
        (STEP_BREATH_AWARENESS, "Breath awareness"),
        (STEP_BHAKTI, "Bhakti / remembrance"),
        (STEP_MANTRA, "Mantra chanting"),
        (STEP_NAAM_JAPA_GUIDED, "Nām japa (guided)"),
        (STEP_KIRTAN_LISTEN, "Kīrtan (listen / follow)"),
        (STEP_BHAJAN_LISTEN, "Bhajan (listen / follow)"),
        (STEP_SILENT_SIT, "Silent sitting"),
        (STEP_SOUNDSCAPE, "Soundscape / ambience"),
        (STEP_AFFIRMATION_SANKALPA, "Affirmation / saṅkalpa"),
        (STEP_TEACHING_DHARMA, "Teaching / śāstra moment"),
        (STEP_SUBTLE_BODY_GUIDED, "Subtle body (guided — advanced)"),
        (STEP_INTEGRATION, "Living the mantra / integration"),
    )

    SAFETY_GENTLE = "gentle"
    SAFETY_MODERATE = "moderate"
    SAFETY_INTENSE = "intense"
    SAFETY_TIER_CHOICES = (
        (SAFETY_GENTLE, "Gentle"),
        (SAFETY_MODERATE, "Moderate"),
        (SAFETY_INTENSE, "Intense — extra care"),
    )

    day = models.ForeignKey(
        SadhanaDay,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    sequence = models.PositiveSmallIntegerField()
    step_type = models.CharField(max_length=32, choices=STEP_CHOICES)
    title = models.CharField(max_length=160)
    instructions = models.TextField(blank=True)
    audio_url = models.URLField(blank=True)
    video_url = models.URLField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(blank=True, null=True)
    subtitle_tracks = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {language, label, format, url, is_default?} for WebVTT/SRT captions.",
    )
    timed_cues = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional list of {t_ms, text} for on-screen follow-along (e.g. mantra lines).",
    )
    safety_tier = models.CharField(
        max_length=16,
        choices=SAFETY_TIER_CHOICES,
        default=SAFETY_GENTLE,
    )
    requires_standing = models.BooleanField(
        default=False,
        help_text="If true, UI can warn users who practice seated only.",
    )

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "sequence"],
                name="unique_sadhana_day_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day_id}: {self.title}"


class SadhanaEnrollment(models.Model):
    """Paid or ongoing access window for one user per program."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sadhana_enrollments",
    )
    program = models.ForeignKey(
        SadhanaProgram,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    access_starts_at = models.DateTimeField()
    access_ends_at = models.DateTimeField()
    billing_record = models.ForeignKey(
        "BillingRecord",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sadhana_enrollments",
    )
    renewal_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "program"],
                name="unique_sadhana_user_program",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.program.slug}"


class SadhanaDayCompletion(models.Model):
    """Marks a user's finished day (paid enrollment or free-sample day)."""

    enrollment = models.ForeignKey(
        SadhanaEnrollment,
        on_delete=models.CASCADE,
        related_name="completed_days",
        blank=True,
        null=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sadhana_day_completions",
        blank=True,
        null=True,
        help_text="Used when marking free-sample days without paid enrollment.",
    )
    day = models.ForeignKey(
        SadhanaDay,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "day"],
                condition=Q(enrollment__isnull=False),
                name="unique_sadhana_enrollment_day_completion",
            ),
            models.UniqueConstraint(
                fields=["user", "day"],
                condition=Q(enrollment__isnull=True, user__isnull=False),
                name="unique_sadhana_user_day_sample_completion",
            ),
            models.CheckConstraint(
                condition=Q(enrollment__isnull=False) | Q(user__isnull=False),
                name="sadhana_completion_has_actor",
            ),
        ]


class PracticeTag(models.Model):
    """Filter / discovery tag for practice materials (e.g. deity, lineage, modality)."""

    slug = models.SlugField(max_length=64, unique=True, db_index=True)
    label = models.CharField(max_length=80)
    category = models.CharField(
        max_length=32,
        blank=True,
        help_text="Optional grouping for UI facets (e.g. deity, lineage).",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self) -> str:
        return self.label


class PracticeWorkflow(models.Model):
    """Single-session or short guided flow (e.g. flagship ~30 min meditation)."""

    ACCESS_FREE_PUBLIC = "free_public"
    ACCESS_PRO_INCLUDED = "pro_included"
    ACCESS_PURCHASE_REQUIRED = "purchase_required"
    ACCESS_CHOICES = (
        (ACCESS_FREE_PUBLIC, "Free — all signed-in users"),
        (ACCESS_PRO_INCLUDED, "Included with active Pro"),
        (ACCESS_PURCHASE_REQUIRED, "Purchase required (any plan)"),
    )

    slug = models.SlugField(max_length=96, unique=True)
    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    philosophy_blurb = models.TextField(
        blank=True,
        help_text="Optional wellness / non-medical disclaimer shown with the flow.",
    )
    access_mode = models.CharField(
        max_length=24,
        choices=ACCESS_CHOICES,
        default=ACCESS_FREE_PUBLIC,
        db_index=True,
    )
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Highlight in Meditate / practice hub when true.",
    )
    is_published = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    estimated_total_minutes = models.PositiveSmallIntegerField(blank=True, null=True)
    purchase_notes = models.CharField(
        max_length=240,
        blank=True,
        help_text="Short copy when purchase is required (checkout wiring is separate).",
    )
    purchase_price_minor_inr = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Razorpay order amount (paise) when access_mode is purchase_required.",
    )
    purchase_price_minor_usd = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Razorpay order amount (cents) when access_mode is purchase_required.",
    )
    purchase_access_days = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Access window after purchase; null = lifetime (no fixed end).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self) -> str:
        return self.title


class PracticeWorkflowStep(models.Model):
    """Ordered step inside a practice workflow — mirrors sadhana step media shape."""

    workflow = models.ForeignKey(
        PracticeWorkflow,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    sequence = models.PositiveSmallIntegerField()
    step_type = models.CharField(max_length=32, choices=SadhanaStep.STEP_CHOICES)
    title = models.CharField(max_length=160)
    instructions = models.TextField(blank=True)
    audio_url = models.URLField(blank=True)
    video_url = models.URLField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(blank=True, null=True)
    subtitle_tracks = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {language, label, format, url, is_default?} for WebVTT/SRT captions.",
    )
    timed_cues = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional list of {t_ms, text} for on-screen follow-along.",
    )
    safety_tier = models.CharField(
        max_length=16,
        choices=SadhanaStep.SAFETY_TIER_CHOICES,
        default=SadhanaStep.SAFETY_GENTLE,
    )
    requires_standing = models.BooleanField(default=False)
    tags = models.ManyToManyField(
        PracticeTag,
        blank=True,
        related_name="workflow_steps",
    )

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "sequence"],
                name="unique_practice_workflow_step_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.workflow.slug}:{self.sequence}"


class PracticeWorkflowEnrollment(models.Model):
    """Time-bounded access after purchase (or staff grant); not used for free_public."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="practice_workflow_enrollments",
    )
    workflow = models.ForeignKey(
        PracticeWorkflow,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    access_starts_at = models.DateTimeField()
    access_ends_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Null means no fixed end (lifetime / open window).",
    )
    billing_record = models.ForeignKey(
        "BillingRecord",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="practice_workflow_enrollments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "workflow"],
                name="unique_practice_workflow_user_enrollment",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.workflow.slug}"


class VerseUserNote(models.Model):
    """Private per-verse study notes for revisiting and verse-scoped Q&A context."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verse_notes",
    )
    chapter = models.PositiveSmallIntegerField()
    verse = models.PositiveSmallIntegerField()
    body = models.TextField(blank=True, max_length=12000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "chapter", "verse"],
                name="unique_user_verse_note",
            ),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Note {self.user_id} BG{self.chapter}.{self.verse}"


class UserReadingState(models.Model):
    """Tracks last read position, unique verses opened, and a simple read streak."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reading_state",
    )
    last_chapter = models.PositiveSmallIntegerField(null=True, blank=True)
    last_verse = models.PositiveSmallIntegerField(null=True, blank=True)
    verses_seen = models.JSONField(default=list, blank=True)
    last_read_date = models.DateField(null=True, blank=True)
    read_streak = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"ReadingState {self.user_id}"


class PracticeLogEntry(models.Model):
    """Manual log of japa, meditation minutes, or reading minutes."""

    TYPE_JAPA_ROUNDS = "japa_rounds"
    TYPE_MEDITATION_MINUTES = "meditation_minutes"
    TYPE_READ_MINUTES = "read_minutes"
    TYPE_CHOICES = (
        (TYPE_JAPA_ROUNDS, "Japa (mala rounds)"),
        (TYPE_MEDITATION_MINUTES, "Meditation minutes"),
        (TYPE_READ_MINUTES, "Reading minutes"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="practice_log_entries",
    )
    logged_on = models.DateField()
    entry_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    mantra_label = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=500, blank=True)
    japa_commitment = models.ForeignKey(
        "JapaCommitment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_log_entries",
        help_text="When set, this row syncs one calendar day of japa for that personal track.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-logged_on", "-created_at"]
        indexes = [
            models.Index(fields=["user", "logged_on"]),
            models.Index(fields=["user", "japa_commitment", "logged_on"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.logged_on} {self.entry_type}"


class MeditationSessionLog(models.Model):
    """Self-reported pre/post mood around a meditation sit (wellness journaling, not clinical)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meditation_session_logs",
    )
    pre_mood = models.PositiveSmallIntegerField(null=True, blank=True)
    pre_stress = models.PositiveSmallIntegerField(null=True, blank=True)
    pre_note = models.TextField(blank=True, max_length=2000)
    post_mood = models.PositiveSmallIntegerField(null=True, blank=True)
    post_stress = models.PositiveSmallIntegerField(null=True, blank=True)
    post_note = models.TextField(blank=True, max_length=2000)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    program_slug = models.SlugField(max_length=96, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"MeditationLog {self.user_id} {self.created_at}"


class JapaCommitment(models.Model):
    """User-defined personal japa / mālā sankalpa (distinct from curated SadhanaProgram)."""

    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_FULFILLED = "fulfilled"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_ARCHIVED, "Archived"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="japa_commitments",
    )
    title = models.CharField(max_length=120)
    focus_label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Iṣṭa / deity / form (free text).",
    )
    mantra_label = models.CharField(max_length=120, blank=True)
    daily_target_malas = models.PositiveSmallIntegerField(default=1)
    started_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    preferred_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"JapaCommitment {self.user_id} {self.title!r}"


class JapaSession(models.Model):
    """One sit for a commitment (start / pause / resume / finish-day or abandon)."""

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = (
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ABANDONED, "Abandoned"),
    )

    commitment = models.ForeignKey(
        JapaCommitment,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="japa_sessions",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    pause_started_at = models.DateTimeField(null=True, blank=True)
    paused_seconds = models.PositiveIntegerField(default=0)
    reported_malas = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["commitment", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"JapaSession {self.user_id} c={self.commitment_id}"


class JapaDailyCompletion(models.Model):
    """Idempotent per-calendar-day completion for a commitment (local date from client)."""

    commitment = models.ForeignKey(
        JapaCommitment,
        on_delete=models.CASCADE,
        related_name="daily_completions",
    )
    date = models.DateField()
    malas_completed = models.PositiveIntegerField()
    session = models.ForeignKey(
        JapaSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_completions",
    )
    note = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["commitment", "date"], name="unique_japa_commitment_date"),
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"JapaDaily {self.commitment_id} {self.date} m={self.malas_completed}"
