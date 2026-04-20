"""Usage limits for PDF export (free tier vs Pro)."""
from __future__ import annotations

from datetime import date

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import UserProfile


def ensure_profile_month(profile: UserProfile) -> None:
    """Reset monthly export counter when calendar month changes."""
    today = timezone.now().date()
    if (
        profile.export_cycle_year != today.year
        or profile.export_cycle_month != today.month
    ):
        profile.exports_this_month = 0
        profile.export_cycle_year = today.year
        profile.export_cycle_month = today.month
        profile.save(
            update_fields=[
                "exports_this_month",
                "export_cycle_year",
                "export_cycle_month",
            ]
        )


def is_pro_active(profile: UserProfile) -> bool:
    if profile.plan != UserProfile.PLAN_PRO:
        return False
    if not profile.subscription_until:
        return False
    return profile.subscription_until > timezone.now()


def _monthly_free_export_limit() -> int:
    try:
        from apps.accounts.models import QuotaSettings

        return int(QuotaSettings.get_solo().free_exports_per_month)
    except Exception:
        return int(getattr(settings, "FREE_EXPORT_LIMIT_PER_MONTH", 5))


def can_export_pdf(profile: UserProfile) -> tuple[bool, str]:
    """Return (allowed, reason_if_blocked)."""
    ensure_profile_month(profile)
    if is_pro_active(profile):
        return True, ""
    limit = _monthly_free_export_limit()
    if profile.exports_this_month >= limit:
        return (
            False,
            f"Free plan allows {limit} computation PDF exports per month. Upgrade to Pro for unlimited exports.",
        )
    return True, ""


def record_export(profile: UserProfile) -> None:
    ensure_profile_month(profile)
    if is_pro_active(profile):
        return
    profile.exports_this_month += 1
    profile.save(update_fields=["exports_this_month"])
