"""Send streak-at-risk push notifications via Expo Push API."""

from django.core.management.base import BaseCommand

from guide_api.push_reminders import run_streak_risk_reminders


class Command(BaseCommand):
    help = (
        "Send streak-at-risk push reminders to users with an active streak who "
        "have not opened the app today. Run this once after 8pm server time or "
        "schedule at a fixed local evening time."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many users would be notified without calling Expo.",
        )
        parser.add_argument(
            "--risk-hour",
            type=int,
            default=20,
            help="Local hour (0-23) after which the streak is considered at risk (default: 20).",
        )

    def handle(self, *args, **options):
        stats = run_streak_risk_reminders(
            dry_run=options["dry_run"],
            risk_hour=options["risk_hour"],
        )
        self.stdout.write(
            "due_users=%(due_users)s sent=%(sent)s deactivated_devices=%(deactivated_devices)s"
            % stats,
        )
