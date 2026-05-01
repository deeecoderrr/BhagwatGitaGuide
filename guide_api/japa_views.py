"""REST APIs for user-defined japa / mālā commitments (personal sankalpa, not SadhanaProgram)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from guide_api.models import (
    JapaCommitment,
    JapaDailyCompletion,
    JapaSession,
    PracticeLogEntry,
)
from guide_api.serializers import (
    JapaCommitmentCreateSerializer,
    JapaCommitmentPatchSerializer,
    JapaFinishDaySerializer,
)


def _err(*, message: str, status_code: int, code: str) -> Response:
    return Response(
        {"error": {"code": code, "message": message}, "detail": message},
        status=status_code,
    )


def _commitment_dict(c: JapaCommitment) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "focus_label": c.focus_label,
        "mantra_label": c.mantra_label,
        "daily_target_malas": c.daily_target_malas,
        "started_on": c.started_on.isoformat(),
        "ends_on": c.ends_on.isoformat() if c.ends_on else None,
        "preferred_time": c.preferred_time.isoformat() if c.preferred_time else None,
        "status": c.status,
        "fulfilled_at": c.fulfilled_at.isoformat() if c.fulfilled_at else None,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def _session_dict(s: JapaSession) -> dict:
    return {
        "id": s.id,
        "commitment_id": s.commitment_id,
        "started_at": s.started_at.isoformat(),
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "pause_started_at": s.pause_started_at.isoformat() if s.pause_started_at else None,
        "paused_seconds": s.paused_seconds,
        "reported_malas": s.reported_malas,
        "status": s.status,
    }


def _close_pause_segment(session: JapaSession) -> None:
    if session.pause_started_at:
        delta = int((timezone.now() - session.pause_started_at).total_seconds())
        if delta > 0:
            session.paused_seconds += delta
        session.pause_started_at = None


def japa_insights_for_user(user) -> dict:
    """Snapshot for embedding in ``GET /insights/me/``."""
    now = timezone.now()
    since_30d = now - timedelta(days=30)
    since_date = since_30d.date()

    active_commitments = list(
        JapaCommitment.objects.filter(user=user, status=JapaCommitment.STATUS_ACTIVE)
    )
    active_count = len(active_commitments)
    active_ids = [c.id for c in active_commitments]

    # Batch-fetch all daily completions for active commitments in 1 query
    completions_qs = JapaDailyCompletion.objects.filter(
        commitment_id__in=active_ids,
        date__gte=since_date,
    ).order_by("-date").values("commitment_id", "date", "malas_completed")

    # Group in Python
    malas_by_commitment: dict[int, int] = defaultdict(int)
    days_by_commitment: dict[int, set] = defaultdict(set)
    history_by_commitment: dict[int, list] = defaultdict(list)
    for row in completions_qs:
        cid = row["commitment_id"]
        malas_by_commitment[cid] += row["malas_completed"]
        days_by_commitment[cid].add(row["date"])
        history_by_commitment[cid].append({"date": row["date"].isoformat(), "malas": row["malas_completed"]})

    active_commitments_list = [
        {
            "id": c.id,
            "title": c.title,
            "mantra_label": c.mantra_label,
            "daily_target_malas": c.daily_target_malas,
            "started_on": c.started_on.isoformat() if c.started_on else None,
            "completed_malas_30d": malas_by_commitment[c.id],
            "distinct_days_30d": len(days_by_commitment[c.id]),
            "daily_history": history_by_commitment[c.id],
        }
        for c in active_commitments
    ]

    sessions_30d = JapaSession.objects.filter(
        user=user,
        status=JapaSession.STATUS_COMPLETED,
        ended_at__gte=since_30d,
    ).count()
    # Totals for all active commitments: already computed above
    malas_30d = sum(malas_by_commitment.values())
    distinct_days = len(set().union(*days_by_commitment.values()) if days_by_commitment else set())
    return {
        "active_commitments": active_count,
        "active_commitments_list": active_commitments_list,
        "completed_sessions_30d": sessions_30d,
        "malas_logged_via_tracks_30d": int(malas_30d),
        "distinct_practice_days_30d": distinct_days,
    }


class JapaCommitmentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = JapaCommitment.objects.filter(user=request.user)
        st = request.query_params.get("status")
        if st in dict(JapaCommitment.STATUS_CHOICES):
            qs = qs.filter(status=st)
        else:
            qs = qs.exclude(status=JapaCommitment.STATUS_ARCHIVED)
        rows = qs.order_by("-updated_at")[:100]
        return Response({"results": [_commitment_dict(c) for c in rows]})

    def post(self, request):
        ser = JapaCommitmentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        started = d.get("started_on") or timezone.localdate()
        ends = d.get("ends_on")
        if ends and ends < started:
            return _err(
                message="ends_on cannot be before started_on.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="japa_invalid_range",
            )
        c = JapaCommitment.objects.create(
            user=request.user,
            title=d["title"].strip()[:120],
            focus_label=(d.get("focus_label") or "").strip()[:120],
            mantra_label=(d.get("mantra_label") or "").strip()[:120],
            daily_target_malas=int(d.get("daily_target_malas") or 1),
            started_on=started,
            ends_on=ends,
            preferred_time=d.get("preferred_time"),
            status=JapaCommitment.STATUS_ACTIVE,
        )
        return Response(_commitment_dict(c), status=status.HTTP_201_CREATED)


class JapaCommitmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        try:
            c = JapaCommitment.objects.get(pk=pk, user=request.user)
        except JapaCommitment.DoesNotExist:
            return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
        today = timezone.localdate()
        daily = (
            JapaDailyCompletion.objects.filter(commitment=c, date=today).first()
        )
        active = JapaSession.objects.filter(
            user=request.user,
            commitment=c,
            status=JapaSession.STATUS_IN_PROGRESS,
        ).first()
        payload = _commitment_dict(c)
        payload["today"] = (
            {
                "date": daily.date.isoformat(),
                "malas_completed": daily.malas_completed,
            }
            if daily
            else None
        )
        payload["active_session"] = _session_dict(active) if active else None
        last_7 = (
            JapaDailyCompletion.objects.filter(commitment=c)
            .order_by("-date")[:7]
            .values("date", "malas_completed")
        )
        payload["recent_days"] = [
            {"date": x["date"].isoformat(), "malas_completed": x["malas_completed"]} for x in last_7
        ]
        return Response(payload)

    def patch(self, request, pk: int):
        try:
            c = JapaCommitment.objects.get(pk=pk, user=request.user)
        except JapaCommitment.DoesNotExist:
            return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
        if c.status in (JapaCommitment.STATUS_FULFILLED, JapaCommitment.STATUS_ARCHIVED):
            return _err(
                message="This commitment is closed.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="japa_closed",
            )
        ser = JapaCommitmentPatchSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "title" in d:
            c.title = d["title"].strip()[:120]
        if "focus_label" in d:
            c.focus_label = (d.get("focus_label") or "").strip()[:120]
        if "mantra_label" in d:
            c.mantra_label = (d.get("mantra_label") or "").strip()[:120]
        if "daily_target_malas" in d:
            c.daily_target_malas = int(d["daily_target_malas"])
        if "ends_on" in d:
            c.ends_on = d.get("ends_on")
        if "preferred_time" in d:
            c.preferred_time = d.get("preferred_time")
        if "status" in d:
            if d["status"] == "archived":
                c.status = JapaCommitment.STATUS_ARCHIVED
            elif d["status"] == "paused":
                c.status = JapaCommitment.STATUS_PAUSED
            elif d["status"] == "active":
                c.status = JapaCommitment.STATUS_ACTIVE
        if c.ends_on and c.ends_on < c.started_on:
            return _err(
                message="ends_on cannot be before started_on.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="japa_invalid_range",
            )
        c.save()
        return Response(_commitment_dict(c))


class JapaCommitmentFulfillView(APIView):
    """Mark the whole sankalpa fulfilled and close any open session."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        try:
            c = JapaCommitment.objects.get(pk=pk, user=request.user)
        except JapaCommitment.DoesNotExist:
            return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
        if c.status in (JapaCommitment.STATUS_FULFILLED, JapaCommitment.STATUS_ARCHIVED):
            return Response(_commitment_dict(c))
        now = timezone.now()
        with transaction.atomic():
            for s in JapaSession.objects.select_for_update().filter(
                user=request.user,
                commitment=c,
                status=JapaSession.STATUS_IN_PROGRESS,
            ):
                _close_pause_segment(s)
                s.status = JapaSession.STATUS_ABANDONED
                s.ended_at = now
                s.save(update_fields=["pause_started_at", "paused_seconds", "status", "ended_at"])
            c.status = JapaCommitment.STATUS_FULFILLED
            c.fulfilled_at = now
            c.save(update_fields=["status", "fulfilled_at", "updated_at"])
        return Response(_commitment_dict(c))


class JapaSessionStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        now = timezone.now()
        with transaction.atomic():
            try:
                c = JapaCommitment.objects.select_for_update().get(pk=pk, user=request.user)
            except JapaCommitment.DoesNotExist:
                return _err(
                    message="Not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="not_found",
                )
            if c.status != JapaCommitment.STATUS_ACTIVE:
                return _err(
                    message="Start requires an active commitment.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_not_active",
                )
            existing = (
                JapaSession.objects.select_for_update()
                .filter(user=request.user, commitment=c, status=JapaSession.STATUS_IN_PROGRESS)
                .first()
            )
            if existing:
                return Response(_session_dict(existing), status=status.HTTP_200_OK)
            for s in JapaSession.objects.select_for_update().filter(
                user=request.user, status=JapaSession.STATUS_IN_PROGRESS
            ):
                _close_pause_segment(s)
                s.status = JapaSession.STATUS_ABANDONED
                s.ended_at = now
                s.save(update_fields=["pause_started_at", "paused_seconds", "status", "ended_at"])
            s = JapaSession.objects.create(
                commitment=c,
                user=request.user,
                started_at=now,
                status=JapaSession.STATUS_IN_PROGRESS,
            )
        return Response(_session_dict(s), status=status.HTTP_201_CREATED)


class JapaSessionPauseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        with transaction.atomic():
            try:
                s = JapaSession.objects.select_for_update().get(pk=pk, user=request.user)
            except JapaSession.DoesNotExist:
                return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
            if s.status != JapaSession.STATUS_IN_PROGRESS:
                return _err(
                    message="Session is not active.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_bad_state",
                )
            if s.pause_started_at:
                return Response(_session_dict(s))
            s.pause_started_at = timezone.now()
            s.save(update_fields=["pause_started_at"])
        return Response(_session_dict(s))


class JapaSessionResumeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        with transaction.atomic():
            try:
                s = JapaSession.objects.select_for_update().get(pk=pk, user=request.user)
            except JapaSession.DoesNotExist:
                return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
            if s.status != JapaSession.STATUS_IN_PROGRESS:
                return _err(
                    message="Session is not active.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_bad_state",
                )
            _close_pause_segment(s)
            s.save(update_fields=["pause_started_at", "paused_seconds"])
        return Response(_session_dict(s))


class JapaSessionAbandonView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        now = timezone.now()
        with transaction.atomic():
            try:
                s = JapaSession.objects.select_for_update().get(pk=pk, user=request.user)
            except JapaSession.DoesNotExist:
                return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
            if s.status != JapaSession.STATUS_IN_PROGRESS:
                return Response(_session_dict(s))
            _close_pause_segment(s)
            s.status = JapaSession.STATUS_ABANDONED
            s.ended_at = now
            s.save(update_fields=["pause_started_at", "paused_seconds", "status", "ended_at"])
        return Response(_session_dict(s))


class JapaSessionFinishDayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        ser = JapaFinishDaySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        local_date: date = d["local_date"]
        add_malas = int(d["malas_completed"])
        note = (d.get("note") or "").strip()[:240]
        now = timezone.now()
        with transaction.atomic():
            try:
                s_locked = JapaSession.objects.select_for_update().get(pk=pk, user=request.user)
            except JapaSession.DoesNotExist:
                return _err(message="Not found.", status_code=status.HTTP_404_NOT_FOUND, code="not_found")
            if s_locked.status != JapaSession.STATUS_IN_PROGRESS:
                return _err(
                    message="Session is not in progress.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_bad_state",
                )
            c = JapaCommitment.objects.select_for_update().get(pk=s_locked.commitment_id)
            if c.user_id != request.user.id:
                return _err(message="Forbidden.", status_code=status.HTTP_403_FORBIDDEN, code="forbidden")
            if c.status not in (JapaCommitment.STATUS_ACTIVE, JapaCommitment.STATUS_PAUSED):
                return _err(
                    message="Commitment is not active.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_not_active",
                )
            if local_date < c.started_on:
                return _err(
                    message="local_date is before this commitment started.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_date_range",
                )
            if c.ends_on and local_date > c.ends_on:
                return _err(
                    message="local_date is after this commitment's end date.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="japa_date_range",
                )
            _close_pause_segment(s_locked)
            s_locked.ended_at = now
            s_locked.reported_malas = add_malas
            s_locked.status = JapaSession.STATUS_COMPLETED
            s_locked.save(
                update_fields=[
                    "pause_started_at",
                    "paused_seconds",
                    "ended_at",
                    "reported_malas",
                    "status",
                ]
            )
            completion, _created = JapaDailyCompletion.objects.get_or_create(
                commitment=c,
                date=local_date,
                defaults={"malas_completed": 0, "session": s_locked, "note": ""},
            )
            completion.malas_completed += add_malas
            completion.session = s_locked
            if note:
                completion.note = note[:240]
            completion.save(update_fields=["malas_completed", "session", "note", "updated_at"])
            row = PracticeLogEntry.objects.filter(
                user=request.user,
                japa_commitment=c,
                logged_on=local_date,
                entry_type=PracticeLogEntry.TYPE_JAPA_ROUNDS,
            ).first()
            mantra = (c.mantra_label or c.title)[:120]
            if row:
                row.quantity = completion.malas_completed
                row.mantra_label = mantra
                row.save(update_fields=["quantity", "mantra_label"])
            else:
                PracticeLogEntry.objects.create(
                    user=request.user,
                    logged_on=local_date,
                    entry_type=PracticeLogEntry.TYPE_JAPA_ROUNDS,
                    quantity=completion.malas_completed,
                    mantra_label=mantra,
                    note="",
                    japa_commitment=c,
                )
        return Response(
            {
                "session": _session_dict(s_locked),
                "daily_total_malas": completion.malas_completed,
                "date": local_date.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
