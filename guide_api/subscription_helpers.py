"""Shared subscription checks (used by API views and practice workflows)."""

from __future__ import annotations

from django.utils import timezone

from guide_api.models import UserSubscription


def normalize_subscription_state(subscription: UserSubscription) -> UserSubscription:
    """Downgrade expired paid subscriptions to Free and persist the change."""
    if subscription.plan == UserSubscription.PLAN_FREE:
        return subscription
    if (
        subscription.subscription_end_date is not None
        and subscription.subscription_end_date <= timezone.now()
    ):
        subscription.plan = UserSubscription.PLAN_FREE
        subscription.is_active = False
        subscription.subscription_end_date = None
        subscription.save(
            update_fields=[
                "plan",
                "is_active",
                "subscription_end_date",
                "updated_at",
            ],
        )
    return subscription


def user_has_active_pro(user) -> bool:
    """True when the user has an active Pro plan window."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    subscription, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={"plan": UserSubscription.PLAN_FREE},
    )
    subscription = normalize_subscription_state(subscription)
    return (
        subscription.plan == UserSubscription.PLAN_PRO
        and subscription.is_active
        and (
            subscription.subscription_end_date is None
            or subscription.subscription_end_date > timezone.now()
        )
    )
