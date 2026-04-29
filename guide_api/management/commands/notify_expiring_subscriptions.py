"""Notify users whose subscriptions are about to expire (push + optional email)."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from guide_api.models import NotificationDevice, UserSubscription

logger = logging.getLogger(__name__)


def _send_expiry_push(user, days_left: int, sub: UserSubscription) -> bool:
    """Send an Expo push notification about upcoming subscription expiry."""
    from guide_api.push_reminders import (
        EXPO_PUSH_URL,
        POST_EXPO_BATCH,
        _default_post_expo_batch,
        is_expo_push_token,
    )

    devices = list(
        NotificationDevice.objects.filter(user=user, active=True)
    )
    expo_devices = [d for d in devices if is_expo_push_token(d.token)]
    if not expo_devices:
        return False

    plan = (sub.plan or "").capitalize() or "Plan"
    if days_left <= 0:
        title = f"Your {plan} plan has expired"
        body = "Renew to keep your daily guidance, deep mode, and practice tracking."
    elif days_left == 1:
        title = f"Your {plan} plan expires tomorrow"
        body = "Renew now to keep your guidance uninterrupted."
    else:
        title = f"Your {plan} plan expires in {days_left} days"
        body = "Renew to keep deep guidance, daily reminders, and practice tracking."

    messages = [
        {
            "to": d.token,
            "title": title,
            "body": body,
            "data": {"type": "subscription_expiry", "days_left": days_left},
            "sound": "default",
            "priority": "default",
        }
        for d in expo_devices
    ]

    poster = POST_EXPO_BATCH or _default_post_expo_batch
    try:
        poster(messages)
        return True
    except Exception:
        logger.exception("Failed to send expiry push for user %s", user.pk)
        return False


class Command(BaseCommand):
    help = "Send push notifications to users whose subscriptions expire within N days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Notify users expiring within this many days (default: 3).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without actually sending.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        now = timezone.now()
        cutoff = now + timedelta(days=days)

        # Find active subscriptions expiring within the window
        expiring = UserSubscription.objects.filter(
            expires_at__isnull=False,
            expires_at__lte=cutoff,
            expires_at__gte=now - timedelta(days=1),  # Include recently expired (grace)
        ).select_related("user")

        sent = 0
        skipped = 0

        for sub in expiring:
            days_left = max(0, (sub.expires_at - now).days)
            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] Would notify {sub.user.username} "
                    f"(plan={sub.plan}, expires_at={sub.expires_at}, "
                    f"days_left={days_left})"
                )
                sent += 1
                continue

            ok = _send_expiry_push(sub.user, days_left, sub)
            if ok:
                sent += 1
                logger.info(
                    "Sent expiry push to %s (plan=%s, days_left=%d)",
                    sub.user.username,
                    sub.plan,
                    days_left,
                )
            else:
                skipped += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Done: {sent} notified, {skipped} skipped (no push device)."
            )
        )
