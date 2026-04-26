"""Daily practice push reminders via Expo Push API."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, time
from typing import Any, Callable

from django.conf import settings
from django.utils import timezone as django_timezone

from guide_api.models import NotificationDevice, UserEngagementProfile

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# ``zoneinfo`` uses IANA names (e.g. ``Asia/Kolkata``). The app often stores
# abbreviations like ``IST``, which are not valid IANA IDs and would silently
# fall back to UTC and never match local wall-clock times.
_TZ_ALIASES: dict[str, str] = {
    "ist": "Asia/Kolkata",
    "india standard time": "Asia/Kolkata",
    "asia/calcutta": "Asia/Kolkata",
    "calcutta": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
}


def zoneinfo_for_reminder_timezone(tz_name: str):
    """Return ``ZoneInfo`` for a user-entered timezone string (IANA or common alias)."""
    from zoneinfo import ZoneInfo

    raw = (tz_name or "").strip()
    if not raw:
        return ZoneInfo("UTC")
    lowered = raw.lower().replace(" ", "_")
    candidate = _TZ_ALIASES.get(lowered, raw)
    try:
        return ZoneInfo(candidate)
    except Exception:
        pass
    try:
        return ZoneInfo(raw)
    except Exception:
        logger.warning(
            "Unknown reminder timezone %r; using UTC (set IANA e.g. Asia/Kolkata).",
            raw,
        )
        return ZoneInfo("UTC")

POST_EXPO_BATCH: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None


def is_expo_push_token(token: str) -> bool:
    return bool(token and token.startswith("ExponentPushToken["))


def is_within_reminder_window(
    now_local: datetime,
    reminder_time: time,
    window_minutes: int,
) -> bool:
    """True if ``now_local`` falls in ``[start, start + window)`` for reminder_time."""
    d = now_local.date()
    start_today = datetime.combine(d, reminder_time, tzinfo=now_local.tzinfo)
    if start_today > now_local:
        start = datetime.combine(
            d - timedelta(days=1),
            reminder_time,
            tzinfo=now_local.tzinfo,
        )
    else:
        start = start_today
    end = start + timedelta(minutes=window_minutes)
    return start <= now_local < end


def _default_post_expo_batch(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []
    payload = json.dumps({"messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        EXPO_PUSH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        },
        method="POST",
    )
    token = getattr(settings, "EXPO_ACCESS_TOKEN", "") or ""
    if token.strip():
        req.add_header("Authorization", f"Bearer {token.strip()}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        logger.error("Expo push HTTP error %s: %s", e.code, raw[:500])
        raise
    except OSError as e:
        logger.error("Expo push network error: %s", e)
        raise

    data = body.get("data")
    if data is None:
        logger.warning("Expo push unexpected body keys: %s", list(body.keys()))
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []


def _normalize_expo_results(raw: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        if i < len(raw) and isinstance(raw[i], dict):
            out.append(raw[i])
        else:
            out.append({"status": "error", "message": "missing ticket"})
    return out


def _device_should_deactivate(ticket: dict[str, Any]) -> bool:
    if ticket.get("status") == "ok":
        return False
    msg = (ticket.get("message") or "").lower()
    details = ticket.get("details") or {}
    err = (details.get("error") if isinstance(details, dict) else None) or ""
    err_l = str(err).lower()
    if "devicenotregistered" in err_l or "devicenotregistered" in msg:
        return True
    if "not registered" in msg and "push" in msg:
        return True
    return False


def run_push_reminders(
    *,
    dry_run: bool = False,
    window_minutes: int | None = None,
    now_utc: datetime | None = None,
) -> dict[str, int]:
    """
    Find users due for a daily push reminder and send via Expo.

    Schedule this management command at least every ``window`` minutes
    (default from ``PUSH_REMINDER_WINDOW_MINUTES``).
    """
    window = (
        window_minutes
        if window_minutes is not None
        else int(getattr(settings, "PUSH_REMINDER_WINDOW_MINUTES", 15))
    )
    if window <= 0:
        window = 15

    from zoneinfo import ZoneInfo

    if now_utc is None:
        now_utc = datetime.now(tz=ZoneInfo("UTC"))
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))

    title = getattr(
        settings,
        "PUSH_REMINDER_TITLE",
        "Daily Gita reflection",
    )
    body = getattr(
        settings,
        "PUSH_REMINDER_BODY",
        "Take a quiet moment with today's verse in Ask Bhagavad Gita.",
    )

    poster = POST_EXPO_BATCH or _default_post_expo_batch

    profiles = (
        UserEngagementProfile.objects.filter(
            reminder_enabled=True,
            preferred_channel=UserEngagementProfile.CHANNEL_PUSH,
            reminder_time__isnull=False,
        )
        .select_related("user")
    )

    planned: list[tuple[UserEngagementProfile, datetime, list[NotificationDevice]]] = []

    for profile in profiles.iterator():
        tz_name = (profile.timezone or "UTC").strip() or "UTC"
        tz = zoneinfo_for_reminder_timezone(tz_name)
        now_local = now_utc.astimezone(tz)
        rt = profile.reminder_time
        assert rt is not None
        if not is_within_reminder_window(now_local, rt, window):
            continue
        today_local = now_local.date()
        if profile.last_reminder_push_date == today_local:
            continue

        devices = list(
            NotificationDevice.objects.filter(
                user=profile.user,
                active=True,
            ),
        )
        expo_devices = [d for d in devices if is_expo_push_token(d.token)]
        if not expo_devices:
            continue
        planned.append((profile, now_local, expo_devices))

    if dry_run:
        return {
            "due_users": len(planned),
            "due_messages": sum(len(x[2]) for x in planned),
            "sent": 0,
            "deactivated_devices": 0,
        }

    total_sent = 0
    total_deactivated = 0

    messages: list[dict[str, Any]] = []
    meta: list[tuple[UserEngagementProfile, date, NotificationDevice]] = []

    for profile, now_local, expo_devices in planned:
        local_date = now_local.date()
        for dev in expo_devices:
            messages.append(
                {
                    "to": dev.token,
                    "title": str(title),
                    "body": str(body),
                    "sound": "default",
                    "priority": "high",
                },
            )
            meta.append((profile, local_date, dev))

    batch_size = 100
    for offset in range(0, len(messages), batch_size):
        chunk_msgs = messages[offset : offset + batch_size]
        chunk_meta = meta[offset : offset + batch_size]
        if not chunk_msgs:
            break
        try:
            raw_results = poster(chunk_msgs)
        except Exception:
            logger.exception("Expo push batch failed at offset %s", offset)
            continue
        results = _normalize_expo_results(raw_results, len(chunk_msgs))

        users_marked_date: set[int] = set()
        for ticket, (profile, local_date, dev) in zip(results, chunk_meta):
            if ticket.get("status") == "ok":
                total_sent += 1
                uid = profile.user_id
                if uid not in users_marked_date:
                    row = UserEngagementProfile.objects.filter(pk=profile.pk).first()
                    if row is not None:
                        row.last_reminder_push_date = local_date
                        row.updated_at = django_timezone.now()
                        row.save(
                            update_fields=[
                                "last_reminder_push_date",
                                "updated_at",
                            ],
                        )
                    users_marked_date.add(uid)
            elif _device_should_deactivate(ticket):
                NotificationDevice.objects.filter(pk=dev.pk).update(active=False)
                total_deactivated += 1
                logger.info(
                    "Deactivated push device %s for user %s (Expo: %s)",
                    dev.pk,
                    profile.user_id,
                    ticket.get("message"),
                )

    return {
        "due_users": len(planned),
        "due_messages": len(messages),
        "sent": total_sent,
        "deactivated_devices": total_deactivated,
    }
