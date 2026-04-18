"""DRF serializers for validating requests and shaping responses."""

from rest_framework import serializers

from guide_api.models import BillingRecord, CommunityPost, Message, SavedReflection, Verse


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
    )
    reflection = serializers.CharField(required=False, allow_blank=True)
    verse_references = serializers.ListField(
        child=serializers.CharField(),
        required=False,
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
    path = serializers.CharField(max_length=255, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)


class AnalyticsSummaryRequestSerializer(serializers.Serializer):
    """Validate growth summary query window parameters."""

    days = serializers.IntegerField(min_value=1, max_value=90, default=7)


class SharedAnswerCreateSerializer(serializers.Serializer):
    """Validate inputs when creating a shareable answer card."""

    question = serializers.CharField(max_length=1000, allow_blank=True)
    guidance = serializers.CharField(max_length=5000)
    meaning = serializers.CharField(max_length=5000, required=False, default="")
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
