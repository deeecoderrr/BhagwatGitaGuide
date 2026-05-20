"""Export quota logic — annual plans (Essentials / Professional) + Pay-as-you-go credits."""
from __future__ import annotations

from django.utils import timezone

from apps.accounts.models import UserProfile


def is_pro_active(profile: UserProfile) -> bool:
    """Legacy helper - kept for backward compat."""
    if profile.plan != UserProfile.PLAN_PRO:
        return False
    if not profile.subscription_until:
        return False
    return profile.subscription_until > timezone.now()


def _annual_plan_active(profile: UserProfile) -> tuple[bool, int]:
    """Return (is_active, export_limit) for the user's current annual plan."""
    if not profile.itr_plan or not profile.itr_plan_until:
        return False, 0
    if profile.itr_plan_until <= timezone.now():
        return False, 0
    limit = UserProfile.ANNUAL_EXPORT_LIMITS.get(profile.itr_plan, 0)
    return True, limit


def can_export_pdf(profile: UserProfile) -> tuple[bool, str]:
    """Return (allowed, reason_if_blocked).

    Priority:
      1. Active annual plan with remaining exports -> allowed.
      2. Pay-as-you-go credit balance -> allowed.
      3. Blocked - must purchase.
    """
    active, limit = _annual_plan_active(profile)
    if active:
        if profile.itr_annual_exports_used < limit:
            return True, ""
        label = profile.itr_plan.title()
        return (
            False,
            f"You've used all {limit} exports on your {label} annual plan. "
            "Renew your plan or top up with Pay-as-you-go.",
        )

    # Expired annual plan message
    if profile.itr_plan and profile.itr_plan_until and profile.itr_plan_until <= timezone.now():
        label = profile.itr_plan.title()
        return (
            False,
            f"Your {label} annual plan expired. Renew to continue exporting.",
        )

    # PAYG credit wallet
    if profile.itr_export_credits > 0:
        return True, ""

    return False, "Purchase a plan to generate PDF exports."


def record_export(profile: UserProfile) -> None:
    """Consume one export - deducts from annual plan first, then PAYG credits."""
    active, _ = _annual_plan_active(profile)
    if active:
        profile.itr_annual_exports_used += 1
        profile.save(update_fields=["itr_annual_exports_used"])
    elif profile.itr_export_credits > 0:
        profile.itr_export_credits -= 1
        profile.save(update_fields=["itr_export_credits"])


def can_export_pdf_anonymous(request) -> tuple[bool, str]:
    """Anonymous users must create an account and purchase a plan."""
    return (
        False,
        "Create an account and purchase a plan to generate PDF exports.",
    )


def record_export_anonymous(request) -> None:
    """No-op - anonymous users cannot export."""
    pass
