"""Unit tests for dataset normalization helpers."""

from django.test import SimpleTestCase, TestCase

from guide_api.dataset_utils import (
    normalize_multiscript_rows,
    to_canonical_csv_rows,
)
from guide_api import services


class MultiScriptDatasetUtilsTests(SimpleTestCase):
    """Validate source row normalization for external dataset ingestion."""

    def test_normalize_multiscript_rows_supports_aliases_and_deduplicates(self):
        """Alias mapping should normalize schema and keep first duplicate row."""
        rows = [
            {
                "chapter_no": "2",
                "verse_number": "47",
                "sanskrit": "कर्मण्येवाधिकारस्ते",
                "english_meaning": "You have a right to your actions...",
                "word-to-word": "karma only your right",
            },
            {
                "Chapter": "2",
                "Verse": "47",
                "Shloka": "duplicate row",
                "EngMeaning": "duplicate english",
            },
            {
                "Chapter": "6",
                "Verse": "5",
                "EngMeaning": "One must elevate the self by the self.",
                "HinMeaning": "मनुष्य स्वयं अपने को ऊपर उठाए।",
            },
        ]

        verses = normalize_multiscript_rows(rows)
        self.assertEqual(len(verses), 2)
        self.assertEqual(verses[0].reference, "2.47")
        self.assertIn("actions", verses[0].english_meaning)
        self.assertEqual(verses[1].reference, "6.5")
        self.assertIn("ऊपर उठाए", verses[1].hindi_meaning)

    def test_to_canonical_csv_rows_matches_expected_schema(self):
        """Canonical CSV renderer should output stable field names."""
        verses = normalize_multiscript_rows(
            [
                {
                    "Chapter": 3,
                    "Verse": 19,
                    "Shloka": "तस्मादसक्तः सततं",
                    "Transliteration": "tasmad asaktah satatam",
                    "HinMeaning": "असक्ति से कर्म करो।",
                    "EngMeaning": "Therefore perform action without attachment.",
                    "WordMeaning": "therefore unattached always",
                }
            ]
        )
        rows = to_canonical_csv_rows(verses)
        self.assertEqual(
            list(rows[0].keys()),
            [
                "ID",
                "Chapter",
                "Verse",
                "Shloka",
                "Transliteration",
                "HinMeaning",
                "EngMeaning",
                "WordMeaning",
            ],
        )
        self.assertEqual(rows[0]["Chapter"], 3)
        self.assertEqual(rows[0]["Verse"], 19)

    def test_normalize_handles_labeled_chapter_and_verse_values(self):
        """Spreadsheet labels like 'Chapter 2' and 'Verse 2.47' should parse."""
        verses = normalize_multiscript_rows(
            [
                {
                    "Title": "Sankhya Yoga",
                    "Chapter": "Chapter 2",
                    "Verse": "Verse 2.47",
                    "Sanskrit Anuvad": "कर्मण्येवाधिकारस्ते",
                    "Hindi Anuvad": "तुझे केवल कर्म करने का अधिकार है।",
                    "Enlgish Translation": "You have a right to perform your duty.",
                }
            ]
        )
        self.assertEqual(len(verses), 1)
        self.assertEqual(verses[0].reference, "2.47")
        self.assertEqual(verses[0].title, "Sankhya Yoga")

    def test_merged_verse_context_prefers_canonical_then_additional_fill(self):
        """Merged context should combine canonical and additional-angle data."""
        original_quote_cache = services._verse_quote_cache
        original_angle_cache = services._verse_additional_angle_cache
        original_merged_cache = services._merged_verse_context_cache
        try:
            services._verse_quote_cache = {
                "2.47": {
                    "sanskrit": "",
                    "transliteration": "",
                    "hindi": "कर्म पर अधिकार है।",
                    "english": "",
                    "word_meaning": "",
                }
            }
            services._verse_additional_angle_cache = {
                "2.47": [
                    {
                        "sanskrit": "कर्मण्येवाधिकारस्ते",
                        "transliteration": "karmany eva adhikaras te",
                        "hindi": "तुझे कर्म करने का अधिकार है।",
                        "english": "You have a right to action alone.",
                        "word_meaning": "action alone your right",
                        "source": "test.json",
                    }
                ]
            }
            services._merged_verse_context_cache = None

            merged = services._merged_verse_context("2.47")
            self.assertIn("कर्मण्येवाधिकारस्ते", merged["sanskrit"])
            self.assertEqual(merged["hindi"], "कर्म पर अधिकार है।")
            self.assertEqual(
                merged["english"],
                "You have a right to action alone.",
            )
            self.assertEqual(len(merged["angles"]), 1)
        finally:
            services._verse_quote_cache = original_quote_cache
            services._verse_additional_angle_cache = original_angle_cache
            services._merged_verse_context_cache = original_merged_cache

    def test_chapter_summary_match_score_boosts_better_fit_chapter(self):
        """Derived chapter summaries should help broad queries prefer the right chapter."""
        original_cache = services._chapter_summary_cache
        try:
            services._chapter_summary_cache = {
                2: {
                    "en": "Krishna teaches wisdom and equanimity.",
                    "hi": "कृष्ण समत्व सिखाते हैं।",
                    "themes": ["anxiety", "purpose"],
                },
                6: {
                    "en": "Krishna teaches meditation, mind-discipline, and focus.",
                    "hi": "कृष्ण ध्यान, मन-नियंत्रण और एकाग्रता सिखाते हैं।",
                    "themes": ["discipline", "anxiety"],
                },
            }
            message = "I cannot control my mind and keep getting distracted."
            chapter_2 = services._chapter_summary_match_score(
                message=message,
                chapter=2,
            )
            chapter_6 = services._chapter_summary_match_score(
                message=message,
                chapter=6,
            )
            self.assertGreater(chapter_6, chapter_2)
        finally:
            services._chapter_summary_cache = original_cache

    def test_author_commentary_text_reads_multi_author_slok_cache(self):
        """Sloka commentary cache should serialize multi-author perspectives."""
        original_cache = services._merged_verse_context_cache
        try:
            services._merged_verse_context_cache = {
                "4.19": {
                    "commentaries": [
                        {"author": "Swami Sivananda", "text": "Right action burns desire."},
                        {"author": "Swami Chinmayananda", "text": "Wisdom purifies intention."},
                    ]
                }
            }
            text = services._author_commentary_text("4.19", limit=2)
            self.assertIn("Swami Sivananda", text)
            self.assertIn("Wisdom purifies intention", text)
        finally:
            services._merged_verse_context_cache = original_cache

    def test_author_commentary_text_prefers_query_relevant_perspective(self):
        """Query-aware commentary selection should bubble up the best-fit author."""
        original_cache = services._merged_verse_context_cache
        try:
            services._merged_verse_context_cache = {
                "6.26": {
                    "commentaries": [
                        {
                            "author": "Author A",
                            "text": "Return the restless mind to the Self through steady discipline and meditation.",
                        },
                        {
                            "author": "Author B",
                            "text": "Offer every action without attachment to fruits.",
                        },
                    ]
                }
            }
            text = services._author_commentary_text(
                "6.26",
                limit=1,
                message="My mind is restless and I cannot focus in meditation.",
            )
            self.assertIn("Author A", text)
            self.assertNotIn("Author B", text)
        finally:
            services._merged_verse_context_cache = original_cache

    def test_author_commentary_text_cleans_noisy_reference_and_glossary_dump(self):
        """Commentary serialization should trim noisy raw reference/glossary fragments."""
        original_cache = services._merged_verse_context_cache
        try:
            services._merged_verse_context_cache = {
                "2.47": {
                    "commentaries": [
                        {
                            "author": "Author A",
                            "text": "।।2.47।। कर्म करने मात्र में तुम्हारा अधिकार है। 2.47 कर्मणि in work? एव only? अधिकारः right? ते thy? मा not?",
                        }
                    ]
                }
            }
            text = services._author_commentary_text("2.47", limit=1)
            self.assertIn("कर्म करने मात्र में तुम्हारा अधिकार है", text)
            self.assertNotIn("कर्मणि in work?", text)
            self.assertNotIn("।।2.47।।", text)
        finally:
            services._merged_verse_context_cache = original_cache


class VedicDatasetIntegrationTests(TestCase):
    """Integration checks for local chapter/sloka data copied into data/."""

    def test_chapter_summary_cache_reads_local_chapter_json_data(self):
        """Copied chapter JSON files should feed chapter summaries when present."""
        original_cache = services._chapter_summary_cache
        try:
            services._chapter_summary_cache = None
            summary = services._load_chapter_summary_cache()
            self.assertIn(4, summary)
            self.assertTrue(summary[4]["en"])
            self.assertTrue(summary[4]["hi"])
        finally:
            services._chapter_summary_cache = original_cache
