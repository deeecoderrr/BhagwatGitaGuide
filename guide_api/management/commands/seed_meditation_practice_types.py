"""Management command: seed the Naam Japa Meditation practice type.

Run once (or repeatedly — it is idempotent):
    python manage.py seed_meditation_practice_types

The command creates/updates MeditationPracticeType rows AND their audio content
items. Safe to re-run after adding new content entries.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from guide_api.models import MeditationPracticeContent, MeditationPracticeType


PRACTICE_TYPES = [
    {
        "slug": "naam-japa",
        "title": "Naam Japa",
        "subtitle": "Devotional Name Repetition",
        "category": MeditationPracticeType.CATEGORY_JAPA,
        "default_access_level": MeditationPracticeType.ACCESS_FREE,
        "counts_as_sadhana": True,
        "sort_order": 10,
        "cover_url": "",
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
    {
        "slug": "mantra-chanting",
        "title": "Mantra Chanting",
        "subtitle": "Sacred Sound Invocation",
        "category": MeditationPracticeType.CATEGORY_MANTRA,
        "default_access_level": MeditationPracticeType.ACCESS_FREE,
        "counts_as_sadhana": True,
        "sort_order": 20,
        "cover_url": "https://res.cloudinary.com/dqjnojvit/image/upload/v1778006459/mantrachanting_rxklvq.png",
        "description": (
            "Mantra Chanting — the practice of vocalising sacred Sanskrit sound formulas with "
            "precise syllabic power.\n\n"
            "\"Mantra\" comes from two Sanskrit roots: \"manas\" (mind) and \"trayate\" (that which "
            "liberates). A mantra is therefore a sacred sound that liberates the mind — not through "
            "meaning alone, but through the vibratory quality of its syllables.\n\n"
            "Unlike Naam Japa, which centres on the devotional repetition of a divine name, Mantra "
            "Chanting works through precise Sanskrit formulations — often called \"beej mantras\" "
            "(seed syllables) — that carry encoded vibratory frequencies. When chanted correctly "
            "and consistently, these sounds are said to restructure the subtle body, clear energetic "
            "blockages, and invoke the specific quality or deity embedded in the mantra.\n\n"
            "The Vedic tradition holds that the universe itself arose from sound (Nada Brahman — "
            "Brahman as cosmic vibration). The 'Om' that begins most mantras is the primordial sound "
            "from which all creation emerged. Every mantra is an echo of that origination.\n\n"
            "How to practice:\n"
            "\u2022 Sit with the spine upright, body relaxed, eyes gently closed.\n"
            "\u2022 Take three slow breaths to settle the mind before beginning.\n"
            "\u2022 Chant aloud first — let the sound fill the space around you and return to you.\n"
            "\u2022 As the session progresses, move to a whisper, then to silent mental repetition.\n"
            "\u2022 Moving from outer sound inward to silence is the classical three-stage approach.\n"
            "\u2022 Pronunciation matters — learn it carefully from the audio tracks here.\n"
            "\u2022 108 repetitions (one mala) is the traditional complete round.\n\n"
            "What happens as you practice:\n"
            "\u2022 Initially, the mantra occupies the mind and crowds out distracting thoughts.\n"
            "\u2022 With regular practice, the mantra begins to arise spontaneously during the day.\n"
            "\u2022 Eventually, the practitioner does not chant the mantra — the mantra chants itself.\n"
            "\u2022 This state — called \"Ajapa Japa\" (the unchanted chant) — is the fruit of practice.\n\n"
            "Benefits (as recorded in tradition and growing research):\n"
            "\u2022 Activates the relaxation response; reduces cortisol and anxiety.\n"
            "\u2022 Invokes the specific quality of the presiding deity — protection, courage, clarity.\n"
            "\u2022 Creates a stable energetic atmosphere in the home or space of chanting.\n"
            "\u2022 Trains the faculty of one-pointed attention (dharana).\n"
            "\u2022 Builds a direct, living relationship with the divine form in the mantra.\n\n"
            "Use the audio tracks here to learn correct pronunciation and rhythm, or to practice "
            "alongside an established chant while you develop your own."
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

# Content entries keyed by practice_type slug → list of audio tracks.
# Identified by (practice_type, title) — safe to re-run (update_or_create).
PRACTICE_CONTENT: dict[str, list[dict]] = {
    "mantra-chanting": [
        {
            "title": "Om Shri Kaal Bhairavaaye Namah",
            "subtitle": "",
            "description": "",
            "content_type": "audio",
            "media_url": "https://pub-c6209ba8767b49ecbd104de0ccd380ab.r2.dev/Audio/mantrachanting/omshrikaalbhairavaayenamh.mp4",
            "thumbnail_url": "https://res.cloudinary.com/dqjnojvit/image/upload/v1778007521/ChatGPT_Image_May_6_2026_12_28_22_AM_glugcw.png",
            "duration_seconds": None,
            "language": "hi",
            "teacher": "",
            "mantra_name": "Kaal Bhairava",
            "supports_loop": True,
            "mode": "practice",
            "access_level": "free",
            "is_active": True,
            "sort_order": 1,
        },
    ],
    "naam-japa": [
        {
            "title": "Shree Radha Naam Jap",
            "subtitle": "",
            "description": "",
            "content_type": "audio",
            "media_url": "https://pub-c6209ba8767b49ecbd104de0ccd380ab.r2.dev/Audio/Naam%20Japa/shreeradhanaamjap.mp4",
            "thumbnail_url": "",
            "duration_seconds": None,
            "language": "hi",
            "teacher": "",
            "mantra_name": "Radha",
            "supports_loop": True,
            "mode": "practice",
            "access_level": "free",
            "is_active": True,
            "sort_order": 1,
        },
        {
            "title": "Samb Sadashiv Naam Jap",
            "subtitle": "",
            "description": "",
            "content_type": "audio",
            "media_url": "https://pub-c6209ba8767b49ecbd104de0ccd380ab.r2.dev/Audio/Naam%20Japa/ShambhSadaShiv.mp4",
            "thumbnail_url": "https://res.cloudinary.com/dqjnojvit/image/upload/v1778004649/ace9388b-6353-497f-8c21-a8c2770bcc6f_otbvrk.png",
            "duration_seconds": None,
            "language": "hi",
            "teacher": "",
            "mantra_name": "Samb Sadashiv",
            "supports_loop": True,
            "mode": "practice",
            "access_level": "free",
            "is_active": True,
            "sort_order": 2,
        },
    ],
}


class Command(BaseCommand):
    help = "Seed Meditation Practice Types and their content (idempotent)."

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

            # Seed content items for this practice type
            for item in PRACTICE_CONTENT.get(slug, []):
                title = item["title"]
                defaults = {k: v for k, v in item.items() if k != "title"}
                _, c_created = MeditationPracticeContent.objects.update_or_create(
                    practice_type=obj,
                    title=title,
                    defaults=defaults,
                )
                self.stdout.write(
                    f"    content {'CREATED' if c_created else 'UPDATED'}: {title}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. practice_types created={created} updated={updated}"
            )
        )
