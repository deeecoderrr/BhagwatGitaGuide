"""Infrastructure middleware: canonical hostname and HTTPS/mixed-content headers."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponsePermanentRedirect

logger = logging.getLogger(__name__)


class CanonicalHostRedirectMiddleware:
    """301 redirect non-canonical hosts to CANONICAL_HOST (production SEO consistency)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical = str(getattr(settings, "CANONICAL_HOST", "")).strip().lower()
        if not canonical or settings.DEBUG:
            return self.get_response(request)

        host = str(request.get_host() or "").split(":", 1)[0].strip().lower()
        if not host or host == canonical:
            return self.get_response(request)

        if request.method not in {"GET", "HEAD"}:
            return self.get_response(request)

        # Apex vs www vs platform default hostnames (SEO single canonical URL)
        redirect_host = False
        if host == f"www.{canonical}":
            redirect_host = True
        elif host.endswith(".fly.dev"):
            redirect_host = True
        elif host.endswith(".onrender.com"):
            redirect_host = True

        if not redirect_host:
            return self.get_response(request)

        path = request.get_full_path()
        if request.GET:
            path = f"{request.path}?{urlencode(request.GET, doseq=True)}"
        target = f"https://{canonical}{path}"
        return HttpResponsePermanentRedirect(target)


class MixedContentProtectionMiddleware:
    """Upgrade insecure subresources on HTTPS responses (production)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG:
            return response
        response.headers.setdefault(
            "Content-Security-Policy",
            "upgrade-insecure-requests; block-all-mixed-content",
        )
        return response
