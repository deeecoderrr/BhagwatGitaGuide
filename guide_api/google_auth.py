"""Google Sign-In: verify ID tokens and map to Django users."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token


def verify_google_id_token(raw_token: str, audience: str) -> dict:
    """Validate a Google Identity Services credential JWT (``credential`` field)."""
    if not audience:
        raise ValueError("Google OAuth is not configured on the server.")
    info = google_id_token.verify_oauth2_token(
        raw_token,
        google_requests.Request(),
        audience,
    )
    iss = info.get("iss")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Invalid Google token issuer.")
    if not info.get("email_verified"):
        raise ValueError("Google email is not verified.")
    email = str(info.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google did not provide an email.")
    return info


def get_or_create_user_from_google_claims(claims: dict):
    """Return ``(user, error_code)`` where error_code is set on failure."""
    user_model = get_user_model()
    sub = str(claims.get("sub", "")).strip()
    if not sub:
        return None, "missing_sub"
    email = str(claims.get("email", "")).strip().lower()
    uname = f"google_{sub}"[:150]

    existing_google = user_model.objects.filter(username=uname).first()
    if existing_google:
        if email and not existing_google.email:
            existing_google.email = email
            existing_google.save(update_fields=["email"])
        return existing_google, None

    conflict = (
        user_model.objects.filter(email__iexact=email)
        .exclude(username=uname)
        .first()
    )
    if conflict:
        return None, "email_exists_password"

    user = user_model(username=uname, email=email)
    user.set_unusable_password()
    user.save()
    return user, None
