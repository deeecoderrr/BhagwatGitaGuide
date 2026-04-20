"""django-allauth: ITR workspace redirect after login/signup when ?next= omitted."""
from __future__ import annotations

from django.conf import settings
from django.shortcuts import resolve_url

from allauth.account import app_settings as account_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import get_next_redirect_url


class ItrAccountAdapter(DefaultAccountAdapter):
    def _itr_workspace_url(self) -> str:
        raw = getattr(settings, "ITR_URL_PREFIX", "/itr-computation").rstrip("/")
        return f"{raw}/documents/"

    def _redirect_from_itr_referer(self, request):
        raw = getattr(settings, "ITR_URL_PREFIX", "/itr-computation").rstrip("/")
        prefix = raw.lower()
        ref = (request.META.get("HTTP_REFERER") or "").lower()
        if f"{prefix}/" in ref or ref.rstrip("/").endswith(prefix):
            return self._itr_workspace_url()
        return None

    def get_login_redirect_url(self, request):
        # allauth's `get_login_redirect_url()` in utils.py only calls the adapter after
        # explicit `redirect_url` and `next` are exhausted, so do not read `next` here.
        ref_url = self._redirect_from_itr_referer(request)
        if ref_url:
            return ref_url
        return super().get_login_redirect_url(request)

    def get_signup_redirect_url(self, request):
        """Post-signup redirect; allauth uses this, not get_login_redirect_url."""
        redirect_to = get_next_redirect_url(request)
        if redirect_to:
            return redirect_to
        ref_url = self._redirect_from_itr_referer(request)
        if ref_url:
            return ref_url
        return resolve_url(account_settings.SIGNUP_REDIRECT_URL)
