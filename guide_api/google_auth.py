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


def apply_google_claims_to_user(user, claims: dict) -> None:
    """Copy human-readable profile fields from OIDC claims onto the user instance."""
    email = str(claims.get("email") or "").strip().lower()
    given = str(claims.get("given_name") or "").strip()[:150]
    family = str(claims.get("family_name") or "").strip()[:150]
    full = str(claims.get("name") or "").strip()

    update_fields = []
    if email and getattr(user, "email", "") != email:
        user.email = email
        update_fields.append("email")

    if given or family:
        if given and user.first_name != given:
            user.first_name = given
            update_fields.append("first_name")
        if family and user.last_name != family:
            user.last_name = family
            update_fields.append("last_name")
    elif full:
        parts = full.split(None, 1)
        first = parts[0][:150]
        last = parts[1][:150] if len(parts) > 1 else ""
        if user.first_name != first:
            user.first_name = first
            update_fields.append("first_name")
        if last and user.last_name != last:
            user.last_name = last
            update_fields.append("last_name")

    if user.pk and update_fields:
        user.save(update_fields=sorted(set(update_fields)))


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
        apply_google_claims_to_user(existing_google, claims)
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
    apply_google_claims_to_user(user, claims)
    user.save()
    return user, None
