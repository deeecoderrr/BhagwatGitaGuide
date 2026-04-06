"""Core database models for verses, chats, and feedback."""

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


class Conversation(models.Model):
    """Logical chat session grouped by external user identifier."""

    user_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


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
