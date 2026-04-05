"""HTTP views for chat, retrieval evaluation, and feedback flows."""

from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView

from guide_api.models import (
    AskEvent,
    Conversation,
    DailyAskUsage,
    EngagementEvent,
    FollowUpEvent,
    Message,
    ResponseFeedback,
    SavedReflection,
    UserEngagementProfile,
    UserSubscription,
    Verse,
)
from guide_api.serializers import (
    AskRequestSerializer,
    EngagementProfileUpdateSerializer,
    FollowUpRequestSerializer,
    LoginRequestSerializer,
    MessageSerializer,
    PlanUpdateRequestSerializer,
    RegisterRequestSerializer,
    RetrievalEvalRequestSerializer,
    SavedReflectionCreateSerializer,
    SavedReflectionSerializer,
    VerseSerializer,
)
from guide_api.services import (
    build_guidance,
    is_risky_prompt,
    retrieve_hybrid_verses_with_trace,
    retrieve_verses,
    retrieve_semantic_verses_with_trace,
    retrieve_verses_with_trace,
)


def _run_guidance_flow(
    *,
    user_id: str,
    message: str,
    mode: str,
    conversation_id: int | None = None,
):
    """Run end-to-end ask pipeline and persist conversation messages."""
    if conversation_id:
        conversation = Conversation.objects.filter(
            id=conversation_id,
            user_id=user_id,
        ).first()
    else:
        conversation = None

    if conversation is None:
        conversation = Conversation.objects.create(user_id=user_id)

    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_USER,
        content=message,
    )

    retrieval = retrieve_verses_with_trace(
        message=message,
        limit=4 if mode == "deep" else 3,
    )
    verses = retrieval.verses
    guidance = build_guidance(message, verses)

    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_ASSISTANT,
        content=guidance.guidance,
    )
    return conversation, verses, guidance, retrieval


def _get_user_plan_and_usage(user):
    """Return user subscription record and today's usage counter."""
    subscription, _ = UserSubscription.objects.get_or_create(user=user)
    usage, _ = DailyAskUsage.objects.get_or_create(
        user=user,
        date=timezone.localdate(),
        defaults={"ask_count": 0},
    )
    return subscription, usage


def _plan_daily_limit(plan: str) -> int:
    """Resolve daily ask limit from configured plan."""
    if plan == UserSubscription.PLAN_PRO:
        return settings.ASK_LIMIT_PRO_DAILY
    return settings.ASK_LIMIT_FREE_DAILY


def _log_ask_event(
    *,
    user_id: str,
    source: str,
    mode: str,
    outcome: str,
    response_mode: str = "",
    retrieval_mode: str = "",
    plan: str = "",
) -> None:
    """Persist analytics row for each ask attempt."""
    AskEvent.objects.create(
        user_id=user_id,
        source=source,
        mode=mode,
        outcome=outcome,
        response_mode=response_mode,
        retrieval_mode=retrieval_mode,
        plan=plan,
    )


def _build_contextual_follow_ups(
    *,
    message: str,
    mode: str,
    query_themes: list[str],
) -> list[dict]:
    """Build deterministic, mobile-friendly follow-up prompts."""
    primary_theme = query_themes[0] if query_themes else "life"
    label_prefix = primary_theme.replace("_", " ").title()
    return [
        {
            "label": f"{label_prefix}: 3-step plan",
            "prompt": (
                "Give me a practical 3-step plan for the next 24 hours "
                f"for this issue: {message}"
            ),
            "intent": "action_plan",
        },
        {
            "label": f"{label_prefix}: deeper meaning",
            "prompt": (
                "Explain one key verse in simpler words and how I should "
                "apply it today."
            ),
            "intent": "deeper_meaning",
        },
        {
            "label": "Self-reflection",
            "prompt": (
                "Ask me one reflection question and one journaling prompt "
                "based on this guidance."
            ),
            "intent": "self_reflection",
        },
    ][: 2 if mode == "simple" else 3]


def _log_follow_up_events(
    *,
    user_id: str,
    source: str,
    event_type: str,
    mode: str,
    follow_ups: list[dict],
) -> None:
    """Persist follow-up shown/clicked analytics events."""
    for follow_up in follow_ups:
        FollowUpEvent.objects.create(
            user_id=user_id,
            source=source,
            event_type=event_type,
            intent=str(follow_up.get("intent", "")),
            prompt=str(follow_up.get("prompt", ""))[:255],
            mode=mode,
        )


def _error_response(
    *,
    message: str,
    status_code: int,
    code: str,
    extra: dict | None = None,
) -> Response:
    """Return stable error envelope while preserving legacy detail field."""
    payload = {
        "error": {
            "code": code,
            "message": message,
        },
        "detail": message,
    }
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def _pagination_params(request) -> tuple[int, int]:
    """Parse mobile-friendly limit/offset with safe defaults."""
    raw_limit = request.query_params.get("limit", "20")
    raw_offset = request.query_params.get("offset", "0")
    limit = int(raw_limit)
    offset = int(raw_offset)
    if limit <= 0:
        limit = 20
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0
    return limit, offset


def _get_engagement_profile(user):
    """Get or create engagement profile for authenticated user."""
    profile, _ = UserEngagementProfile.objects.get_or_create(user=user)
    return profile


def _serialize_engagement_profile(profile) -> dict:
    """Return stable API payload for engagement state."""
    return {
        "daily_streak": profile.daily_streak,
        "last_active_date": (
            profile.last_active_date.isoformat()
            if profile.last_active_date
            else None
        ),
        "reminder_enabled": profile.reminder_enabled,
        "reminder_time": (
            profile.reminder_time.strftime("%H:%M:%S")
            if profile.reminder_time
            else None
        ),
        "timezone": profile.timezone,
        "preferred_channel": profile.preferred_channel,
    }


def _log_engagement_event(*, user, event_type: str, metadata: dict) -> None:
    """Persist engagement analytics events."""
    EngagementEvent.objects.create(
        user=user,
        event_type=event_type,
        metadata=metadata,
    )


def _update_streak_for_today(user):
    """Update daily streak based on user's previous active date."""
    profile = _get_engagement_profile(user)
    today = timezone.localdate()
    previous = profile.last_active_date
    if previous == today:
        return profile
    if previous == (today - timedelta(days=1)):
        profile.daily_streak = max(1, profile.daily_streak + 1)
    else:
        profile.daily_streak = 1
    profile.last_active_date = today
    profile.save(
        update_fields=["daily_streak", "last_active_date", "updated_at"]
    )
    _log_engagement_event(
        user=user,
        event_type=EngagementEvent.EVENT_STREAK_UPDATED,
        metadata={
            "daily_streak": profile.daily_streak,
            "last_active_date": today.isoformat(),
        },
    )
    return profile


class HealthView(APIView):
    """Lightweight readiness endpoint for health checks."""

    def get(self, request):
        """Return service health status payload."""
        return Response({"status": "ok", "service": "gita-guide-api"})


class RegisterView(APIView):
    """Create user account and return API token."""

    def post(self, request):
        """Validate signup input and issue authentication token."""
        serializer = RegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"].strip()
        password = serializer.validated_data["password"]

        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            return _error_response(
                message="Username is already taken.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="username_taken",
            )

        user = user_model.objects.create_user(
            username=username,
            password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Authenticate existing user and return API token."""

    def post(self, request):
        """Validate credentials and issue existing/new token."""
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = authenticate(
            request=request,
            username=username,
            password=password,
        )
        if user is None:
            return _error_response(
                message="Invalid username or password.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_credentials",
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})


class LogoutView(APIView):
    """Logout by deleting the caller's current token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Invalidate active API token for authenticated user."""
        Token.objects.filter(user=request.user).delete()
        return Response({"status": "logged_out"})


class MeView(APIView):
    """Return current authenticated user identity."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Serve minimal identity payload for client checks."""
        subscription, usage = _get_user_plan_and_usage(request.user)
        engagement = _get_engagement_profile(request.user)
        daily_limit = _plan_daily_limit(subscription.plan)
        return Response(
            {
                "username": request.user.get_username(),
                "plan": subscription.plan,
                "daily_limit": daily_limit,
                "used_today": usage.ask_count,
                "remaining_today": max(daily_limit - usage.ask_count, 0),
                "engagement": _serialize_engagement_profile(engagement),
            }
        )


class PlanUpdateView(APIView):
    """Mock plan switch endpoint for local quota and paywall testing."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Update current user's plan between free and pro."""
        serializer = PlanUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription, usage = _get_user_plan_and_usage(request.user)
        subscription.plan = serializer.validated_data["plan"]
        subscription.save(update_fields=["plan", "updated_at"])
        daily_limit = _plan_daily_limit(subscription.plan)
        return Response(
            {
                "username": request.user.get_username(),
                "plan": subscription.plan,
                "daily_limit": daily_limit,
                "used_today": usage.ask_count,
                "remaining_today": max(daily_limit - usage.ask_count, 0),
            }
        )


class EngagementProfileView(APIView):
    """Expose streak and reminder preferences for mobile clients."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return current engagement profile snapshot."""
        profile = _get_engagement_profile(request.user)
        return Response(_serialize_engagement_profile(profile))

    def patch(self, request):
        """Update reminder settings and notification channel."""
        serializer = EngagementProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = _get_engagement_profile(request.user)
        changed = {}
        for field, value in serializer.validated_data.items():
            if getattr(profile, field) != value:
                setattr(profile, field, value)
                if hasattr(value, "isoformat"):
                    changed[field] = value.isoformat()
                else:
                    changed[field] = value
        if changed:
            profile.save(update_fields=[*changed.keys(), "updated_at"])
            _log_engagement_event(
                user=request.user,
                event_type=EngagementEvent.EVENT_REMINDER_PREF_UPDATED,
                metadata={"changed_fields": changed},
            )
        return Response(_serialize_engagement_profile(profile))


class AskView(APIView):
    """Main API endpoint: user prompt -> retrieval + guidance response."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Validate input, apply safety, and return grounded guidance."""
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if is_risky_prompt(data["message"]):
            _log_ask_event(
                user_id=request.user.get_username(),
                source=AskEvent.SOURCE_API,
                mode=data["mode"],
                outcome=AskEvent.OUTCOME_BLOCKED_SAFETY,
            )
            return _error_response(
                message=(
                    "This app cannot provide crisis or self-harm guidance, "
                    "or medical/legal decisions. Please contact local "
                    "emergency or professional support immediately."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                code="safety_blocked",
            )

        subscription, usage = _get_user_plan_and_usage(request.user)
        daily_limit = _plan_daily_limit(subscription.plan)
        if usage.ask_count >= daily_limit:
            _log_ask_event(
                user_id=request.user.get_username(),
                source=AskEvent.SOURCE_API,
                mode=data["mode"],
                outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                plan=subscription.plan,
            )
            return _error_response(
                message=(
                    "Daily ask limit reached for your plan. "
                    "Please upgrade to Pro or try again tomorrow."
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="quota_exceeded",
                extra={
                    "plan": subscription.plan,
                    "daily_limit": daily_limit,
                    "used_today": usage.ask_count,
                    "remaining_today": 0,
                },
            )

        conversation, verses, guidance, retrieval = _run_guidance_flow(
            user_id=request.user.get_username(),
            message=data["message"],
            mode=data["mode"],
            conversation_id=data.get("conversation_id"),
        )
        usage.ask_count += 1
        usage.save(update_fields=["ask_count"])
        engagement = _update_streak_for_today(request.user)
        _log_ask_event(
            user_id=request.user.get_username(),
            source=AskEvent.SOURCE_API,
            mode=data["mode"],
            outcome=AskEvent.OUTCOME_SERVED,
            response_mode=guidance.response_mode,
            retrieval_mode=retrieval.retrieval_mode,
            plan=subscription.plan,
        )

        response_data = {
            "conversation_id": conversation.id,
            "guidance": guidance.guidance,
            "verses": VerseSerializer(verses, many=True).data,
            "meaning": guidance.meaning,
            "actions": guidance.actions,
            "reflection": guidance.reflection,
            "verse_references": [
                f"{verse.chapter}.{verse.verse}" for verse in verses
            ],
            "plan": subscription.plan,
            "daily_limit": daily_limit,
            "used_today": usage.ask_count,
            "remaining_today": max(daily_limit - usage.ask_count, 0),
            "engagement": _serialize_engagement_profile(engagement),
        }
        follow_ups = _build_contextual_follow_ups(
            message=data["message"],
            mode=data["mode"],
            query_themes=retrieval.query_themes,
        )
        response_data["follow_ups"] = follow_ups
        _log_follow_up_events(
            user_id=request.user.get_username(),
            source=FollowUpEvent.SOURCE_API,
            event_type=FollowUpEvent.EVENT_SHOWN,
            mode=data["mode"],
            follow_ups=follow_ups,
        )
        if settings.DEBUG:
            response_data["response_mode"] = guidance.response_mode
            response_data["retrieval_mode"] = retrieval.retrieval_mode
            response_data["retrieved_references"] = [
                verse["reference"] for verse in response_data["verses"]
            ]
            response_data["retrieval_scores"] = retrieval.retrieval_scores
            response_data["query_themes"] = retrieval.query_themes
        return Response(response_data)


class FollowUpGenerateView(APIView):
    """Generate contextual continuation prompts for mobile/web clients."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Return deterministic follow-up prompts from query context."""
        serializer = FollowUpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        retrieval = retrieve_verses_with_trace(
            message=data["message"],
            limit=4 if data["mode"] == "deep" else 3,
        )
        follow_ups = _build_contextual_follow_ups(
            message=data["message"],
            mode=data["mode"],
            query_themes=retrieval.query_themes,
        )
        _log_follow_up_events(
            user_id=request.user.get_username(),
            source=FollowUpEvent.SOURCE_API,
            event_type=FollowUpEvent.EVENT_SHOWN,
            mode=data["mode"],
            follow_ups=follow_ups,
        )
        return Response(
            {
                "mode": data["mode"],
                "query_themes": retrieval.query_themes,
                "follow_ups": follow_ups,
            }
        )


class RetrievalEvalView(APIView):
    """Retrieval debugging endpoint without response generation."""

    @staticmethod
    def _serialize_trace(retrieval):
        """Serialize retrieval result object into API-safe JSON payload."""
        verse_data = VerseSerializer(retrieval.verses, many=True).data
        return {
            "retrieval_mode": retrieval.retrieval_mode,
            "retrieved_references": [
                verse["reference"] for verse in verse_data
            ],
            "retrieval_scores": retrieval.retrieval_scores,
            "query_themes": retrieval.query_themes,
            "query_tokens": retrieval.query_tokens,
            "verses": verse_data,
        }

    def post(self, request):
        """Return retrieval traces or side-by-side benchmark output."""
        serializer = RetrievalEvalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        limit = 4 if data["mode"] == "deep" else 3

        if data["mode"] == "benchmark":
            semantic = retrieve_semantic_verses_with_trace(
                message=data["message"],
                limit=limit,
            )
            hybrid = retrieve_hybrid_verses_with_trace(
                message=data["message"],
                limit=limit,
            )
            return Response(
                {
                    "mode": "benchmark",
                    "semantic": self._serialize_trace(semantic),
                    "hybrid": self._serialize_trace(hybrid),
                }
            )

        retrieval = retrieve_verses_with_trace(
            message=data["message"],
            limit=limit,
        )
        return Response(self._serialize_trace(retrieval))


class DailyVerseView(APIView):
    """Return a deterministic daily verse and short reflection."""

    def get(self, request):
        """Serve first available verse or seed fallback if empty DB."""
        verse = Verse.objects.order_by("chapter", "verse").first()
        if verse is None:
            verses = retrieve_verses("daily verse", limit=1)
            verse = verses[0]

        return Response(
            {
                "verse": VerseSerializer(verse).data,
                "reflection": (
                    "Do your work with sincerity today and release "
                    "attachment to outcomes."
                ),
            }
        )


class ConversationHistoryView(APIView):
    """Fetch most recent conversation timeline for a user."""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id: str):
        """Return ordered message list for the latest user session."""
        active_user_id = request.user.get_username()
        requested_user_id = active_user_id if user_id == "me" else user_id
        if requested_user_id != active_user_id:
            return _error_response(
                message="You can only access your own conversation history.",
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden_user_scope",
            )

        conversation = (
            Conversation.objects.filter(user_id=active_user_id)
            .order_by("-updated_at")
            .first()
        )
        if conversation is None:
            return Response({"user_id": active_user_id, "messages": []})

        messages = MessageSerializer(
            conversation.messages.all(),
            many=True,
        ).data
        return Response(
            {
                "user_id": active_user_id,
                "conversation_id": conversation.id,
                "messages": messages,
            }
        )


class FeedbackView(APIView):
    """Capture and browse user feedback on response quality."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return latest feedback entries for lightweight review."""
        try:
            limit, offset = _pagination_params(request)
        except ValueError:
            return _error_response(
                message="limit and offset must be integers.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_pagination",
            )
        user_id = request.user.get_username()
        base_qs = ResponseFeedback.objects.filter(user_id=user_id)
        entries = base_qs[offset:offset + limit]
        data = [
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "helpful": entry.helpful,
                "mode": entry.mode,
                "response_mode": entry.response_mode,
                "note": entry.note,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]
        total = base_qs.count()
        next_offset = offset + limit if (offset + limit) < total else None
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "results": data,
            }
        )

    def post(self, request):
        """Validate and persist one feedback event."""
        user_id = request.user.get_username()
        message = str(request.data.get("message", "")).strip()
        mode = str(request.data.get("mode", "simple")).strip()
        response_mode = (
            str(request.data.get("response_mode", "fallback")).strip()
        )
        helpful = request.data.get("helpful")
        note = str(request.data.get("note", "")).strip()
        conversation_id = request.data.get("conversation_id")

        if helpful in [True, False]:
            parsed_helpful = helpful
        elif str(helpful).lower() in {"true", "1", "yes"}:
            parsed_helpful = True
        elif str(helpful).lower() in {"false", "0", "no"}:
            parsed_helpful = False
        else:
            return _error_response(
                message="helpful must be true or false",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_helpful_value",
            )

        if mode not in {"simple", "deep"}:
            mode = "simple"
        if response_mode not in {"llm", "fallback"}:
            response_mode = "fallback"

        conversation = None
        if conversation_id:
            conversation = Conversation.objects.filter(
                id=conversation_id,
                user_id=user_id,
            ).first()

        entry = ResponseFeedback.objects.create(
            conversation=conversation,
            user_id=user_id,
            message=message,
            mode=mode,
            response_mode=response_mode,
            helpful=parsed_helpful,
            note=note,
        )
        return Response(
            {"id": entry.id, "status": "saved"},
            status=status.HTTP_201_CREATED,
        )


class SavedReflectionListCreateView(APIView):
    """Create and list saved reflections for authenticated users."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return user's saved reflections in reverse chronological order."""
        try:
            limit, offset = _pagination_params(request)
        except ValueError:
            return _error_response(
                message="limit and offset must be integers.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_pagination",
            )
        base_qs = SavedReflection.objects.filter(user=request.user)
        entries = base_qs[offset:offset + limit]
        total = base_qs.count()
        next_offset = offset + limit if (offset + limit) < total else None
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "results": SavedReflectionSerializer(entries, many=True).data,
            }
        )

    def post(self, request):
        """Save one reflection/bookmark from ask output payload."""
        serializer = SavedReflectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = None
        conversation_id = data.get("conversation_id")
        if conversation_id:
            conversation = Conversation.objects.filter(
                id=conversation_id,
                user_id=request.user.get_username(),
            ).first()

        entry = SavedReflection.objects.create(
            user=request.user,
            conversation=conversation,
            message=data["message"],
            guidance=data["guidance"],
            meaning=data.get("meaning", ""),
            actions=data.get("actions", []),
            reflection=data.get("reflection", ""),
            verse_references=data.get("verse_references", []),
            note=data.get("note", ""),
        )
        return Response(
            SavedReflectionSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class SavedReflectionDetailView(APIView):
    """Delete one saved reflection owned by current user."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, reflection_id: int):
        """Delete target saved reflection if it belongs to caller."""
        entry = SavedReflection.objects.filter(
            id=reflection_id,
            user=request.user,
        ).first()
        if entry is None:
            return _error_response(
                message="Saved reflection not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="saved_reflection_not_found",
            )
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatUIView(View):
    """Simple server-rendered page for manual API testing."""

    template_name = "guide_api/chat_ui.html"

    def get(self, request):
        """Render empty chat form."""
        default_user_id = self._default_user_id(request)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "",
                "selected_plan": "free",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    default_user_id,
                ),
                "user_id": default_user_id,
                "mode": "simple",
                "message": "",
            },
        )

    def post(self, request):
        """Handle ask or feedback submit action from HTML form."""
        action = request.POST.get("action", "ask").strip()
        if action == "register":
            return self._handle_register(request)
        if action == "login":
            return self._handle_login(request)
        if action == "logout":
            return self._handle_logout(request)
        if action == "feedback":
            return self._handle_feedback(request)
        if action == "plan":
            return self._handle_plan_update(request)
        if action == "save":
            return self._handle_save_reflection(request)

        starter_prompts = self._starter_prompts()
        recent_questions = self._recent_questions(request)

        user_id = (
            request.POST.get("user_id", self._default_user_id(request)).strip()
            or self._default_user_id(request)
        )
        message = request.POST.get("message", "").strip()
        mode = request.POST.get("mode", "simple")
        follow_up_intent = request.POST.get("follow_up_intent", "").strip()

        if mode not in {"simple", "deep"}:
            mode = "simple"

        if not message:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Please enter a message to continue.",
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": mode,
                    "message": message,
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

        if is_risky_prompt(message):
            _log_ask_event(
                user_id=user_id,
                source=AskEvent.SOURCE_CHAT_UI,
                mode=mode,
                outcome=AskEvent.OUTCOME_BLOCKED_SAFETY,
                plan=UserSubscription.PLAN_FREE,
            )
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "This app cannot provide crisis/self-harm or "
                        "medical/legal guidance. Please seek local "
                        "professional support "
                        "immediately."
                    ),
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": mode,
                    "message": message,
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

        quota = self._resolve_chat_ui_quota(user_id)
        if quota and quota["usage"].ask_count >= quota["daily_limit"]:
            _log_ask_event(
                user_id=user_id,
                source=AskEvent.SOURCE_CHAT_UI,
                mode=mode,
                outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                plan=quota["subscription"].plan,
            )
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Daily ask limit reached for this user plan "
                        "in chat UI. "
                        "Switch to Pro or try tomorrow."
                    ),
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": mode,
                    "message": message,
                    "selected_plan": quota["subscription"].plan,
                    "quota_snapshot": {
                        "plan": quota["subscription"].plan,
                        "daily_limit": quota["daily_limit"],
                        "used_today": quota["usage"].ask_count,
                        "remaining_today": 0,
                    },
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

        conversation, verses, guidance, retrieval = _run_guidance_flow(
            user_id=user_id,
            message=message,
            mode=mode,
        )
        response_data = {
            "conversation_id": conversation.id,
            "guidance": guidance.guidance,
            "verses": VerseSerializer(verses, many=True).data,
            "meaning": guidance.meaning,
            "actions": guidance.actions,
            "reflection": guidance.reflection,
            "verse_references": [
                f"{verse.chapter}.{verse.verse}" for verse in verses
            ],
        }
        follow_ups = _build_contextual_follow_ups(
            message=message,
            mode=mode,
            query_themes=retrieval.query_themes,
        )
        response_data["follow_ups"] = follow_ups
        _log_follow_up_events(
            user_id=user_id,
            source=FollowUpEvent.SOURCE_CHAT_UI,
            event_type=FollowUpEvent.EVENT_SHOWN,
            mode=mode,
            follow_ups=follow_ups,
        )
        if follow_up_intent:
            _log_follow_up_events(
                user_id=user_id,
                source=FollowUpEvent.SOURCE_CHAT_UI,
                event_type=FollowUpEvent.EVENT_CLICKED,
                mode=mode,
                follow_ups=[
                    {
                        "intent": follow_up_intent,
                        "prompt": message,
                    }
                ],
            )
        if quota:
            quota["usage"].ask_count += 1
            quota["usage"].save(update_fields=["ask_count"])
            response_data["plan"] = quota["subscription"].plan
            response_data["daily_limit"] = quota["daily_limit"]
            response_data["used_today"] = quota["usage"].ask_count
            response_data["remaining_today"] = max(
                quota["daily_limit"] - quota["usage"].ask_count,
                0,
            )
        _log_ask_event(
            user_id=user_id,
            source=AskEvent.SOURCE_CHAT_UI,
            mode=mode,
            outcome=AskEvent.OUTCOME_SERVED,
            response_mode=guidance.response_mode,
            retrieval_mode=retrieval.retrieval_mode,
            plan=(
                quota["subscription"].plan
                if quota
                else UserSubscription.PLAN_FREE
            ),
        )
        if settings.DEBUG:
            response_data["response_mode"] = guidance.response_mode
            response_data["retrieval_mode"] = retrieval.retrieval_mode
            response_data["retrieved_references"] = [
                verse["reference"] for verse in response_data["verses"]
            ]
            response_data["retrieval_scores"] = retrieval.retrieval_scores
            response_data["query_themes"] = retrieval.query_themes

        self._store_recent_question(request, message)
        updated_recent_questions = self._recent_questions(request)

        return render(
            request,
            self.template_name,
            {
                "response_data": response_data,
                "error": "",
                "feedback_message": "",
                "user_id": user_id,
                "mode": mode,
                "message": message,
                "selected_plan": (
                    response_data.get("plan")
                    if response_data.get("plan")
                    else "free"
                ),
                "quota_snapshot": {
                    "plan": response_data.get("plan", "free"),
                    "daily_limit": response_data.get("daily_limit", "N/A"),
                    "used_today": response_data.get("used_today", "N/A"),
                    "remaining_today": response_data.get(
                        "remaining_today",
                        "N/A",
                    ),
                },
                "starter_prompts": starter_prompts,
                "recent_questions": updated_recent_questions,
                "follow_up_prompts": response_data.get("follow_ups", []),
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user_id,
                ),
            },
        )

    def _handle_feedback(self, request):
        """Persist feedback submitted via manual chat UI."""
        user_id = (
            request.POST.get("user_id", self._default_user_id(request)).strip()
            or self._default_user_id(request)
        )
        message = request.POST.get("message", "").strip()
        mode = request.POST.get("mode", "simple").strip()
        response_mode = request.POST.get("response_mode", "fallback").strip()
        note = request.POST.get("note", "").strip()
        helpful_value = request.POST.get("helpful", "").strip().lower()
        conversation_id = request.POST.get("conversation_id")

        helpful = helpful_value == "true"
        if helpful_value not in {"true", "false"}:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Invalid feedback value.",
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": mode,
                    "message": message,
                },
            )

        if mode not in {"simple", "deep"}:
            mode = "simple"
        if response_mode not in {"llm", "fallback"}:
            response_mode = "fallback"

        conversation = None
        if conversation_id:
            conversation = Conversation.objects.filter(
                id=conversation_id,
                user_id=user_id,
            ).first()

        ResponseFeedback.objects.create(
            conversation=conversation,
            user_id=user_id,
            message=message,
            mode=mode,
            response_mode=response_mode,
            helpful=helpful,
            note=note,
        )

        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Thank you. Your feedback was saved.",
                "user_id": user_id,
                "mode": mode,
                "message": message,
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
            },
        )

    def _handle_save_reflection(self, request):
        """Save current response into bookmarks for existing usernames."""
        user_id = (
            request.POST.get("user_id", self._default_user_id(request)).strip()
            or self._default_user_id(request)
        )
        user_model = get_user_model()
        user = user_model.objects.filter(username=user_id).first()
        if user is None:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Saving reflections requires an existing auth user. "
                        "Create/login user first."
                    ),
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": request.POST.get("mode", "simple"),
                    "message": request.POST.get("message", ""),
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": [],
                },
            )

        conversation = None
        conversation_id = request.POST.get("conversation_id")
        if conversation_id and str(conversation_id).isdigit():
            conversation = Conversation.objects.filter(
                id=int(conversation_id),
                user_id=user.get_username(),
            ).first()

        actions_raw = request.POST.get("actions", "")
        actions = [
            item.strip() for item in actions_raw.split("|") if item.strip()
        ]
        refs_raw = request.POST.get("verse_references", "")
        verse_references = [
            item.strip() for item in refs_raw.split("|") if item.strip()
        ]

        SavedReflection.objects.create(
            user=user,
            conversation=conversation,
            message=request.POST.get("message", "").strip(),
            guidance=request.POST.get("guidance", "").strip(),
            meaning=request.POST.get("meaning", "").strip(),
            actions=actions,
            reflection=request.POST.get("reflection", "").strip(),
            verse_references=verse_references,
            note=request.POST.get("note", "").strip(),
        )
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Reflection saved.",
                "user_id": user_id,
                "mode": request.POST.get("mode", "simple"),
                "message": request.POST.get("message", ""),
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user_id,
                ),
            },
        )

    @staticmethod
    def _saved_reflections_for_user(request, user_id: str) -> list[dict]:
        """Return last saved reflections for a known username."""
        user_model = get_user_model()
        user = user_model.objects.filter(username=user_id).first()
        if user is None:
            return []
        rows = SavedReflection.objects.filter(user=user)[:5]
        return [
            {
                "id": row.id,
                "message": row.message,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    def _resolve_chat_ui_quota(self, user_id: str):
        """Return quota context when chat-ui user maps to a real auth user."""
        user_model = get_user_model()
        user = user_model.objects.filter(username=user_id).first()
        if user is None:
            return None
        subscription, usage = _get_user_plan_and_usage(user)
        return {
            "subscription": subscription,
            "usage": usage,
            "daily_limit": _plan_daily_limit(subscription.plan),
        }

    def _handle_plan_update(self, request):
        """Allow chat-ui testers to switch plan for known usernames."""
        user_id = (
            request.POST.get("user_id", self._default_user_id(request)).strip()
            or self._default_user_id(request)
        )
        selected_plan = request.POST.get("selected_plan", "free").strip()
        if selected_plan not in {
            UserSubscription.PLAN_FREE,
            UserSubscription.PLAN_PRO,
        }:
            selected_plan = UserSubscription.PLAN_FREE
        quota = self._resolve_chat_ui_quota(user_id)
        if quota is None:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Plan update works only for existing auth usernames. "
                        "Create/login user first."
                    ),
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": request.POST.get("mode", "simple"),
                    "message": request.POST.get("message", ""),
                    "selected_plan": selected_plan,
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )

        subscription = quota["subscription"]
        subscription.plan = selected_plan
        subscription.save(update_fields=["plan", "updated_at"])
        refreshed = self._resolve_chat_ui_quota(user_id)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": f"Plan updated to {selected_plan}.",
                "user_id": user_id,
                "mode": request.POST.get("mode", "simple"),
                "message": request.POST.get("message", ""),
                "selected_plan": selected_plan,
                "quota_snapshot": {
                    "plan": selected_plan,
                    "daily_limit": refreshed["daily_limit"],
                    "used_today": refreshed["usage"].ask_count,
                    "remaining_today": max(
                        refreshed["daily_limit"]
                        - refreshed["usage"].ask_count,
                        0,
                    ),
                },
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
            },
        )

    def _handle_register(self, request):
        """Register user from chat-ui panel and persist session token."""
        username = str(request.POST.get("register_username", "")).strip()
        password = str(request.POST.get("register_password", "")).strip()
        if not username or not password:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Please enter username and password to register.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        if len(password) < 8:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Password must be at least 8 characters.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Username is already taken.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        user = user_model.objects.create_user(
            username=username,
            password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        request.session["chat_ui_auth_username"] = user.username
        request.session["chat_ui_auth_token"] = token.key
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": (
                    f"Registered and logged in as {user.username}."
                ),
                "user_id": user.username,
                "mode": "simple",
                "message": "",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user.username,
                ),
            },
        )

    def _handle_login(self, request):
        """Authenticate user from chat-ui and persist auth session values."""
        username = str(request.POST.get("login_username", "")).strip()
        password = str(request.POST.get("login_password", "")).strip()
        user = authenticate(
            request=request,
            username=username,
            password=password,
        )
        if user is None:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Invalid username or password.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        token, _ = Token.objects.get_or_create(user=user)
        request.session["chat_ui_auth_username"] = user.username
        request.session["chat_ui_auth_token"] = token.key
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": f"Logged in as {user.username}.",
                "user_id": user.username,
                "mode": "simple",
                "message": "",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user.username,
                ),
            },
        )

    def _handle_logout(self, request):
        """Logout chat-ui user by clearing stored session token."""
        token_key = request.session.get("chat_ui_auth_token")
        if token_key:
            Token.objects.filter(key=token_key).delete()
        request.session.pop("chat_ui_auth_username", None)
        request.session.pop("chat_ui_auth_token", None)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Logged out.",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    "demo-user",
                ),
            },
        )

    @staticmethod
    def _default_user_id(request) -> str:
        """Resolve default chat-ui user from session fallback."""
        return str(request.session.get("chat_ui_auth_username", "demo-user"))

    @staticmethod
    def _starter_prompts() -> list[str]:
        """Return curated first-question prompts for quick onboarding."""
        return [
            "I feel anxious about my career growth and future.",
            "I get angry quickly in relationships. How can I respond better?",
            "I feel stuck and directionless. How do I find purpose?",
            "I procrastinate and lose discipline. What should I do daily?",
        ]

    @staticmethod
    def _follow_up_prompts() -> list[str]:
        """Return actionable follow-up prompts shown after each response."""
        return [
            "Give me a 3-step plan for today based on these verses.",
            "Explain one verse in simpler words for my situation.",
            "Ask me one reflection question to continue this conversation.",
        ]

    @staticmethod
    def _recent_questions(request) -> list[str]:
        """Read the latest chat-ui questions from session state."""
        items = request.session.get("chat_ui_recent_questions", [])
        if isinstance(items, list):
            return [str(item) for item in items[:3]]
        return []

    @staticmethod
    def _store_recent_question(request, message: str) -> None:
        """Store most recent unique questions for one-click reuse."""
        message = message.strip()
        if not message:
            return
        existing = request.session.get("chat_ui_recent_questions", [])
        if not isinstance(existing, list):
            existing = []
        updated = [message] + [item for item in existing if item != message]
        request.session["chat_ui_recent_questions"] = updated[:3]
