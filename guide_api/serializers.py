"""DRF serializers for validating requests and shaping responses."""

from rest_framework import serializers

from guide_api.models import (
    BillingRecord,
    CommunityPost,
    Message,
    NotificationDevice,
    PracticeLogEntry,
    SavedReflection,
    SupportTicket,
    Verse,
    VerseUserNote,
)


class VerseSerializer(serializers.ModelSerializer):
    """Expose verse content and a computed chapter.verse reference."""

    reference = serializers.SerializerMethodField()

    class Meta:
        model = Verse
        fields = [
            "reference",
            "chapter",
            "verse",
            "translation",
            "commentary",
            "themes",
        ]

    def get_reference(self, obj: Verse) -> str:
        """Return stable verse reference format used across APIs."""
        return f"{obj.chapter}.{obj.verse}"


class AskRequestSerializer(serializers.Serializer):
    """Validate inputs for the main ask endpoint."""

    user_id = serializers.CharField(max_length=64, required=False)
    message = serializers.CharField()
    language = serializers.ChoiceField(
        choices=["en", "hi"],
        default="en",
    )
    mode = serializers.ChoiceField(
        choices=["simple", "deep"],
        default="simple",
    )
    conversation_id = serializers.IntegerField(required=False)
    verse_ref = serializers.CharField(max_length=16, required=False, allow_blank=True)
    verse_note_excerpt = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class GuestAskRequestSerializer(serializers.Serializer):
    """Validate unauthenticated ask requests from mobile guest mode."""

    guest_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    message = serializers.CharField()
    language = serializers.ChoiceField(choices=["en", "hi"], default="en")
    mode = serializers.ChoiceField(choices=["simple", "deep"], default="simple")
    verse_ref = serializers.CharField(max_length=16, required=False, allow_blank=True)
    verse_note_excerpt = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class RetrievalEvalRequestSerializer(serializers.Serializer):
    """Validate retrieval evaluation requests, including benchmark mode."""

    message = serializers.CharField()
    mode = serializers.ChoiceField(
        choices=["simple", "deep", "benchmark"],
        default="simple",
    )


class AskResponseSerializer(serializers.Serializer):
    """Legacy explicit response schema for ask output."""

    conversation_id = serializers.IntegerField()
    guidance = serializers.CharField()
    verses = VerseSerializer(many=True)
    meaning = serializers.CharField()
    actions = serializers.ListField(child=serializers.CharField())
    reflection = serializers.CharField()


class MessageSerializer(serializers.ModelSerializer):
    """Serialize stored conversation messages for history endpoint."""

    class Meta:
        model = Message
        fields = ["role", "content", "created_at"]


class RegisterRequestSerializer(serializers.Serializer):
    """Validate registration payload for username/password signup."""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=8, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)


class LoginRequestSerializer(serializers.Serializer):
    """Validate login payload for username/password authentication."""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)


class GoogleAuthRequestSerializer(serializers.Serializer):
    """Validate Google Identity Services credential (JWT string)."""

    id_token = serializers.CharField()


class PlanUpdateRequestSerializer(serializers.Serializer):
    """Validate mock billing plan update payload for testing gates."""

    plan = serializers.ChoiceField(choices=["free", "plus", "pro"])


class SavedReflectionCreateSerializer(serializers.Serializer):
    """Validate create payload for saved reflection/bookmark entries."""

    conversation_id = serializers.IntegerField(required=False)
    message = serializers.CharField()
    guidance = serializers.CharField()
    meaning = serializers.CharField(required=False, allow_blank=True)
    actions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    reflection = serializers.CharField(required=False, allow_blank=True)
    verse_references = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
    )


class SavedReflectionSerializer(serializers.ModelSerializer):
    """Serialize saved reflections for web and mobile clients."""

    class Meta:
        model = SavedReflection
        fields = [
            "id",
            "conversation",
            "message",
            "guidance",
            "meaning",
            "actions",
            "reflection",
            "verse_references",
            "note",
            "created_at",
            "updated_at",
        ]


class FollowUpRequestSerializer(serializers.Serializer):
    """Validate contextual follow-up generation requests."""

    message = serializers.CharField()
    language = serializers.ChoiceField(
        choices=["en", "hi"],
        default="en",
    )
    mode = serializers.ChoiceField(
        choices=["simple", "deep"],
        default="simple",
    )


class EngagementProfileUpdateSerializer(serializers.Serializer):
    """Validate mutable reminder preferences for engagement profile."""

    reminder_enabled = serializers.BooleanField(required=False)
    reminder_time = serializers.TimeField(required=False, allow_null=True)
    timezone = serializers.CharField(max_length=64, required=False)
    preferred_channel = serializers.ChoiceField(
        choices=["push", "email", "none"],
        required=False,
    )
    reminder_language = serializers.ChoiceField(
        choices=["en", "hi"],
        required=False,
    )


class SupportRequestSerializer(serializers.Serializer):
    """Validate support requests submitted from API or chat UI."""

    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    issue_type = serializers.ChoiceField(
        choices=["payment", "account", "bug", "other"],
        default="other",
    )
    message = serializers.CharField(max_length=2000)


class ChapterListSerializer(serializers.Serializer):
    """Serialize chapter metadata for chapter listing screen."""

    chapter_number = serializers.IntegerField()
    name = serializers.CharField()
    translation = serializers.CharField()
    transliteration = serializers.CharField()
    verses_count = serializers.IntegerField()
    meaning_en = serializers.CharField()
    meaning_hi = serializers.CharField()


class ChapterDetailSerializer(serializers.Serializer):
    """Serialize full chapter detail with summary."""

    chapter_number = serializers.IntegerField()
    name = serializers.CharField()
    translation = serializers.CharField()
    transliteration = serializers.CharField()
    verses_count = serializers.IntegerField()
    meaning_en = serializers.CharField()
    meaning_hi = serializers.CharField()
    summary_en = serializers.CharField()
    summary_hi = serializers.CharField()


class CommentarySerializer(serializers.Serializer):
    """Serialize individual author commentary."""

    author = serializers.CharField()
    text = serializers.CharField()
    language = serializers.CharField()


class VerseSynthesisSerializer(serializers.Serializer):
    """Serialize cached multilingual verse synthesis for the reader UI."""

    generation_source = serializers.CharField()
    overview_en = serializers.CharField()
    overview_hi = serializers.CharField()
    commentary_consensus_en = serializers.CharField()
    commentary_consensus_hi = serializers.CharField()
    life_application_en = serializers.CharField()
    life_application_hi = serializers.CharField()
    key_points_en = serializers.ListField(child=serializers.CharField())
    key_points_hi = serializers.ListField(child=serializers.CharField())


class BillingRecordSerializer(serializers.ModelSerializer):
    """Serialize invoice-ready payment ledger rows for app/admin consumers."""

    username = serializers.SerializerMethodField()

    class Meta:
        model = BillingRecord
        fields = [
            "id",
            "plan",
            "payment_status",
            "tax_treatment",
            "is_international",
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
            "currency",
            "amount_minor",
            "amount_major",
            "razorpay_order_id",
            "razorpay_payment_id",
            "payment_method",
            "invoice_reference",
            "verified_at",
            "paid_at",
            "created_at",
            "updated_at",
            "username",
        ]

    def get_username(self, obj: BillingRecord) -> str:
        """Expose username when row is linked to an authenticated account."""
        if obj.user:
            return obj.user.username
        return ""


class VerseDetailSerializer(serializers.Serializer):
    """Full verse detail with sanskrit, translations, and commentaries."""

    reference = serializers.CharField()
    chapter = serializers.IntegerField()
    verse = serializers.IntegerField()
    speaker = serializers.CharField()
    slok = serializers.CharField()  # Sanskrit
    transliteration = serializers.CharField()
    translation = serializers.CharField()
    themes = serializers.ListField(child=serializers.CharField())
    hindi_meaning = serializers.CharField()
    english_meaning = serializers.CharField()
    word_meaning = serializers.CharField()
    commentaries = CommentarySerializer(many=True)
    synthesis = VerseSynthesisSerializer()
    cached = serializers.BooleanField()


class MantraRequestSerializer(serializers.Serializer):
    """Validate mantra generation request."""

    mood = serializers.ChoiceField(
        choices=["calm", "focus", "courage", "peace", "strength", "clarity"],
        default="peace",
    )
    language = serializers.ChoiceField(
        choices=["en", "hi"],
        default="en",
    )


class QuoteArtStyleSerializer(serializers.Serializer):
    """Serialize available quote art style for UI display."""

    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    preview_colors = serializers.DictField()


class QuoteArtRequestSerializer(serializers.Serializer):
    """Validate quote art generation request."""

    verse_reference = serializers.CharField(max_length=10)
    style = serializers.ChoiceField(
        choices=["divine", "minimal", "nature", "cosmic"],
        default="divine",
    )
    language = serializers.ChoiceField(
        choices=["en", "hi"],
        default="en",
    )
    custom_quote = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
    )


class QuoteArtStyleConfigSerializer(serializers.Serializer):
    """Serialize style configuration for rendering."""

    id = serializers.CharField()
    name = serializers.CharField()
    background_color = serializers.CharField()
    text_color = serializers.CharField()
    accent_color = serializers.CharField()
    font_style = serializers.CharField()
    gradient = serializers.ListField(child=serializers.CharField())


class QuoteArtResponseSerializer(serializers.Serializer):
    """Serialize generated quote art data for mobile rendering."""

    verse_reference = serializers.CharField()
    chapter = serializers.IntegerField()
    verse = serializers.IntegerField()
    quote_text = serializers.CharField()
    sanskrit_text = serializers.CharField()
    transliteration = serializers.CharField()
    language = serializers.CharField()
    style = QuoteArtStyleConfigSerializer()
    attribution = serializers.CharField()
    share_text = serializers.CharField()


class FeaturedQuoteSerializer(serializers.Serializer):
    """Serialize featured quote for art suggestions."""

    reference = serializers.CharField()
    preview_quote = serializers.CharField()
    sanskrit_preview = serializers.CharField()


class AnalyticsEventIngestSerializer(serializers.Serializer):
    """Validate frontend growth event ingestion payload."""

    event_type = serializers.ChoiceField(
        choices=[
            "starter_click",
            "share_click",
            "copy_link_click",
            "ask_submit",
        ]
    )
    source = serializers.ChoiceField(
        choices=["chat_ui", "seo_index", "seo_topic"],
        default="chat_ui",
    )
    path = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    metadata = serializers.JSONField(required=False)


class AnalyticsSummaryRequestSerializer(serializers.Serializer):
    """Validate growth summary query window parameters."""

    days = serializers.IntegerField(min_value=1, max_value=90, default=7)


class SharedAnswerCreateSerializer(serializers.Serializer):
    """Validate inputs when creating a shareable answer card."""

    question = serializers.CharField(max_length=1000, allow_blank=True)
    guidance = serializers.CharField(max_length=5000)
    meaning = serializers.CharField(
        max_length=5000,
        required=False,
        default="",
    )
    actions = serializers.ListField(
        child=serializers.CharField(max_length=500),
        max_length=20,
        required=False,
        default=list,
    )
    reflection = serializers.CharField(
        max_length=5000,
        required=False,
        default="",
    )
    verse_references = serializers.ListField(
        child=serializers.CharField(max_length=16),
        max_length=20,
        required=False,
        default=list,
    )
    language = serializers.ChoiceField(choices=["en", "hi"], default="en")


class CommunityPostCreateSerializer(serializers.Serializer):
    """Validate new community thread post or reply."""

    body = serializers.CharField(max_length=CommunityPost.MAX_BODY_CHARS)
    parent_id = serializers.IntegerField(required=False, allow_null=True)


class CommunityPostPatchSerializer(serializers.Serializer):
    """Validate community post body edit."""

    body = serializers.CharField(max_length=CommunityPost.MAX_BODY_CHARS)


class ConversationCreateSerializer(serializers.Serializer):
    """Validate explicit conversation create payload."""

    initial_message = serializers.CharField(required=False, allow_blank=True)


class ProfileUpdateSerializer(serializers.Serializer):
    """Validate mutable profile fields for authenticated users."""

    username = serializers.CharField(max_length=150, required=False)
    first_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )
    email = serializers.EmailField(required=False, allow_blank=True)


class ChangePasswordSerializer(serializers.Serializer):
    """Validate authenticated password-change request."""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)


class ForgotPasswordSerializer(serializers.Serializer):
    """Validate forgot-password request payload."""

    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, data):
        """Require at least one of username or email."""
        if not data.get("username") and not data.get("email"):
            raise serializers.ValidationError("Either username or email is required.")
        return data

class ResetPasswordConfirmSerializer(serializers.Serializer):
    """Validate token-based password reset confirmation payload."""

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


class NotificationDeviceRegisterSerializer(serializers.Serializer):
    """Validate push notification device registration payload."""

    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=["android", "ios", "web"])


class NotificationDeviceSerializer(serializers.ModelSerializer):
    """Serialize registered push devices."""

    class Meta:
        model = NotificationDevice
        fields = [
            "id",
            "platform",
            "active",
            "created_at",
            "updated_at",
            "last_seen_at",
        ]


class NotificationPreferenceSerializer(serializers.Serializer):
    """Expose reminder preference fields on notification endpoints."""

    reminder_enabled = serializers.BooleanField(required=False)
    reminder_time = serializers.TimeField(required=False, allow_null=True)
    timezone = serializers.CharField(max_length=64, required=False)
    preferred_channel = serializers.ChoiceField(
        choices=["push", "email", "none"],
        required=False,
    )
    reminder_language = serializers.ChoiceField(
        choices=["en", "hi"],
        required=False,
    )


class SupportTicketSerializer(serializers.ModelSerializer):
    """Serialize support-ticket rows for user self-service list."""

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "issue_type",
            "message",
            "status",
            "created_at",
            "updated_at",
        ]


class VerseUserNoteSerializer(serializers.ModelSerializer):
    """Serialize a user's private note for one verse."""

    reference = serializers.SerializerMethodField()

    class Meta:
        model = VerseUserNote
        fields = ["reference", "chapter", "verse", "body", "created_at", "updated_at"]

    def get_reference(self, obj: VerseUserNote) -> str:
        return f"{obj.chapter}.{obj.verse}"


class VerseUserNoteWriteSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=12000, allow_blank=True)


class VerseOpenSerializer(serializers.Serializer):
    chapter = serializers.IntegerField(min_value=1, max_value=18)
    verse = serializers.IntegerField(min_value=1, max_value=999)


class PracticeLogCreateSerializer(serializers.Serializer):
    logged_on = serializers.DateField()
    entry_type = serializers.ChoiceField(
        choices=[
            PracticeLogEntry.TYPE_JAPA_ROUNDS,
            PracticeLogEntry.TYPE_MEDITATION_MINUTES,
            PracticeLogEntry.TYPE_READ_MINUTES,
        ],
    )
    quantity = serializers.IntegerField(min_value=1, max_value=86400)
    mantra_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class MeditationSessionCreateSerializer(serializers.Serializer):
    pre_mood = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    pre_stress = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    pre_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    post_mood = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    post_stress = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    post_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    duration_seconds = serializers.IntegerField(
        min_value=0, max_value=86400 * 2, required=False, allow_null=True
    )
    program_slug = serializers.SlugField(max_length=96, required=False, allow_blank=True)


class JapaCommitmentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    focus_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    mantra_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    daily_target_malas = serializers.IntegerField(min_value=1, max_value=9999, default=1)
    started_on = serializers.DateField(required=False)
    ends_on = serializers.DateField(required=False, allow_null=True)
    preferred_time = serializers.TimeField(required=False, allow_null=True)


class JapaCommitmentPatchSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120, required=False)
    focus_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    mantra_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    daily_target_malas = serializers.IntegerField(required=False, min_value=1, max_value=9999)
    ends_on = serializers.DateField(required=False, allow_null=True)
    preferred_time = serializers.TimeField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=["active", "paused", "archived"],
        required=False,
    )


class JapaFinishDaySerializer(serializers.Serializer):
    """Mālā rounds completed this sit; summed into the commitment's calendar day."""

    local_date = serializers.DateField()
    malas_completed = serializers.IntegerField(min_value=1, max_value=9999)
    note = serializers.CharField(max_length=240, required=False, allow_blank=True)
