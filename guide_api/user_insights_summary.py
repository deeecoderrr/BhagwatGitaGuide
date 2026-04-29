"""
Aggregated journey snapshot for ``GET /api/insights/me/``.

All insight-style counts and rollups for the mobile Insights tab live here so
``guide_api/views.py`` stays thin and this module can be tested or extended in
one place (queries, windows, and response shape).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from guide_api.gita_sequence import path_progress_payload
from guide_api.japa_views import japa_insights_for_user
from guide_api.models import (
    AskEvent,
    CommunityPost,
    Conversation,
    MeditationSessionLog,
    Message,
    PracticeLogEntry,
    SadhanaDayCompletion,
    SadhanaEnrollment,
    SavedReflection,
    UserGitaSequenceJourney,
    UserReadingState,
    VerseUserNote,
)


def normalize_verse_reference(ref: object) -> str | None:
    """Normalize verse keys (e.g. ``2.47``, ``BG 2.47``) to ``chapter.verse``."""
    s = str(ref or "").strip()
    if not s:
        return None
    s = re.sub(r"^\s*BG\s+", "", s, flags=re.I).strip()
    m = re.search(r"(\d+)\s*\.\s*(\d+)", s)
    if not m:
        return None
    return f"{int(m.group(1))}.{int(m.group(2))}"


def _chapter_from_normalized_ref(key: str) -> int | None:
    """Return Gita chapter 1–18 from ``chapter.verse`` or None."""
    parts = (key or "").split(".", 1)
    if len(parts) != 2:
        return None
    try:
        c = int(parts[0])
    except ValueError:
        return None
    if 1 <= c <= 18:
        return c
    return None


def _build_gita_insights(
    *,
    user: AbstractBaseUser,
    username: str,
    since_30d,
    saved_rows: list,
    verse_counter: Counter,
    verses_seen_list: list,
    read_minutes_7d: int,
    read_minutes_total: int,
) -> dict[str, Any]:
    """Bhagavad Gita–centric study footprint (reading, notes, saves, guidance)."""
    seen_chapters: set[int] = set()
    unique_verse_keys: set[str] = set()
    for raw in verses_seen_list:
        key = normalize_verse_reference(raw)
        if not key:
            continue
        unique_verse_keys.add(key)
        ch = _chapter_from_normalized_ref(key)
        if ch is not None:
            seen_chapters.add(ch)

    chapter_weight: Counter[int] = Counter()
    for ref, w in verse_counter.items():
        cht = _chapter_from_normalized_ref(ref)
        if cht is not None:
            chapter_weight[cht] += w
    for raw in verses_seen_list:
        key = normalize_verse_reference(raw)
        if not key:
            continue
        cht = _chapter_from_normalized_ref(key)
        if cht is not None:
            chapter_weight[cht] += 1

    top_chapters = [
        {"chapter": c, "count": n} for c, n in chapter_weight.most_common(5)
    ]

    saved_with_verses = sum(
        1
        for row in saved_rows
        if row.verse_references
        and any(str(x).strip() for x in row.verse_references)
    )

    verse_notes = VerseUserNote.objects.filter(user=user).count()
    asks_served_30d = AskEvent.objects.filter(
        user_id=username,
        outcome=AskEvent.OUTCOME_SERVED,
        created_at__gte=since_30d,
    ).count()

    return {
        "chapters_explored": len(seen_chapters),
        "verses_opened": len(unique_verse_keys),
        "verse_notes": verse_notes,
        "saved_reflections_with_verses": saved_with_verses,
        "read_minutes_7d": int(read_minutes_7d),
        "read_minutes_total": int(read_minutes_total),
        "asks_with_guidance_30d": asks_served_30d,
        "top_chapters": top_chapters,
        "verses_opened_list": sorted(list(unique_verse_keys)),
        "chapters_explored_list": sorted(list(seen_chapters)),
    }


def build_user_insights_summary(
    user: AbstractBaseUser,
    *,
    now=None,
    engagement: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the JSON-serializable payload for ``UserInsightsSummaryView``.

    ``engagement`` must be the pre-serialized profile dict (built in the view with
    ``_serialize_engagement_profile`` / ``_get_engagement_profile``) to avoid circular
    imports between this module and ``views.py``.
    """
    if now is None:
        now = timezone.now()
    username = user.get_username()
    since_30d = now - timedelta(days=30)
    since_7d_date = (now - timedelta(days=7)).date()

    conv_agg = Conversation.objects.filter(user_id=username).aggregate(
        total=Count("pk"),
        last_updated=Max("updated_at"),
    )
    conv_total = conv_agg["total"] or 0
    lu = conv_agg["last_updated"]
    last_activity_at = lu.isoformat() if lu else None

    saved_rows = list(
        SavedReflection.objects.filter(user=user).only("verse_references"),
    )
    saved_total = len(saved_rows)
    verse_counter: Counter[str] = Counter()
    for row in saved_rows:
        refs = row.verse_references
        if not refs:
            continue
        for raw in refs:
            key = normalize_verse_reference(raw)
            if key:
                verse_counter[key] += 1
    verse_companions = [
        {"reference": ref, "count": count}
        for ref, count in verse_counter.most_common(8)
    ]

    recent_questions: list[dict[str, str]] = []
    for msg in (
        Message.objects.filter(
            conversation__user_id=username,
            role=Message.ROLE_USER,
        )
        .order_by("-created_at")[:12]
    ):
        snippet = " ".join((msg.content or "").strip().split())
        if not snippet:
            continue
        if len(snippet) > 120:
            snippet = snippet[:117].rstrip() + "…"
        recent_questions.append(
            {
                "snippet": snippet,
                "created_at": msg.created_at.isoformat(),
            },
        )
        if len(recent_questions) >= 5:
            break

    community_agg = CommunityPost.objects.filter(
        author=user,
        deleted_at__isnull=True,
    ).aggregate(
        root_posts=Count("pk", filter=Q(parent__isnull=True)),
        replies=Count("pk", filter=Q(parent__isnull=False)),
    )
    root_posts = community_agg["root_posts"] or 0
    reply_posts = community_agg["replies"] or 0

    active_enrollments = (
        SadhanaEnrollment.objects.filter(
            user=user,
            access_ends_at__gt=now,
            access_starts_at__lte=now,
        )
        .select_related("program")
        .order_by("-access_ends_at")
    )
    sadhana_active_list = [
        {
            "slug": e.program.slug,
            "title": e.program.title,
            "access_ends_at": e.access_ends_at.isoformat(),
        } for e in active_enrollments
    ]
    sadhana_active = sadhana_active_list[0] if sadhana_active_list else None

    sadhana_completions_30d = (
        SadhanaDayCompletion.objects.filter(completed_at__gte=since_30d)
        .filter(Q(user=user) | Q(enrollment__user=user))
        .distinct()
        .count()
    )

    read_state = UserReadingState.objects.filter(user=user).first()
    verses_seen_list = (
        read_state.verses_seen
        if read_state and isinstance(read_state.verses_seen, list)
        else []
    )

    practice_7d_agg = PracticeLogEntry.objects.filter(
        user=user,
        logged_on__gte=since_7d_date,
    ).aggregate(
        japa=Sum(
            "quantity",
            filter=Q(entry_type=PracticeLogEntry.TYPE_JAPA_ROUNDS),
        ),
        med=Sum(
            "quantity",
            filter=Q(entry_type=PracticeLogEntry.TYPE_MEDITATION_MINUTES),
        ),
        read_min=Sum(
            "quantity",
            filter=Q(entry_type=PracticeLogEntry.TYPE_READ_MINUTES),
        ),
    )
    japa_7d = practice_7d_agg["japa"] or 0
    med_min_7d = practice_7d_agg["med"] or 0
    read_min_7d = practice_7d_agg["read_min"] or 0
    meditation_logs_30d = MeditationSessionLog.objects.filter(
        user=user,
        created_at__gte=since_30d,
    ).count()

    practice_all_agg = PracticeLogEntry.objects.filter(
        user=user,
    ).aggregate(
        read_min=Sum(
            "quantity",
            filter=Q(entry_type=PracticeLogEntry.TYPE_READ_MINUTES),
        ),
    )
    read_min_all = practice_all_agg["read_min"] or 0

    gita = _build_gita_insights(
        user=user,
        username=username,
        since_30d=since_30d,
        saved_rows=saved_rows,
        verse_counter=verse_counter,
        verses_seen_list=verses_seen_list,
        read_minutes_7d=read_min_7d,
        read_minutes_total=read_min_all,
    )

    gita_path = path_progress_payload(
        UserGitaSequenceJourney.objects.filter(user=user).first(),
    )

    return {
        "engagement": engagement,
        "conversations": {
            "total": conv_total,
            "last_activity_at": last_activity_at,
        },
        "saved_reflections": {"total": saved_total},
        "verse_companions": verse_companions,
        "recent_questions": recent_questions,
        "community": {
            "root_posts": root_posts,
            "replies": reply_posts,
        },
        "sadhana": {
            "active": sadhana_active,
            "active_list": sadhana_active_list,
            "completed_days_last_30d": sadhana_completions_30d,
        },
        "reading": {
            "verses_opened_count": len(
                {str(x).strip() for x in verses_seen_list if str(x).strip()},
            ),
            "read_streak": read_state.read_streak if read_state else 0,
            "last_read_date": (
                read_state.last_read_date.isoformat()
                if read_state and read_state.last_read_date
                else None
            ),
            "last_verse": (
                f"{read_state.last_chapter}.{read_state.last_verse}"
                if read_state
                and read_state.last_chapter is not None
                and read_state.last_verse is not None
                else None
            ),
        },
        "practice": {
            "japa_rounds_7d": int(japa_7d),
            "meditation_minutes_7d": int(med_min_7d),
            "read_minutes_7d": int(read_min_7d),
            "read_minutes_total": int(read_min_all),
            "meditation_session_logs_30d": meditation_logs_30d,
        },
        "japa": japa_insights_for_user(user),
        "gita": gita,
        "gita_path": gita_path,
        "generated_at": now.isoformat(),
    }
