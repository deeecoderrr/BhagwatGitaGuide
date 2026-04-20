from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AnonymousUser


def google_oauth(request):
    return {
        "google_oauth_configured": getattr(
            settings, "GOOGLE_OAUTH_CONFIGURED", False
        ),
    }


def support_contact(request):
    """Expose SUPPORT_EMAIL for account templates (mailto, footnotes)."""
    return {"support_email": getattr(settings, "SUPPORT_EMAIL", "")}


def account_profile(request):
    user = request.user
    if isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {"account_profile": None}
    from apps.accounts.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    return {"account_profile": profile}
