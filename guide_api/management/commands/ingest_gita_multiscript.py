"""Normalize Kaggle multi-script source as additive dataset."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from guide_api.dataset_utils import (
    load_multiscript_rows,
    normalize_multiscript_rows,
    write_canonical_csv,
)
from guide_api.models import Verse


class Command(BaseCommand):
    """Ingest CSV/XLSX Gita data into canonical local dataset artifacts."""

    help = (
        "Ingest multi-script Bhagavad Gita data from CSV/XLSX as additional "
        "angle dataset, with optional canonical file updates."
    )

    def add_arguments(self, parser):
        """Define CLI options for source, outputs, and DB sync behavior."""
        parser.add_argument(
            "--input",
            required=True,
            help="Path to source CSV/XLSX file (for example Kaggle export).",
        )
        parser.add_argument(
            "--sheet",
            default="",
            help="Optional worksheet name when input is XLSX.",
        )
        parser.add_argument(
            "--output-csv",
            default="data/Bhagwad_Gita.csv",
            help="Canonical CSV output path when --update-canonical is set.",
        )
        parser.add_argument(
            "--output-json",
            default="data/gita_700.json",
            help="Importer JSON output path when --update-canonical is set.",
        )
        parser.add_argument(
            "--angles-output",
            default="data/gita_additional_angles.json",
            help=(
                "Output path for additive angle dataset used to enrich "
                "retrieval and prompting."
            ),
        )
        parser.add_argument(
            "--import-db",
            action="store_true",
            help=(
                "Upsert rows into Verse table. Recommended with "
                "--update-canonical."
            ),
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="When --import-db is set, overwrite existing translation data.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and print summary without writing files or DB.",
        )
        parser.add_argument(
            "--update-canonical",
            action="store_true",
            help=(
                "Also refresh canonical CSV/JSON files. By default, command "
                "only writes additive angle dataset."
            ),
        )

    def _merge_additional_angles(
        self,
        *,
        existing_rows: list[dict],
        source_path: Path,
        verses,
    ) -> list[dict]:
        """Merge additional verse angles while avoiding duplicate entries."""
        merged = []
        seen = set()

        for row in existing_rows:
            reference = str(row.get("reference", "")).strip()
            english = str(row.get("english", "")).strip()
            key = (reference, english.lower())
            if not reference or key in seen:
                continue
            seen.add(key)
            merged.append(row)

        source_name = source_path.name
        for verse in verses:
            reference = verse.reference
            english = verse.english_meaning.strip()
            key = (reference, english.lower())
            if not english or key in seen:
                continue
            seen.add(key)
            merged.append(
                {
                    "reference": reference,
                    "chapter": verse.chapter,
                    "verse": verse.verse,
                    "title": verse.title,
                    "sanskrit": verse.shloka,
                    "transliteration": verse.transliteration,
                    "hindi": verse.hindi_meaning,
                    "english": english,
                    "word_meaning": verse.word_meaning,
                    "source": source_name,
                }
            )

        merged.sort(
            key=lambda item: (
                int(item.get("chapter", 0)),
                int(item.get("verse", 0)),
                str(item.get("source", "")),
                str(item.get("english", "")),
            )
        )
        return merged

    def handle(self, *args, **options):
        """Load, normalize, persist artifacts, and optionally import rows."""
        input_path = Path(options["input"]).expanduser().resolve()
        output_csv = Path(options["output_csv"]).resolve()
        output_json = Path(options["output_json"]).resolve()
        angles_output = Path(options["angles_output"]).resolve()
        sheet_name = (options.get("sheet") or "").strip() or None
        should_import_db = bool(options["import_db"])
        overwrite = bool(options["overwrite"])
        dry_run = bool(options["dry_run"])
        update_canonical = bool(options["update_canonical"])

        if not input_path.exists():
            raise CommandError(f"Input file not found: {input_path}")

        try:
            raw_rows = load_multiscript_rows(path=input_path, sheet=sheet_name)
            verses = normalize_multiscript_rows(raw_rows)
        except Exception as exc:
            raise CommandError(f"Failed to ingest source: {exc}") from exc

        if not verses:
            raise CommandError("No valid verse rows found in source file.")

        payload = [
            {
                "chapter": verse.chapter,
                "verse": verse.verse,
                "translation": verse.english_meaning,
                # Prefer word meaning as concise commentary signal.
                "commentary": verse.word_meaning or verse.transliteration,
                "themes": [],
            }
            for verse in verses
        ]

        self.stdout.write(
            f"Parsed rows: {len(raw_rows)} | valid verses: {len(verses)}"
        )

        existing_angles = []
        if angles_output.exists():
            try:
                existing_angles = json.loads(
                    angles_output.read_text(encoding="utf-8")
                )
            except Exception:
                existing_angles = []
        merged_angles = self._merge_additional_angles(
            existing_rows=existing_angles,
            source_path=input_path,
            verses=verses,
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run only: no writes made."))
            self.stdout.write(f"First verse: {payload[0]['chapter']}.{payload[0]['verse']}")
            self.stdout.write(
                f"Additional angles rows after merge: {len(merged_angles)}"
            )
            self.stdout.write(
                self.style.SUCCESS("Validation complete."),
            )
            return

        angles_output.parent.mkdir(parents=True, exist_ok=True)
        angles_output.write_text(
            json.dumps(merged_angles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        created = 0
        updated = 0
        if update_canonical:
            write_canonical_csv(path=output_csv, verses=verses)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if should_import_db:
            for row in payload:
                verse, was_created = Verse.objects.get_or_create(
                    chapter=row["chapter"],
                    verse=row["verse"],
                    defaults={
                        "translation": row["translation"],
                        "commentary": row["commentary"],
                        "themes": row["themes"],
                    },
                )
                if was_created:
                    created += 1
                    continue
                if overwrite:
                    verse.translation = row["translation"]
                    verse.commentary = row["commentary"]
                    verse.save(update_fields=["translation", "commentary"])
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Ingestion complete "
                f"(angles={angles_output}, canonical_updated={update_canonical}, "
                f"csv={output_csv if update_canonical else 'unchanged'}, "
                f"json={output_json if update_canonical else 'unchanged'}, "
                f"created={created}, updated={updated})"
            )
        )
