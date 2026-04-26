"""Send scheduled daily practice push notifications via Expo Push API."""

from django.core.management.base import BaseCommand

from guide_api.push_reminders import run_push_reminders


class Command(BaseCommand):
    help = (
        "Send daily push reminders for users with reminder_enabled, push channel, "
        "and a registered Expo push token. Schedule this every PUSH_REMINDER_WINDOW_MINUTES "
        "(default 15) via cron or a scheduler."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many users would be notified without calling Expo.",
        )
        parser.add_argument(
            "--window",
            type=int,
            default=None,
            help="Reminder match window in minutes (default: PUSH_REMINDER_WINDOW_MINUTES).",
        )

    def handle(self, *args, **options):
        stats = run_push_reminders(
            dry_run=options["dry_run"],
            window_minutes=options["window"],
        )
        self.stdout.write(
            "due_users=%(due_users)s due_messages=%(due_messages)s "
            "sent=%(sent)s deactivated_devices=%(deactivated_devices)s"
            % stats,
        )
