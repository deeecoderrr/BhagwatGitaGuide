"""Delete expired ITR PDF blobs from storage (schedule via cron)."""

from django.core.management.base import BaseCommand

from apps.exports.retention import purge_expired_exports


class Command(BaseCommand):
    help = "Remove ITR summary PDFs past ITR_OUTPUT_RETENTION_HOURS (DB rows kept)."

    def handle(self, *args, **options):
        n = purge_expired_exports()
        self.stdout.write(self.style.SUCCESS(f"Purged {n} expired export file(s)."))
