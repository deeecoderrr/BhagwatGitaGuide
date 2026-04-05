"""Infer and store verse themes using keyword mapping logic."""

from django.core.management.base import BaseCommand

from guide_api.models import Verse
from guide_api.services import infer_themes_from_text


class Command(BaseCommand):
    """Management command to infer and write verse themes."""

    help = "Auto-tag verse themes from translation/commentary keywords."

    def add_arguments(self, parser):
        """Define dry-run and overwrite behavior for tagging."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show updates without writing to DB.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing themes instead of merging.",
        )

    def handle(self, *args, **options):
        """Iterate verses, infer themes, and save changes when needed."""
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        updated = 0
        unchanged = 0
        no_match = 0

        for verse in Verse.objects.all():
            text = f"{verse.translation} {verse.commentary}"
            inferred = infer_themes_from_text(text)
            inferred_list = sorted(inferred)

            if overwrite:
                next_themes = inferred_list
            else:
                next_themes = sorted(set(verse.themes) | inferred)

            if not inferred:
                no_match += 1

            if next_themes == verse.themes:
                unchanged += 1
                continue

            updated += 1
            if not dry_run:
                verse.themes = next_themes
                verse.save(update_fields=["themes"])

        summary = (
            f"Theme tagging complete. updated={updated} unchanged={unchanged} "
            f"no_match={no_match} dry_run={dry_run} overwrite={overwrite}"
        )
        self.stdout.write(self.style.SUCCESS(summary))
