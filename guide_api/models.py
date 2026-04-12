"""Core database models for verses, chats, and feedback."""

import uuid

from django.conf import settings
from django.db import models


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
    PLAN_PRO = "pro"
    PLAN_CHOICES = (
        (PLAN_FREE, "Free"),
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
    """Singleton quota controls for guest, free, and pro ask limits."""

    singleton = models.BooleanField(default=True, unique=True, editable=False)

    guest_limit_enabled = models.BooleanField(default=True)
    guest_ask_limit = models.PositiveIntegerField(default=3)

    free_limit_enabled = models.BooleanField(default=True)
    free_daily_ask_limit = models.PositiveIntegerField(default=5)

    pro_limit_enabled = models.BooleanField(default=True)
    pro_daily_ask_limit = models.PositiveIntegerField(default=10000)

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
