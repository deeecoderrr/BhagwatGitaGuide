"""Import Bhagavad Gita verses from JSON into the Verse table."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from guide_api.models import Verse


class Command(BaseCommand):
    """Management command to upsert verse records from JSON payload."""

    help = "Import Bhagavad Gita verses from a JSON file."

    def add_arguments(self, parser):
        """Define CLI options for file path and validation behavior."""
        parser.add_argument(
            "--file",
            required=True,
            help="Path to JSON file containing verse records.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report counts without writing to DB.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail on first invalid row instead of skipping invalid rows.",
        )

    def handle(self, *args, **options):
        """Validate input rows and upsert verses into the database."""
        file_path = Path(options["file"])
        dry_run = options["dry_run"]
        strict = options["strict"]

        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        if not isinstance(payload, list):
            raise CommandError(
                "Top-level JSON must be a list of verse objects.",
            )

        created = 0
        updated = 0
        skipped = 0
        errors = 0

        for idx, row in enumerate(payload, start=1):
            validation_error = self._validate_row(row)
            if validation_error:
                errors += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Row {idx} skipped: {validation_error}",
                    )
                )
                if strict:
                    raise CommandError(f"Strict mode error at row {idx}")
                continue

            chapter = row["chapter"]
            verse = row["verse"]
            translation = row["translation"].strip()
            commentary = str(row.get("commentary", "")).strip()
            themes = row.get("themes", [])

            if dry_run:
                existing = Verse.objects.filter(
                    chapter=chapter,
                    verse=verse,
                ).exists()
                if existing:
                    updated += 1
                else:
                    created += 1
                continue

            _, created_flag = Verse.objects.update_or_create(
                chapter=chapter,
                verse=verse,
                defaults={
                    "translation": translation,
                    "commentary": commentary,
                    "themes": themes,
                    "embedding": [],
                },
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        processed = len(payload) - errors
        skipped += errors
        summary = (
            f"Import complete. total={len(payload)} processed={processed} "
            f"created={created} updated={updated} skipped={skipped} "
            f"dry_run={dry_run}"
        )
        self.stdout.write(self.style.SUCCESS(summary))

    @staticmethod
    def _validate_row(row):
        """Return validation error string or None when row is valid."""
        if not isinstance(row, dict):
            return "row is not an object"

        required_fields = ["chapter", "verse", "translation"]
        missing = [field for field in required_fields if field not in row]
        if missing:
            return f"missing required fields: {', '.join(missing)}"

        chapter = row.get("chapter")
        verse = row.get("verse")
        translation = row.get("translation")
        themes = row.get("themes", [])

        if not isinstance(chapter, int) or chapter <= 0:
            return "chapter must be a positive integer"
        if not isinstance(verse, int) or verse <= 0:
            return "verse must be a positive integer"
        if not isinstance(translation, str) or not translation.strip():
            return "translation must be a non-empty string"
        if not isinstance(themes, list):
            return "themes must be a list when provided"
        if any(not isinstance(theme, str) for theme in themes):
            return "all themes values must be strings"

        return None
