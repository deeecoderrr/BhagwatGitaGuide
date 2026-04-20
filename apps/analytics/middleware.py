"""Audience cookie + VisitorProfile/GrowthEvent (marketing funnel)."""
from __future__ import annotations

import logging
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

AUDIENCE_COOKIE = "itr_audience"
AUDIENCE_COOKIE_MAX_AGE = 60 * 60 * 24 * 395


def itr_url_prefix_norm() -> str:
    """e.g. /itr-computation (no trailing slash)."""
    p = getattr(settings, "ITR_URL_PREFIX", "/itr-computation").strip()
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/")


def _itr_marketing_paths() -> frozenset[str]:
    pre = itr_url_prefix_norm()
    return frozenset({f"{pre}/", f"{pre}/pricing/"})


_TRACKED_EVENT_PATHS = _itr_marketing_paths()


class AudienceTrackingMiddleware:
    """Set persistent visitor cookie; upsert VisitorProfile; optional GrowthEvent."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audience_id = ""

        pre = itr_url_prefix_norm()
        rp = request.path.rstrip("/")
        outside_itr = rp != pre and not rp.startswith(pre + "/")
        skip = (
            getattr(settings, "ANALYTICS_TRACKING_DISABLED", False)
            or request.path.startswith("/admin")
            or request.path.startswith("/static/")
            or request.path.startswith("/media/")
            or outside_itr
        )

        vid = request.COOKIES.get(AUDIENCE_COOKIE, "").strip()[:64]

        if not skip and request.method == "GET":
            if not vid:
                vid = uuid4().hex
            request.audience_id = vid

        response = self.get_response(request)

        if skip or request.method != "GET" or not vid:
            return response

        try:
            self._persist(request, vid, response)
        except Exception:
            logger.exception("Audience tracking failed")

        return response

    def _persist(self, request, vid: str, response) -> None:
        from apps.analytics.models import GrowthEvent, VisitorProfile

        had_cookie = bool(request.COOKIES.get(AUDIENCE_COOKIE))
        utm_s = request.GET.get("utm_source", "").strip()[:64]
        utm_m = request.GET.get("utm_medium", "").strip()[:64]
        utm_c = request.GET.get("utm_campaign", "").strip()[:64]
        utm_t = request.GET.get("utm_term", "").strip()[:64]
        utm_co = request.GET.get("utm_content", "").strip()[:64]
        user = request.user if request.user.is_authenticated else None

        profile, created = VisitorProfile.objects.get_or_create(
            visitor_id=vid,
            defaults={
                "user": user,
                "visit_count": 1,
                "first_utm_source": utm_s,
                "first_utm_medium": utm_m,
                "first_utm_campaign": utm_c,
                "first_utm_term": utm_t,
                "first_utm_content": utm_co,
                "last_utm_source": utm_s,
                "last_utm_medium": utm_m,
                "last_utm_campaign": utm_c,
                "last_utm_term": utm_t,
                "last_utm_content": utm_co,
                "last_path": request.path[:255],
            },
        )

        if not had_cookie:
            secure = not settings.DEBUG
            response.set_cookie(
                AUDIENCE_COOKIE,
                vid,
                max_age=AUDIENCE_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=secure,
            )

        if created:
            request.session["_itr_audience_bumped"] = True
            request.session.modified = True
            self._maybe_log_event(request, vid, created=True)
            return

        profile.last_path = request.path[:255]
        if utm_s:
            profile.last_utm_source = utm_s
        if utm_m:
            profile.last_utm_medium = utm_m
        if utm_c:
            profile.last_utm_campaign = utm_c
        if utm_t:
            profile.last_utm_term = utm_t
        if utm_co:
            profile.last_utm_content = utm_co
        if user and profile.user_id is None:
            profile.user = user

        if not request.session.get("_itr_audience_bumped"):
            profile.visit_count += 1
            request.session["_itr_audience_bumped"] = True
            request.session.modified = True

        profile.save()

        self._maybe_log_event(request, vid, created=False)

    def _maybe_log_event(self, request, vid: str, *, created: bool) -> None:
        from apps.analytics.models import GrowthEvent

        path = request.path
        if path not in _TRACKED_EVENT_PATHS:
            return

        cache_key = f"_itr_ge_{path.strip('/') or 'home'}"
        today = timezone.now().date().isoformat()
        if request.session.get(cache_key) == today:
            return
        request.session[cache_key] = today
        request.session.modified = True

        pre = itr_url_prefix_norm()
        et = (
            GrowthEvent.EVENT_PAGE_VIEW
            if path == f"{pre}/"
            else GrowthEvent.EVENT_PRICING_VIEW
        )
        GrowthEvent.objects.create(
            visitor_id=vid,
            event_type=et,
            path=path[:255],
            metadata={
                "utm_source": request.GET.get("utm_source", "")[:64],
                "utm_medium": request.GET.get("utm_medium", "")[:64],
                "utm_campaign": request.GET.get("utm_campaign", "")[:64],
                "utm_term": request.GET.get("utm_term", "")[:64],
                "utm_content": request.GET.get("utm_content", "")[:64],
                "new_visitor": created,
            },
        )
