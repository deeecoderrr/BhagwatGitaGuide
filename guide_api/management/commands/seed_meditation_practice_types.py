"""Management command: seed the Naam Japa Meditation practice type.

Run once (or repeatedly — it is idempotent):
    python manage.py seed_meditation_practice_types

The command only creates/updates MeditationPracticeType rows.
Audio content items are added via Django admin once the audio files are ready.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from guide_api.models import MeditationPracticeType


PRACTICE_TYPES = [
    {
        "slug": "naam-japa",
        "title": "Naam Japa",
        "subtitle": "Devotional Name Repetition",
        "category": MeditationPracticeType.CATEGORY_JAPA,
        "default_access_level": MeditationPracticeType.ACCESS_FREE,
        "counts_as_sadhana": True,
        "sort_order": 10,
        "description": (
            "Naam Japa — the devotional practice of repeating a sacred Name.\n\n"
            "\"Naam\" means Divine Name. \"Japa\" means quiet, steady repetition or "
            "remembrance — aloud, in a whisper, or purely in the heart. Together, "
            "Naam Japa is the act of bringing the mind back, again and again, to a "
            "sacred word or mantra that represents the Divine.\n\n"
            "This is one of the most accessible Bhakti (devotional) practices in the "
            "Bhagavad Gita and the broader Vedic tradition. Krishna himself declares "
            "in the Gita (10.25): 'Of yajnas, I am the japa yajna (sacrifice of "
            "silent repetition).' Naam Japa is therefore not mere mechanical "
            "counting — it is a form of worship, offering attention to the Divine.\n\n"
            "How to practice:\n"
            "• Choose a sacred name or mantra that resonates with you — 'Om', "
            "'Hare Krishna', 'Ram', 'Om Namah Shivaya', 'So Hum', or any name of "
            "the Divine you hold dear.\n"
            "• Sit quietly, with spine gently upright and body relaxed.\n"
            "• Begin repeating the name — aloud, softly, or mentally.\n"
            "• If using a mala (japa rosary of 108 beads), move one bead per "
            "repetition, completing one round (mala) of 108.\n"
            "• When the mind wanders — and it will — gently, without frustration, "
            "bring it back to the Name.\n"
            "• The quality of attention and love matters far more than speed or "
            "quantity.\n\n"
            "Benefits (as recorded in tradition and growing research):\n"
            "• Calms the fluctuating mind (chitta vritti nirodha).\n"
            "• Builds a steady, devotional inner atmosphere.\n"
            "• Reduces anxiety, emotional reactivity, and mental noise.\n"
            "• Cultivates Bhakti — a loving connection to the Divine.\n"
            "• Over time, the Name begins to arise spontaneously in daily life.\n\n"
            "You can use the audio tracks here to learn the pronunciation and melody "
            "of various Naam Japa chants, or to practice together by playing them "
            "on loop while you do your own repetition alongside."
        ),
    },
    # Future types can be added here as rows — no code change needed.
    # {
    #     "slug": "pranayama",
    #     "title": "Pranayama",
    #     "subtitle": "Sacred Breathwork",
    #     "category": MeditationPracticeType.CATEGORY_BREATH,
    #     ...
    # },
]


class Command(BaseCommand):
    help = "Seed Meditation Practice Types (idempotent)."

    def handle(self, *args, **options):
        created = updated = 0
        for pt in PRACTICE_TYPES:
            slug = pt.pop("slug")
            obj, was_created = MeditationPracticeType.objects.update_or_create(
                slug=slug,
                defaults=pt,
            )
            if was_created:
                created += 1
            else:
                updated += 1
            self.stdout.write(
                f"  {'CREATED' if was_created else 'UPDATED'}: {slug} — {obj.title}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created} updated={updated}"
            )
        )
