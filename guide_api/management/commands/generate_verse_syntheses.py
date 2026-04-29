"""Bulk-generate VerseSynthesis rows for all Verse objects that lack one."""
from __future__ import annotations

import hashlib
import json
import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from guide_api.models import Verse, VerseSynthesis

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are a Bhagavad Gita scholar. Given the original verse text, its translation,
word-for-word meanings, and all available commentary, produce an integrated
synthesis. Respond ONLY with valid JSON matching this exact shape:

{
  "overview_en": "...",
  "overview_hi": "...",
  "commentary_consensus_en": "...",
  "commentary_consensus_hi": "...",
  "life_application_en": "...",
  "life_application_hi": "...",
  "key_points_en": ["...", "..."],
  "key_points_hi": ["...", "..."]
}

Guidelines:
- overview: 2-3 sentence essence of the verse.
- commentary_consensus: A bridge across the major acharya commentaries, noting
  agreement and gentle distinctions (Shankaracharya, Ramanujacharya, Madhvacharya, etc.).
- life_application: How this verse applies to an everyday modern seeker's life.
- key_points: 3-5 bullet points capturing the most important teachings.
- Hi fields should be written in simple, accessible Hindi (Devanagari).
"""


def _build_verse_context(verse: Verse) -> str:
    """Gather all available text for the verse into a prompt context block."""
    parts = [f"Bhagavad Gita {verse.chapter}.{verse.verse}"]

    if verse.text:
        parts.append(f"\nSanskrit:\n{verse.text}")
    if verse.transliteration:
        parts.append(f"\nTransliteration:\n{verse.transliteration}")
    if verse.word_meanings:
        parts.append(f"\nWord-for-word:\n{verse.word_meanings}")
    if verse.translation_en:
        parts.append(f"\nTranslation (EN):\n{verse.translation_en}")
    if verse.translation_hi:
        parts.append(f"\nTranslation (HI):\n{verse.translation_hi}")
    if verse.meaning_plain:
        parts.append(f"\nMeaning (plain):\n{verse.meaning_plain}")

    # Include all commentaries
    for field in [
        "shankaracharya_commentary",
        "ramanujacharya_commentary",
        "madhvacharya_commentary",
        "vallabhacharya_commentary",
        "chinmayananda_commentary",
    ]:
        text = getattr(verse, field, None) or ""
        if text.strip():
            label = field.replace("_commentary", "").title()
            parts.append(f"\n{label} Commentary:\n{text.strip()}")

    return "\n".join(parts)


def _source_hash(context: str) -> str:
    return hashlib.sha256(context.encode()).hexdigest()[:32]


def _call_openai(context: str) -> dict | None:
    """Call OpenAI and parse JSON response."""
    try:
        import openai
    except ImportError:
        logger.error("openai package not installed. pip install openai")
        return None

    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        logger.error("OPENAI_API_KEY not configured.")
        return None

    client = openai.OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.4,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception:
        logger.exception("OpenAI call failed")
        return None


class Command(BaseCommand):
    help = "Generate VerseSynthesis for verses that don't have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--chapter",
            type=int,
            default=0,
            help="Only process verses from this chapter (0 = all).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max number of verses to process (0 = unlimited).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be generated without calling OpenAI.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate even if a synthesis already exists.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep between API calls (rate-limit safety).",
        )

    def handle(self, *args, **options):
        chapter = options["chapter"]
        limit = options["limit"]
        dry_run = options["dry_run"]
        force = options["force"]
        sleep_sec = options["sleep"]

        qs = Verse.objects.all().order_by("chapter", "verse")
        if chapter:
            qs = qs.filter(chapter=chapter)

        if not force:
            existing_ids = set(
                VerseSynthesis.objects.values_list("verse_id", flat=True)
            )
            qs = qs.exclude(id__in=existing_ids)

        verses = list(qs)
        if limit:
            verses = verses[:limit]

        total = len(verses)
        self.stdout.write(f"Found {total} verse(s) to process.")

        created = 0
        failed = 0

        for i, verse in enumerate(verses, 1):
            ref = f"BG {verse.chapter}.{verse.verse}"
            context = _build_verse_context(verse)
            s_hash = _source_hash(context)

            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] [{i}/{total}] Would generate synthesis for {ref}"
                )
                created += 1
                continue

            self.stdout.write(f"[{i}/{total}] Generating synthesis for {ref}...")
            data = _call_openai(context)

            if not data:
                self.stderr.write(f"  ✗ Failed for {ref}")
                failed += 1
                continue

            VerseSynthesis.objects.update_or_create(
                verse=verse,
                defaults={
                    "source_hash": s_hash,
                    "generation_source": VerseSynthesis.SOURCE_LLM,
                    "overview_en": data.get("overview_en", ""),
                    "overview_hi": data.get("overview_hi", ""),
                    "commentary_consensus_en": data.get("commentary_consensus_en", ""),
                    "commentary_consensus_hi": data.get("commentary_consensus_hi", ""),
                    "life_application_en": data.get("life_application_en", ""),
                    "life_application_hi": data.get("life_application_hi", ""),
                    "key_points_en": data.get("key_points_en", []),
                    "key_points_hi": data.get("key_points_hi", []),
                },
            )
            created += 1
            self.stdout.write(f"  ✓ {ref}")

            if sleep_sec > 0 and i < total:
                time.sleep(sleep_sec)

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Done: {created} created, {failed} failed, {total} total."
            )
        )
