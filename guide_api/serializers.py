"""DRF serializers for validating requests and shaping responses."""

from rest_framework import serializers

from guide_api.models import Message, SavedReflection, Verse


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


class PlanUpdateRequestSerializer(serializers.Serializer):
    """Validate mock billing plan update payload for testing gates."""

    plan = serializers.ChoiceField(choices=["free", "pro"])


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
