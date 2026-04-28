"""REST API for optional verse-by-verse Gita path (start / pause / resume / advance)."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from guide_api.gita_sequence import (
    first_verse,
    path_progress_payload,
    total_verse_count,
    verse_following,
)
from guide_api.models import UserGitaSequenceJourney
from guide_api.views import _error_response


def _get_journey(user):
    return UserGitaSequenceJourney.objects.filter(user=user).first()


class GitaPathView(APIView):
    """Current Gita path state (or not enrolled)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        j = _get_journey(request.user)
        if j is None:
            return Response(
                {
                    "enrolled": False,
                    "journey": None,
                    "total_verses": total_verse_count(),
                }
            )
        return Response(
            {
                "enrolled": True,
                "journey": path_progress_payload(j),
                "total_verses": total_verse_count(),
            }
        )


class GitaPathStartView(APIView):
    """
    Begin or restart the path at the first verse in the database.
    Optional body: ``intention`` (str) — personal sankalpa.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        first = first_verse()
        if first is None:
            return _error_response(
                message="Verse catalog is empty.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="gita_path_no_verses",
            )
        intention = (request.data.get("intention") or "").strip()[:2000]
        existing = _get_journey(request.user)
        if existing is None:
            j = UserGitaSequenceJourney.objects.create(
                user=request.user,
                status=UserGitaSequenceJourney.STATUS_ACTIVE,
                next_chapter=first.chapter,
                next_verse=first.verse,
                intention_text=intention,
            )
        else:
            existing.status = UserGitaSequenceJourney.STATUS_ACTIVE
            existing.next_chapter = first.chapter
            existing.next_verse = first.verse
            existing.completed_at = None
            existing.intention_text = intention or existing.intention_text
            existing.save(
                update_fields=[
                    "status",
                    "next_chapter",
                    "next_verse",
                    "completed_at",
                    "intention_text",
                    "updated_at",
                ]
            )
            j = existing
        return Response(
            {
                "ok": True,
                "journey": path_progress_payload(j),
                "total_verses": total_verse_count(),
            },
            status=status.HTTP_200_OK,
        )


class GitaPathPauseView(APIView):
    """Pause the path (explicit leave or client blur)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        j = _get_journey(request.user)
        if j is None:
            return _error_response(
                message="No Gita path enrolled.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="gita_path_not_found",
            )
        if j.status == UserGitaSequenceJourney.STATUS_COMPLETED:
            return Response({"ok": True, "journey": path_progress_payload(j)})
        j.status = UserGitaSequenceJourney.STATUS_PAUSED
        j.save(update_fields=["status", "updated_at"])
        return Response({"ok": True, "journey": path_progress_payload(j)})


class GitaPathResumeView(APIView):
    """Resume a paused path."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        j = _get_journey(request.user)
        if j is None:
            return _error_response(
                message="No Gita path enrolled.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="gita_path_not_found",
            )
        if j.status == UserGitaSequenceJourney.STATUS_COMPLETED:
            return Response({"ok": True, "journey": path_progress_payload(j)})
        j.status = UserGitaSequenceJourney.STATUS_ACTIVE
        j.save(update_fields=["status", "updated_at"])
        return Response({"ok": True, "journey": path_progress_payload(j)})


class GitaPathAdvanceView(APIView):
    """
    Mark the current ``next`` verse as read and move the pointer forward.
    Idempotent if already completed.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        j = _get_journey(request.user)
        if j is None:
            return _error_response(
                message="No Gita path enrolled.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="gita_path_not_found",
            )
        if j.status == UserGitaSequenceJourney.STATUS_COMPLETED:
            return Response({"ok": True, "journey": path_progress_payload(j)})
        nc, nv = j.next_chapter, j.next_verse
        if nc is None or nv is None:
            return _error_response(
                message="Invalid journey cursor.",
                status_code=status.HTTP_409_CONFLICT,
                code="gita_path_invalid_cursor",
            )
        nxt = verse_following(nc, nv)
        j.status = UserGitaSequenceJourney.STATUS_ACTIVE
        if nxt is None:
            j.status = UserGitaSequenceJourney.STATUS_COMPLETED
            j.next_chapter = None
            j.next_verse = None
            j.completed_at = timezone.now()
            j.save(
                update_fields=[
                    "status",
                    "next_chapter",
                    "next_verse",
                    "completed_at",
                    "updated_at",
                ]
            )
        else:
            j.next_chapter = nxt.chapter
            j.next_verse = nxt.verse
            j.save(update_fields=["status", "next_chapter", "next_verse", "updated_at"])
        return Response({"ok": True, "journey": path_progress_payload(j)})


class GitaPathAbandonView(APIView):
    """Remove the path so the user is no longer enrolled."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        deleted, _ = UserGitaSequenceJourney.objects.filter(user=request.user).delete()
        return Response({"ok": True, "deleted": deleted > 0})
