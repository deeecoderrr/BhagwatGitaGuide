from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostRedirectMiddleware:
    """301 redirect non-canonical hosts to a single canonical domain.

    This avoids duplicate-indexing (www vs apex vs fly.dev) and makes Search
    Console + sitemaps consistent.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical_host = str(getattr(settings, "CANONICAL_HOST", "")).strip().lower()
        if not canonical_host or settings.DEBUG:
            return self.get_response(request)

        request_host = str(request.get_host() or "").split(":", 1)[0].strip().lower()
        if not request_host or request_host == canonical_host:
            return self.get_response(request)

        # Only redirect safe idempotent methods.
        if request.method not in {"GET", "HEAD"}:
            return self.get_response(request)

        # Redirect www + fly.dev to canonical.
        if request_host == f"www.{canonical_host}" or request_host.endswith(".fly.dev"):
            scheme = "https"
            path = request.get_full_path()
            # get_full_path already includes query, but we avoid any surprises with
            # empty query dict on some edge cases.
            if request.GET:
                path = f"{request.path}?{urlencode(request.GET, doseq=True)}"
            target = f"{scheme}://{canonical_host}{path}"
            return HttpResponsePermanentRedirect(target)

        return self.get_response(request)

