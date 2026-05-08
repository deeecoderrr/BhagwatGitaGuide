"""Management command to migrate media URLs from an old base to a new CDN base.

Usage:
  python manage.py update_media_cdn_url \\
    --old-base https://old-storage.example.com \\
    --new-base https://cdn.askbhagavadgita.co.in \\
    [--dry-run]

This updates:
  - SadhanaStep.audio_url / .video_url
  - PracticeWorkflowStep.audio_url
  - JapaCommitment.audio_url  (if field exists)
  - MeditationPracticeType.audio_url (if field exists)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Bulk-replace a media URL prefix across all relevant model fields."

    def add_arguments(self, parser):
        parser.add_argument("--old-base", required=True, help="URL prefix to replace (no trailing slash)")
        parser.add_argument("--new-base", required=True, help="New URL prefix (no trailing slash)")
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")

    def handle(self, *args, **options):
        old = options["old_base"].rstrip("/")
        new = options["new_base"].rstrip("/")
        dry = options["dry_run"]

        if not old or not new:
            raise CommandError("Both --old-base and --new-base are required.")
        if old == new:
            raise CommandError("--old-base and --new-base are identical; nothing to do.")

        self.stdout.write(f"{'[DRY RUN] ' if dry else ''}Replacing: {old!r} → {new!r}\n")

        total_updated = 0

        # ── SadhanaStep ─────────────────────────────────────────────────────
        try:
            from guide_api.models import SadhanaStep
            total_updated += self._update_url_fields(
                SadhanaStep, ["audio_url", "video_url"], old, new, dry
            )
        except ImportError:
            pass

        # ── PracticeWorkflowStep ─────────────────────────────────────────────
        try:
            from guide_api.models import PracticeWorkflowStep
            total_updated += self._update_url_fields(
                PracticeWorkflowStep, ["audio_url"], old, new, dry
            )
        except ImportError:
            pass

        # ── JapaCommitment ───────────────────────────────────────────────────
        try:
            from guide_api.models import JapaCommitment
            fields = [
                f.name for f in JapaCommitment._meta.get_fields()
                if hasattr(f, "name") and "audio" in f.name.lower()
            ]
            if fields:
                total_updated += self._update_url_fields(JapaCommitment, fields, old, new, dry)
        except ImportError:
            pass

        # ── MeditationPracticeType / MeditationPracticeItem ─────────────────
        for model_name in ("MeditationPracticeType", "MeditationPracticeItem"):
            try:
                from guide_api import models as m
                Model = getattr(m, model_name, None)
                if Model:
                    fields = [
                        f.name for f in Model._meta.get_fields()
                        if hasattr(f, "name") and ("audio" in f.name.lower() or "media" in f.name.lower())
                    ]
                    if fields:
                        total_updated += self._update_url_fields(Model, fields, old, new, dry)
            except ImportError:
                pass

        verb = "Would update" if dry else "Updated"
        self.stdout.write(self.style.SUCCESS(f"\n{verb} {total_updated} field value(s) across all models."))
        if dry:
            self.stdout.write("Re-run without --dry-run to apply changes.")

    def _update_url_fields(self, Model, fields: list[str], old: str, new: str, dry: bool) -> int:
        """Replace old prefix in each URLField for matching rows."""
        from django.db.models import Q, Value
        from django.db.models.functions import Replace

        updated_total = 0
        for field in fields:
            # Only touch rows where the field starts with old prefix
            qs = Model.objects.filter(**{f"{field}__startswith": old})
            count = qs.count()
            if count == 0:
                continue

            self.stdout.write(
                f"  {Model.__name__}.{field}: {count} row(s) to update"
            )

            if not dry:
                with transaction.atomic():
                    qs.update(
                        **{field: Replace(field, Value(old), Value(new))}
                    )
            updated_total += count

        return updated_total
