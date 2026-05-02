"""Streak update logic shared across view modules.

Extracted so that japa_views, sadhana_views, and views can all call
``update_streak_for_today`` without circular import issues.

A streak day is earned whenever the user completes any meaningful spiritual
practice:
  - Asks a guidance question (AskView / AskStreamView)
  - Logs a meditation sit (MeditationSessionLogCreateView)
  - Logs practice entries: meditation_minutes or japa_rounds (PracticeLogListCreateView)
  - Finishes a japa day (JapaSessionFinishDayView)
  - Completes a sadhana program day (SadhanaDayCompleteView)
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from guide_api.models import EngagementEvent, UserEngagementProfile


def serialize_engagement_profile(profile) -> dict:
    """Return stable API payload for an engagement profile instance."""
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
        "reminder_language": getattr(profile, "reminder_language", None) or "en",
    }


def update_streak_for_today(user):
    """Increment (or reset) the user's daily engagement streak.

    Idempotent within a single calendar day — multiple calls on the same day
    return the already-updated profile without writing again.

    Returns the (possibly updated) ``UserEngagementProfile`` instance.
    """
    _ck = f"eng_profile:{user.pk}"
    cached = cache.get(_ck)
    if cached is not None:
        profile = cached
    else:
        profile, _ = UserEngagementProfile.objects.get_or_create(user=user)
        cache.set(_ck, profile, 300)

    today = timezone.localdate()
    previous = profile.last_active_date

    # Already counted for today — nothing to do.
    if previous == today:
        return profile

    if previous == (today - timedelta(days=1)):
        profile.daily_streak = max(1, profile.daily_streak + 1)
    else:
        profile.daily_streak = 1

    profile.last_active_date = today
    profile.save(update_fields=["daily_streak", "last_active_date", "updated_at"])
    cache.delete(_ck)  # invalidate cached copy after write

    EngagementEvent.objects.create(
        user=user,
        event_type=EngagementEvent.EVENT_STREAK_UPDATED,
        metadata={
            "daily_streak": profile.daily_streak,
            "last_active_date": today.isoformat(),
        },
    )
    return profile
