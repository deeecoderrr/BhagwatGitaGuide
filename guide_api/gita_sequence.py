"""Helpers for canonical verse order (full Gita path) and progress."""

from __future__ import annotations

from django.db.models import Q

from guide_api.models import UserGitaSequenceJourney, Verse


def total_verse_count() -> int:
    return Verse.objects.count()


def first_verse() -> Verse | None:
    return Verse.objects.order_by("chapter", "verse").first()


def verse_following(chapter: int, verse: int) -> Verse | None:
    """Next verse in canonical order after (chapter, verse), or None if at end."""
    return (
        Verse.objects.filter(Q(chapter=chapter, verse__gt=verse) | Q(chapter__gt=chapter))
        .order_by("chapter", "verse")
        .first()
    )


def verses_completed_before_next(next_ch: int | None, next_v: int | None) -> int:
    """
    Count of verses strictly before the ``next`` pointer (verses already read
    in sequence). If next is the first verse, returns 0.
    """
    if next_ch is None or next_v is None:
        return 0
    return Verse.objects.filter(
        Q(chapter__lt=next_ch) | Q(chapter=next_ch, verse__lt=next_v),
    ).count()


def path_progress_payload(journey: UserGitaSequenceJourney | None) -> dict | None:
    """JSON-serializable summary for API + insights; None if not enrolled."""
    if journey is None:
        return None
    total = total_verse_count()
    if total == 0:
        return {
            "enrolled": True,
            "status": journey.status,
            "next": None,
            "verses_completed": 0,
            "total_verses": 0,
            "percent": 0.0,
            "intention_text": (journey.intention_text or "").strip() or None,
            "started_at": journey.started_at.isoformat(),
            "completed_at": (
                journey.completed_at.isoformat() if journey.completed_at else None
            ),
        }
    if journey.status == UserGitaSequenceJourney.STATUS_COMPLETED:
        return {
            "enrolled": True,
            "status": journey.status,
            "next": None,
            "verses_completed": total,
            "total_verses": total,
            "percent": 100.0,
            "intention_text": (journey.intention_text or "").strip() or None,
            "started_at": journey.started_at.isoformat(),
            "completed_at": (
                journey.completed_at.isoformat() if journey.completed_at else None
            ),
        }
    nc, nv = journey.next_chapter, journey.next_verse
    if nc is None or nv is None:
        return {
            "enrolled": True,
            "status": journey.status,
            "next": None,
            "verses_completed": 0,
            "total_verses": total,
            "percent": 0.0,
            "intention_text": (journey.intention_text or "").strip() or None,
            "started_at": journey.started_at.isoformat(),
            "completed_at": None,
        }
    done = verses_completed_before_next(nc, nv)
    pct = round(100.0 * done / total, 2) if total else 0.0
    return {
        "enrolled": True,
        "status": journey.status,
        "next": f"{nc}.{nv}",
        "verses_completed": done,
        "total_verses": total,
        "percent": pct,
        "intention_text": (journey.intention_text or "").strip() or None,
        "started_at": journey.started_at.isoformat(),
        "completed_at": None,
    }
