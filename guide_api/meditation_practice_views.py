"""
REST API for the extensible Meditation / Sadhana Practice Library.

Endpoints
---------
GET  /api/v1/meditation/types/
GET  /api/v1/meditation/types/<slug>/
GET  /api/v1/meditation/types/<slug>/contents/
POST /api/v1/meditation/sessions/start/
POST /api/v1/meditation/sessions/<pk>/complete/
POST /api/v1/meditation/sessions/<pk>/interrupt/
GET  /api/v1/meditation/sessions/recent/
GET  /api/v1/meditation/insights/

Access levels
-------------
free     → any authenticated user
plus     → PLAN_PLUS or PLAN_PRO
pro      → PLAN_PRO only
purchase → user has a valid MeditationContentUnlock row

Only practice-mode completed sessions count toward sadhana insights.
Learn-only sessions are stored but flagged separately.
"""
from __future__ import annotations

from django.utils import timezone

from rest_framework import serializers, status
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from guide_api.models import (
    MeditationContentUnlock,
    MeditationPracticeContent,
    MeditationPracticeSession,
    MeditationPracticeType,
    UserSubscription,
)
from guide_api.subscription_helpers import normalize_subscription_state


# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_user_plan(user) -> str:
    """Return user plan string ('free', 'plus', 'pro').  Safe for anonymous."""
    if user is None or not getattr(user, "is_authenticated", False):
        return UserSubscription.PLAN_FREE
    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={"plan": UserSubscription.PLAN_FREE},
    )
    sub = normalize_subscription_state(sub)
    return sub.plan


def _plan_rank(plan: str) -> int:
    return {"free": 0, "plus": 1, "pro": 2}.get(plan, 0)


def _content_access(content: MeditationPracticeContent, user) -> dict:
    """Return access info dict for a content item."""
    level = content.access_level
    plan = _get_user_plan(user)

    if level == MeditationPracticeContent.ACCESS_FREE:
        return {"locked": False, "locked_reason": None, "required_plan": None,
                "purchase_required": False, "can_play": True, "can_practice": True}

    if level == MeditationPracticeContent.ACCESS_PLUS:
        unlocked = _plan_rank(plan) >= _plan_rank("plus")
        reason = None if unlocked else "Requires Plus+ subscription"
        return {"locked": not unlocked, "locked_reason": reason,
                "required_plan": "plus", "purchase_required": False,
                "can_play": unlocked, "can_practice": unlocked}

    if level == MeditationPracticeContent.ACCESS_PRO:
        unlocked = plan == UserSubscription.PLAN_PRO
        reason = None if unlocked else "Requires Pro subscription"
        return {"locked": not unlocked, "locked_reason": reason,
                "required_plan": "pro", "purchase_required": False,
                "can_play": unlocked, "can_practice": unlocked}

    if level == MeditationPracticeContent.ACCESS_PURCHASE:
        if user and getattr(user, "is_authenticated", False):
            unlock = (
                MeditationContentUnlock.objects
                .filter(user=user, content=content)
                .first()
            )
            if unlock and unlock.is_valid():
                return {"locked": False, "locked_reason": None,
                        "required_plan": None, "purchase_required": False,
                        "can_play": True, "can_practice": True}
        inr = content.purchase_price_minor_inr
        usd = content.purchase_price_minor_usd
        return {
            "locked": True,
            "locked_reason": "One-time purchase required",
            "required_plan": None,
            "purchase_required": True,
            "purchase_price_inr": inr,
            "purchase_price_usd": usd,
            "can_play": False,
            "can_practice": False,
        }

    # Fallback — treat as free
    return {"locked": False, "locked_reason": None, "required_plan": None,
            "purchase_required": False, "can_play": True, "can_practice": True}


def _type_access_for_user(practice_type: MeditationPracticeType, user) -> dict:
    """Access check at the practice-type level."""
    level = practice_type.default_access_level
    plan = _get_user_plan(user)

    if level == MeditationPracticeType.ACCESS_FREE:
        return {"locked": False, "locked_reason": None, "required_plan": None}
    if level == MeditationPracticeType.ACCESS_PLUS:
        unlocked = _plan_rank(plan) >= _plan_rank("plus")
        return {
            "locked": not unlocked,
            "locked_reason": None if unlocked else "Requires Plus+ subscription",
            "required_plan": "plus",
        }
    if level == MeditationPracticeType.ACCESS_PRO:
        unlocked = plan == UserSubscription.PLAN_PRO
        return {
            "locked": not unlocked,
            "locked_reason": None if unlocked else "Requires Pro subscription",
            "required_plan": "pro",
        }
    return {"locked": False, "locked_reason": None, "required_plan": None}


# ─── serializers ──────────────────────────────────────────────────────────────

class MeditationPracticeTypeListSerializer(serializers.ModelSerializer):
    locked = serializers.SerializerMethodField()
    locked_reason = serializers.SerializerMethodField()
    required_plan = serializers.SerializerMethodField()
    content_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = MeditationPracticeType
        fields = [
            "slug", "title", "subtitle", "category",
            "icon_url", "cover_url", "default_access_level",
            "counts_as_sadhana", "sort_order",
            "locked", "locked_reason", "required_plan",
            "content_count",
        ]

    def _access(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return _type_access_for_user(obj, user)

    def get_locked(self, obj): return self._access(obj)["locked"]
    def get_locked_reason(self, obj): return self._access(obj)["locked_reason"]
    def get_required_plan(self, obj): return self._access(obj)["required_plan"]

    def get_content_count(self, obj):
        return obj.contents.filter(is_active=True).count()

    def get_cover_url(self, obj):
        """Return cover_url (external CDN) if set, else build absolute URL from uploaded cover_image."""
        if obj.cover_url:
            return obj.cover_url
        if obj.cover_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
            return obj.cover_image.url
        return None


class MeditationPracticeTypeDetailSerializer(MeditationPracticeTypeListSerializer):
    class Meta(MeditationPracticeTypeListSerializer.Meta):
        fields = MeditationPracticeTypeListSerializer.Meta.fields + [
            "description",
        ]


class MeditationPracticeContentSerializer(serializers.ModelSerializer):
    locked = serializers.SerializerMethodField()
    locked_reason = serializers.SerializerMethodField()
    required_plan = serializers.SerializerMethodField()
    purchase_required = serializers.SerializerMethodField()
    purchase_price_inr = serializers.SerializerMethodField()
    purchase_price_usd = serializers.SerializerMethodField()
    can_play = serializers.SerializerMethodField()
    can_practice = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = MeditationPracticeContent
        fields = [
            "id", "title", "subtitle", "description",
            "content_type", "thumbnail_url",
            "duration_seconds", "duration_minutes",
            "language", "teacher", "mantra_name",
            "supports_loop", "mode", "access_level",
            "sort_order",
            # access fields
            "locked", "locked_reason", "required_plan",
            "purchase_required", "purchase_price_inr", "purchase_price_usd",
            "can_play", "can_practice",
            # media only when user can play
            "media_url",
        ]

    def _access(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return _content_access(obj, user)

    def get_locked(self, obj): return self._access(obj)["locked"]
    def get_locked_reason(self, obj): return self._access(obj)["locked_reason"]
    def get_required_plan(self, obj): return self._access(obj)["required_plan"]
    def get_purchase_required(self, obj): return self._access(obj)["purchase_required"]
    def get_purchase_price_inr(self, obj): return self._access(obj).get("purchase_price_inr")
    def get_purchase_price_usd(self, obj): return self._access(obj).get("purchase_price_usd")
    def get_can_play(self, obj): return self._access(obj)["can_play"]
    def get_can_practice(self, obj): return self._access(obj)["can_practice"]

    def get_duration_minutes(self, obj):
        if obj.duration_seconds:
            return round(obj.duration_seconds / 60, 1)
        return None

    def get_media_url(self, obj):
        # Only return media URL if user can actually play
        if self._access(obj)["can_play"]:
            return obj.media_url
        return None


class MeditationSessionStartSerializer(serializers.Serializer):
    practice_type_slug = serializers.SlugField(max_length=96)
    content_id = serializers.IntegerField(required=False, allow_null=True)
    mode = serializers.ChoiceField(
        choices=["learn", "practice"],
        default="practice",
    )
    # Pre-session optional details
    intention = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    chosen_mantra = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    target_duration_seconds = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    target_count = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    used_mala = serializers.BooleanField(required=False, allow_null=True, default=None)
    mood_before = serializers.ChoiceField(
        choices=["1", "2", "3", "4", "5"],
        required=False,
        allow_blank=True,
        default="",
    )


class MeditationSessionCompleteSerializer(serializers.Serializer):
    tracked_seconds = serializers.IntegerField(min_value=0, default=0)
    mood_after = serializers.ChoiceField(
        choices=["1", "2", "3", "4", "5"],
        required=False,
        allow_blank=True,
        default="",
    )
    presence_rating = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)
    chanting_mode = serializers.ChoiceField(
        choices=["aloud", "whisper", "mental", "listen_along", "mixed"],
        required=False,
        allow_blank=True,
        default="",
    )
    actual_count = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    helpful = serializers.BooleanField(required=False, allow_null=True, default=None)
    internal_observation = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    reflection_note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class MeditationSessionInterruptSerializer(serializers.Serializer):
    tracked_seconds = serializers.IntegerField(min_value=0, default=0)


class MeditationSessionSummarySerializer(serializers.ModelSerializer):
    practice_type_slug = serializers.CharField(source="practice_type.slug")
    practice_type_title = serializers.CharField(source="practice_type.title")
    content_title = serializers.SerializerMethodField()

    class Meta:
        model = MeditationPracticeSession
        fields = [
            "id", "practice_type_slug", "practice_type_title",
            "content_title", "mode", "status",
            "started_at", "ended_at",
            "duration_seconds", "tracked_seconds",
            "intention", "chosen_mantra",
            "mood_before", "mood_after",
            "presence_rating", "chanting_mode",
            "actual_count", "helpful",
            "internal_observation", "reflection_note",
        ]

    def get_content_title(self, obj):
        return obj.content.title if obj.content_id else None


# ─── views ────────────────────────────────────────────────────────────────────

class MeditationPracticeTypeListView(APIView):
    """GET /api/v1/meditation/types/ — list all active practice types."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MeditationPracticeType.objects.filter(is_active=True)
        data = MeditationPracticeTypeListSerializer(
            qs, many=True, context={"request": request}
        ).data
        return Response({"results": data, "count": len(data)})


class MeditationPracticeTypeDetailView(APIView):
    """GET /api/v1/meditation/types/<slug>/ — detail + content list."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            obj = MeditationPracticeType.objects.get(slug=slug, is_active=True)
        except MeditationPracticeType.DoesNotExist:
            return Response({"error": {"message": "Practice type not found.", "code": "NOT_FOUND"}},
                            status=status.HTTP_404_NOT_FOUND)
        data = MeditationPracticeTypeDetailSerializer(obj, context={"request": request}).data
        return Response(data)


class MeditationPracticeContentsView(APIView):
    """GET /api/v1/meditation/types/<slug>/contents/ — content list for a practice type."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            practice_type = MeditationPracticeType.objects.get(slug=slug, is_active=True)
        except MeditationPracticeType.DoesNotExist:
            return Response({"error": {"message": "Practice type not found.", "code": "NOT_FOUND"}},
                            status=status.HTTP_404_NOT_FOUND)
        mode_filter = request.query_params.get("mode")  # learn / practice / both
        qs = practice_type.contents.filter(is_active=True)
        if mode_filter in ("learn", "practice"):
            qs = qs.filter(mode__in=[mode_filter, "both"])
        data = MeditationPracticeContentSerializer(
            qs, many=True, context={"request": request}
        ).data
        return Response({"results": data, "count": len(data)})


class MeditationSessionStartView(APIView):
    """POST /api/v1/meditation/sessions/start/"""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = MeditationSessionStartSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"error": {"message": "Validation error.", "code": "VALIDATION_ERROR"},
                 "details": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        d = ser.validated_data

        try:
            practice_type = MeditationPracticeType.objects.get(
                slug=d["practice_type_slug"], is_active=True
            )
        except MeditationPracticeType.DoesNotExist:
            return Response(
                {"error": {"message": "Practice type not found.", "code": "NOT_FOUND"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        content = None
        if d.get("content_id"):
            try:
                content = MeditationPracticeContent.objects.get(
                    pk=d["content_id"], practice_type=practice_type, is_active=True
                )
                access = _content_access(content, request.user)
                if access["locked"]:
                    return Response(
                        {"error": {"message": access["locked_reason"] or "Content locked.",
                                   "code": "FORBIDDEN"}},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except MeditationPracticeContent.DoesNotExist:
                return Response(
                    {"error": {"message": "Content not found.", "code": "NOT_FOUND"}},
                    status=status.HTTP_404_NOT_FOUND,
                )

        session = MeditationPracticeSession.objects.create(
            user=request.user,
            practice_type=practice_type,
            content=content,
            mode=d["mode"],
            status=MeditationPracticeSession.STATUS_STARTED,
            started_at=timezone.now(),
            intention=d.get("intention", ""),
            chosen_mantra=d.get("chosen_mantra", ""),
            target_duration_seconds=d.get("target_duration_seconds"),
            target_count=d.get("target_count"),
            used_mala=d.get("used_mala"),
            mood_before=d.get("mood_before", ""),
        )
        return Response(
            {"session_id": session.pk, "started_at": session.started_at.isoformat()},
            status=status.HTTP_201_CREATED,
        )


class MeditationSessionCompleteView(APIView):
    """POST /api/v1/meditation/sessions/<pk>/complete/"""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            session = MeditationPracticeSession.objects.get(pk=pk, user=request.user)
        except MeditationPracticeSession.DoesNotExist:
            return Response(
                {"error": {"message": "Session not found.", "code": "NOT_FOUND"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if session.status == MeditationPracticeSession.STATUS_COMPLETED:
            return Response({"ok": True, "already_completed": True})

        ser = MeditationSessionCompleteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"error": {"message": "Validation error.", "code": "VALIDATION_ERROR"},
                 "details": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        d = ser.validated_data

        now = timezone.now()
        tracked = d.get("tracked_seconds", 0)
        elapsed = int((now - session.started_at).total_seconds())

        session.status = MeditationPracticeSession.STATUS_COMPLETED
        session.ended_at = now
        session.duration_seconds = elapsed
        session.tracked_seconds = tracked
        session.mood_after = d.get("mood_after", "")
        session.presence_rating = d.get("presence_rating")
        session.chanting_mode = d.get("chanting_mode", "")
        session.actual_count = d.get("actual_count")
        session.helpful = d.get("helpful")
        session.internal_observation = d.get("internal_observation", "")
        session.reflection_note = d.get("reflection_note", "")
        session.save()

        return Response({
            "ok": True,
            "session_id": session.pk,
            "mode": session.mode,
            "tracked_seconds": session.tracked_seconds,
            "counts_as_sadhana": (
                session.mode == MeditationPracticeSession.MODE_PRACTICE
                and session.practice_type.counts_as_sadhana
            ),
        })


class MeditationSessionInterruptView(APIView):
    """POST /api/v1/meditation/sessions/<pk>/interrupt/
    Called when user navigates away / app goes to background mid-session.
    Saves partial data safely; session can be referenced for insights.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            session = MeditationPracticeSession.objects.get(pk=pk, user=request.user)
        except MeditationPracticeSession.DoesNotExist:
            return Response(
                {"error": {"message": "Session not found.", "code": "NOT_FOUND"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if session.status != MeditationPracticeSession.STATUS_STARTED:
            return Response({"ok": True, "already_ended": True})

        ser = MeditationSessionInterruptSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"error": {"message": "Validation error.", "code": "VALIDATION_ERROR"},
                 "details": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        d = ser.validated_data

        now = timezone.now()
        session.status = MeditationPracticeSession.STATUS_INTERRUPTED
        session.ended_at = now
        session.duration_seconds = int((now - session.started_at).total_seconds())
        session.tracked_seconds = d.get("tracked_seconds", 0)
        session.save(update_fields=[
            "status", "ended_at", "duration_seconds", "tracked_seconds", "updated_at",
        ])
        return Response({"ok": True, "session_id": session.pk})


class MeditationSessionRecentView(APIView):
    """GET /api/v1/meditation/sessions/recent/?limit=20"""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 20)), 50)
        qs = (
            MeditationPracticeSession.objects
            .filter(user=request.user)
            .select_related("practice_type", "content")
            .order_by("-started_at")[:limit]
        )
        data = MeditationSessionSummarySerializer(qs, many=True).data
        return Response({"results": data, "count": len(data)})


class MeditationInsightsView(APIView):
    """GET /api/v1/meditation/insights/ — aggregated personal stats."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Avg, Count, Sum

        practice_qs = MeditationPracticeSession.objects.filter(user=request.user)
        completed_practice = practice_qs.filter(
            mode=MeditationPracticeSession.MODE_PRACTICE,
            status=MeditationPracticeSession.STATUS_COMPLETED,
        )
        completed_learn = practice_qs.filter(
            mode=MeditationPracticeSession.MODE_LEARN,
            status=MeditationPracticeSession.STATUS_COMPLETED,
        )

        stats = completed_practice.aggregate(
            total_sessions=Count("id"),
            total_tracked_seconds=Sum("tracked_seconds"),
            avg_presence=Avg("presence_rating"),
        )

        # Most practiced mantra
        top_mantra = (
            completed_practice.filter(chosen_mantra__gt="")
            .values("chosen_mantra")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )

        # Mood delta (avg after - avg before where both present)
        mood_sessions = completed_practice.filter(
            mood_before__gt="", mood_after__gt=""
        ).values_list("mood_before", "mood_after")
        mood_delta = None
        if mood_sessions.exists():
            deltas = [int(b) - int(a) for a, b in mood_sessions]
            mood_delta = round(sum(deltas) / len(deltas), 2)

        # Per practice-type breakdown
        by_type = list(
            completed_practice.values(
                "practice_type__slug", "practice_type__title"
            ).annotate(
                sessions=Count("id"),
                tracked_seconds=Sum("tracked_seconds"),
                total_malas=Sum("actual_count"),
            ).order_by("-sessions")
        )

        return Response({
            "practice_sessions_completed": stats["total_sessions"] or 0,
            "learn_sessions_completed": completed_learn.count(),
            "total_tracked_minutes": round((stats["total_tracked_seconds"] or 0) / 60, 1),
            "avg_presence_rating": round(stats["avg_presence"], 2) if stats["avg_presence"] else None,
            "top_mantra": top_mantra["chosen_mantra"] if top_mantra else None,
            "avg_mood_improvement": mood_delta,
            "by_practice_type": by_type,
        })


class MeditationTypeInsightsView(APIView):
    """GET /api/v1/meditation/insights/<slug>/ — per-practice-type drill-down."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        from django.db.models import Avg, Count, Sum

        try:
            practice_type = MeditationPracticeType.objects.get(slug=slug, is_active=True)
        except MeditationPracticeType.DoesNotExist:
            return Response(
                {"error": "NOT_FOUND", "message": "Practice type not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        completed = MeditationPracticeSession.objects.filter(
            user=request.user,
            practice_type=practice_type,
            mode=MeditationPracticeSession.MODE_PRACTICE,
            status=MeditationPracticeSession.STATUS_COMPLETED,
        )

        agg = completed.aggregate(
            total_sessions=Count("id"),
            total_tracked_seconds=Sum("tracked_seconds"),
            avg_presence=Avg("presence_rating"),
            total_malas=Sum("actual_count"),
        )

        # Mood delta
        mood_sessions = completed.filter(
            mood_before__gt="", mood_after__gt=""
        ).values_list("mood_before", "mood_after")
        mood_delta = None
        if mood_sessions.exists():
            deltas = [int(b) - int(a) for a, b in mood_sessions]
            mood_delta = round(sum(deltas) / len(deltas), 2)

        # Per-content breakdown
        by_content = [
            {
                "content_id": row["content__id"],
                "content_title": row["content__title"] or "Free practice",
                "sessions": row["sessions"],
                "tracked_minutes": round((row["tracked_seconds"] or 0) / 60, 1),
                "total_malas": row["total_malas"] or 0,
            }
            for row in (
                completed
                .values("content__id", "content__title")
                .annotate(
                    sessions=Count("id"),
                    tracked_seconds=Sum("tracked_seconds"),
                    total_malas=Sum("actual_count"),
                )
                .order_by("-sessions")
            )
        ]

        # Chanting mode distribution
        chanting_dist = list(
            completed.filter(chanting_mode__gt="")
            .values("chanting_mode")
            .annotate(sessions=Count("id"))
            .order_by("-sessions")
        )
        top_chanting_mode = chanting_dist[0]["chanting_mode"] if chanting_dist else None

        # Recent sessions (last 10)
        recent_qs = (
            completed.select_related("content", "practice_type")
            .order_by("-started_at")[:10]
        )
        recent_data = MeditationSessionSummarySerializer(recent_qs, many=True).data

        return Response({
            "practice_type_slug": practice_type.slug,
            "practice_type_title": practice_type.title,
            "sessions": agg["total_sessions"] or 0,
            "total_tracked_minutes": round((agg["total_tracked_seconds"] or 0) / 60, 1),
            "avg_presence_rating": round(agg["avg_presence"], 2) if agg["avg_presence"] else None,
            "total_malas": agg["total_malas"] or 0,
            "avg_mood_improvement": mood_delta,
            "top_chanting_mode": top_chanting_mode,
            "by_content": by_content,
            "chanting_mode_distribution": chanting_dist,
            "recent_sessions": recent_data,
        })
