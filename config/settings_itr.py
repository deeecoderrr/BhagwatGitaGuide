"""
ITR Summary Generator — optional Django settings (under ITR_URL_PREFIX).

Enable with ITR_ENABLED=true (default). When disabled, the project runs without
allauth, ITR apps, or ITR URL routes (Bhagavad Gita–only deploy).
"""

from __future__ import annotations

import os
from typing import Any


def register_itr_settings(g: dict[str, Any]) -> None:
    """Mutate the main settings namespace (call as register_itr_settings(globals()))."""
    if os.getenv("ITR_ENABLED", "true").lower() not in ("1", "true", "yes"):
        g["ITR_ENABLED"] = False
        return

    g["ITR_ENABLED"] = True

    base_dir = g["BASE_DIR"]

    g["ITR_URL_PREFIX"] = (
        os.getenv("ITR_URL_PREFIX", "/itr-computation") or "/itr-computation"
    ).strip()

    g["INSTALLED_APPS"].extend(
        [
            "django.contrib.sites",
            "allauth",
            "allauth.account",
            "allauth.socialaccount",
            "allauth.socialaccount.providers.google",
            "django_rq",
            "apps.core",
            "apps.accounts",
            "apps.analytics",
            "apps.billing",
            "apps.comments",
            "apps.documents",
            "apps.exports",
            "apps.extractors",
            "apps.marketing",
            "apps.reviews",
        ],
    )

    g["SITE_ID"] = 1

    # Post login/signup for allauth (Django default /accounts/profile/ is not routed here).
    _itr_home = g["ITR_URL_PREFIX"].rstrip("/") + "/documents/"
    g["LOGIN_REDIRECT_URL"] = os.getenv("LOGIN_REDIRECT_URL", "").strip() or _itr_home

    g["AUTHENTICATION_BACKENDS"] = [
        "django.contrib.auth.backends.ModelBackend",
        "allauth.account.auth_backends.AuthenticationBackend",
    ]

    session_ix = g["MIDDLEWARE"].index(
        "django.contrib.sessions.middleware.SessionMiddleware",
    )
    g["MIDDLEWARE"].insert(
        session_ix + 1,
        "allauth.account.middleware.AccountMiddleware",
    )
    g["MIDDLEWARE"].append(
        "apps.analytics.middleware.AudienceTrackingMiddleware",
    )

    g["TEMPLATES"][0]["DIRS"] = [base_dir / "templates"]
    _ctx = g["TEMPLATES"][0]["OPTIONS"]["context_processors"]
    _ctx.extend(
        [
            "apps.accounts.context_processors.google_oauth",
            "apps.accounts.context_processors.account_profile",
            "apps.accounts.context_processors.support_contact",
        ],
    )
    g["STATICFILES_DIRS"] = [base_dir / "static_itr"]

    g["MEDIA_URL"] = "/media/"
    g["MEDIA_ROOT"] = base_dir / "media"

    g["ACCOUNT_LOGIN_METHODS"] = {"username", "email"}
    g["ACCOUNT_SIGNUP_FIELDS"] = [
        "email*",
        "username*",
        "password1*",
        "password2*",
    ]
    g["ACCOUNT_ADAPTER"] = "apps.accounts.adapter.ItrAccountAdapter"

    # Default `none`: allauth `optional` still *sends* confirmation mail on signup;
    # without SMTP that send raises → 500 in production. Set `optional` or `mandatory`
    # when EMAIL_HOST / EMAIL_BACKEND can deliver mail.
    _email_verification = (
        os.getenv("ACCOUNT_EMAIL_VERIFICATION", "none").strip().lower()
    )
    if _email_verification not in ("none", "optional", "mandatory"):
        _email_verification = "none"
    g["ACCOUNT_EMAIL_VERIFICATION"] = _email_verification

    g["PRO_PLAN_AMOUNT_PAISE"] = int(
        os.getenv("PRO_PLAN_AMOUNT_PAISE", "49900"),
    )
    g["FREE_EXPORT_LIMIT_PER_MONTH"] = int(
        os.getenv("FREE_EXPORT_LIMIT_PER_MONTH", "5"),
    )
    g["ITR_RAZORPAY_WEBHOOK_SECRET"] = os.getenv(
        "ITR_RAZORPAY_WEBHOOK_SECRET",
        "",
    ).strip()

    g["ITR_ASYNC_EXTRACTION"] = (
        os.getenv("ITR_ASYNC_EXTRACTION", "false").lower() == "true"
    )
    g["COMPUTATION_PDF_FIRM_NAME"] = os.getenv(
        "COMPUTATION_PDF_FIRM_NAME",
        "",
    ).strip()
    g["COMPUTATION_PDF_REPORT_DATE"] = os.getenv(
        "COMPUTATION_PDF_REPORT_DATE",
        "",
    ).strip()

    g["ITR_OUTPUT_RETENTION_HOURS"] = float(
        os.getenv("ITR_OUTPUT_RETENTION_HOURS", "24"),
    )
    g["ITR_DELETE_INPUT_AFTER_EXPORT"] = os.getenv(
        "ITR_DELETE_INPUT_AFTER_EXPORT",
        "true",
    ).lower() in ("1", "true", "yes")

    g["RQ_QUEUES"] = {
        "default": {
            "URL": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            "DEFAULT_TIMEOUT": 480,
        },
    }

    google_id = os.getenv("GOOGLE_CLIENT_ID", "").strip() or str(
        g.get("GOOGLE_OAUTH_CLIENT_ID", "") or "",
    ).strip()
    # Web OAuth needs the OAuth client secret (distinct from GIS client id alone).
    google_secret = (
        os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    )

    g["SOCIALACCOUNT_PROVIDERS"] = {}
    # Register Google only when both id and secret exist (matches template visibility).
    if google_id and google_secret:
        g["SOCIALACCOUNT_PROVIDERS"]["google"] = {
            "SCOPE": ["profile", "email"],
            "AUTH_PARAMS": {"access_type": "online"},
            "APP": {
                "client_id": google_id,
                "secret": google_secret,
                "key": "",
            },
        }

    # Used by templates/account/*.html to show "Continue with Google"
    g["GOOGLE_OAUTH_CONFIGURED"] = bool(google_id and google_secret)
