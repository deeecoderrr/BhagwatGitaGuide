from __future__ import annotations

"""Domain services for safety checks, retrieval, and guidance generation."""

from dataclasses import dataclass
import csv
import hashlib
import json
import logging
import math
import re
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from openai import OpenAI

from guide_api.data.default_verses import DEFAULT_VERSES
from guide_api.models import Verse, VerseSynthesis

logger = logging.getLogger(__name__)
_seed_synced = False
SUPPORTED_LANGUAGE_CODES = {"en", "hi"}
VERSE_SYNTHESIS_SCHEMA_VERSION = "v2"
_verse_quote_cache: dict[str, dict[str, str]] | None = None
_verse_additional_angle_cache: dict[str, list[dict[str, str]]] | None = None
_merged_verse_context_cache: dict[str, dict[str, object]] = {}
_chapter_summary_cache: dict[int, dict[str, object]] | None = None
_vedic_slok_cache: dict[str, dict[str, object]] = {}

RISK_KEYWORDS = {
    "suicide",
    "kill myself",
    "self harm",
    "hurt myself",
    "hurt someone",
    "kill someone",
    "stop medication",
    "legal advice",
}

THEME_KEYWORDS = {
    "anxiety": {
        "anxiety",
        "anxious",
        "overthinking",
        "worry",
        "worried",
        "fear",
        "stressed",
        "stress",
        "panic",
        "uncertain",
        "uncertainty",
        "tension",
        "stress",
        "chinta",
        "dar",
        "ghabrahat",
        "ghabrahat",
        "चिंता",
        "तनाव",
        "डर",
        "घबराहट",
        "बेचैनी",
    },
    "career": {
        "career",
        "job",
        "work",
        "promotion",
        "office",
        "boss",
        "salary",
        "performance",
        "naukri",
        "kaam",
        "office",
        "promotion",
        "kariyar",
        "career growth",
        "करियर",
        "नौकरी",
        "काम",
        "प्रमोशन",
    },
    "relationships": {
        "relationship",
        "marriage",
        "partner",
        "family",
        "friends",
        "wife",
        "husband",
        "breakup",
        "rishte",
        "family",
        "ghar",
        "rishta",
        "relationship issue",
        "रिश्ता",
        "रिश्ते",
        "परिवार",
        "घर",
        "संबंध",
    },
    "anger": {
        "anger",
        "angry",
        "frustrated",
        "rage",
        "irritated",
        "gussa",
        "irritation",
        "annoyed",
        "frustration",
        "गुस्सा",
        "क्रोध",
        "चिड़चिड़ापन",
        "खीझ",
    },
    "discipline": {
        "discipline",
        "habit",
        "consistency",
        "focus",
        "routine",
        "procrastinate",
        "procrastination",
        "lazy",
        "delay",
        "distracted",
        "important",
        "study",
        "routine",
        "aadat",
        "anushasan",
        "focus nahi",
        "procrastination",
        "अनुशासन",
        "आदत",
        "दिनचर्या",
        "ध्यान",
        "एकाग्रता",
        "टालमटोल",
    },
    "purpose": {
        "purpose",
        "meaning",
        "lost",
        "direction",
        "calling",
        "path",
        "choose",
        "choice",
        "duty",
        "right",
        "responsibility",
        "empty",
        "hopeless",
        "stuck",
        "uncertain",
        "confused",
        "confusion",
        "directionless",
        "stuck",
        "path",
        "life path",
        "jeevan",
        "uddeshya",
        "मार्ग",
        "उद्देश्य",
        "जीवन का अर्थ",
        "भ्रम",
        "दिशाहीन",
    },
    "comparison": {
        "compare",
        "comparison",
        "jealous",
        "envy",
        "inferior",
        "recognition",
        "praise",
        "others",
        "worth",
        "superior",
        "inferior",
        "measure",
        "jalan",
        "tulna",
        "comparison",
        "self-worth",
        "recognition",
        "तुलना",
        "जलन",
        "ईर्ष्या",
        "हीन",
        "मान-सम्मान",
    },
    "mortality": {
        "war",
        "death",
        "die",
        "dying",
        "dead",
        "destroy",
        "destruction",
        "kill",
        "killed",
        "mortal",
        "mortality",
        "will i die",
        "afterlife",
        "soul",
        "immortal",
        "rebirth",
        "safe",
        "safety",
        "protect",
        "protection",
        "survive",
        "survival",
        "weapon",
        "weapons",
        "violence",
        "conflict",
        "battle",
        "battlefield",
        "world war",
        "nuclear",
        "bomb",
        "end of world",
        "apocalypse",
        "doomsday",
        "mrityu",
        "maut",
        "marna",
        "yuddh",
        "jung",
        "atma",
        "aatma",
        "punarjanm",
        "suraksha",
        "मृत्यु",
        "मौत",
        "मरना",
        "युद्ध",
        "जंग",
        "नाश",
        "विनाश",
        "आत्मा",
        "पुनर्जन्म",
        "सुरक्षा",
        "हथियार",
    },
}
STOPWORDS = {
    "a",
    "an",
    "the",
    "to",
    "for",
    "of",
    "in",
    "on",
    "at",
    "is",
    "am",
    "are",
    "was",
    "were",
    "be",
    "i",
    "me",
    "my",
    "you",
    "your",
    "it",
    "this",
    "that",
    "and",
    "or",
    "but",
    "with",
    "about",
    "feel",
    "feeling",
    "life",
    "really",
    "very",
    "always",
    "never",
    "today",
    "cannot",
    "cant",
    "keep",
    "want",
    "just",
    "much",
    "thing",
    "things",
}

THEME_REFERENCE_PRIORS = {
    "anxiety": {"2.47", "2.48", "6.5", "6.26", "6.35", "18.58", "18.66"},
    "anger": {"2.62", "2.63", "3.27", "3.30", "3.37", "16.21"},
    "career": {"2.47", "3.19", "3.30", "18.58"},
    "relationships": {"12.13", "12.15", "16.21"},
    "discipline": {"6.12", "6.26", "6.35", "3.19", "3.8", "2.48", "18.58"},
    "purpose": {"3.35", "18.47", "18.66", "6.5", "2.50", "2.31"},
    "comparison": {
        "2.47",
        "2.48",
        "2.50",
        "2.62",
        "2.63",
        "2.71",
        "3.30",
        "12.13",
        "12.15",
        "16.21",
    },
    "mortality": {
        "2.20",
        "2.22",
        "2.23",
        "2.27",
        "2.47",
        "2.62",
        "2.63",
        "2.14",
        "6.5",
        "18.66",
    },
}

THEME_CHAPTER_PRIORS = {
    "anxiety": {2, 6, 18},
    "anger": {2, 3, 16},
    "career": {2, 3, 18},
    "discipline": {3, 6, 18},
    "purpose": {2, 3, 18},
    "comparison": {2, 12, 16},
    "mortality": {2, 6, 11, 18},
}

ACTION_OR_DECISION_TERMS = {
    "action",
    "act",
    "choose",
    "choice",
    "decision",
    "duty",
    "responsibility",
    "career",
    "job",
    "work",
    "business",
    "path",
    "direction",
    "kaam",
    "naukri",
    "decision lena",
    "कर्तव्य",
    "निर्णय",
    "रास्ता",
}

EMOTION_REACTIVITY_TERMS = {
    "angry",
    "anger",
    "frustrated",
    "fear",
    "anxious",
    "worry",
    "panic",
    "hurtful",
    "react",
    "impulsive",
    "gussa",
    "chinta",
    "dar",
    "ghabrahat",
    "गुस्सा",
    "चिंता",
    "डर",
}

MORTALITY_OR_WAR_TERMS = {
    "war",
    "death",
    "die",
    "dying",
    "dead",
    "destroy",
    "destruction",
    "kill",
    "killed",
    "mortal",
    "immortal",
    "soul",
    "weapon",
    "battle",
    "conflict",
    "world war",
    "nuclear",
    "apocalypse",
    "safe",
    "safety",
    "survive",
    "मृत्यु",
    "मौत",
    "युद्ध",
    "नाश",
}

UNIVERSAL_CURATED_REFERENCES = [
    "2.20",
    "2.23",
    "2.47",
    "2.48",
    "3.19",
    "3.30",
    "6.5",
    "6.26",
    "6.35",
    "12.13",
    "12.15",
    "18.66",
]

CHAPTER_PERSPECTIVE_EN = {
    1: (
        "Arjuna is overwhelmed by grief and moral confusion on the battlefield."
    ),
    2: (
        "Krishna begins teaching wisdom, steady action, and equanimity."
    ),
    3: (
        "Krishna urges Arjuna toward disciplined selfless action (karma-yoga)."
    ),
    4: "Krishna explains divine wisdom, right action, and sacred duty.",
    5: (
        "Krishna compares renunciation and action, favoring detached action."
    ),
    6: (
        "Krishna teaches meditation, mind-discipline, and inner steadiness."
    ),
    7: "Krishna reveals deeper knowledge of the divine and devotion.",
    8: "Krishna teaches remembrance of the divine in life and death.",
    9: "Krishna reveals the royal path of loving devotion and trust.",
    10: "Krishna describes divine manifestations to strengthen devotion.",
    11: "Arjuna sees the cosmic form and understands divine vastness.",
    12: "Krishna teaches practical devotion through humility and love.",
    13: "Krishna distinguishes body, self, and true spiritual knowledge.",
    14: "Krishna explains the three gunas and how to rise beyond them.",
    15: "Krishna teaches the eternal self and the highest reality.",
    16: "Krishna contrasts divine and destructive tendencies in character.",
    17: "Krishna explains faith, discipline, and intention in action.",
    18: "Krishna synthesizes all teachings and calls for surrender with duty.",
}

CHAPTER_PERSPECTIVE_HI = {
    1: "अर्जुन युद्धभूमि में शोक और नैतिक भ्रम से व्याकुल हैं।",
    2: "कृष्ण समत्व, आत्मबोध और स्थिर कर्म का उपदेश शुरू करते हैं।",
    3: "कृष्ण अर्जुन को निःस्वार्थ कर्तव्य-कर्म (कर्मयोग) के लिए प्रेरित करते हैं।",
    4: "कृष्ण दिव्य ज्ञान, धर्मयुक्त कर्म और कर्तव्य का रहस्य समझाते हैं।",
    5: "कृष्ण संन्यास और कर्म की तुलना कर आसक्ति-रहित कर्म को श्रेष्ठ बताते हैं।",
    6: "कृष्ण ध्यान, मन-नियंत्रण और आंतरिक स्थिरता सिखाते हैं।",
    7: "कृष्ण ईश्वर-तत्व के गहरे ज्ञान और भक्ति का मार्ग बताते हैं।",
    8: "कृष्ण जीवन और मृत्यु के क्षण में ईश्वर-स्मरण का महत्व बताते हैं।",
    9: "कृष्ण प्रेमपूर्ण भक्ति और विश्वास का राजमार्ग प्रकट करते हैं।",
    10: "कृष्ण अपनी विभूतियों का वर्णन कर भक्ति को दृढ़ करते हैं।",
    11: "अर्जुन विराट रूप का दर्शन कर ईश्वर की अनंतता समझते हैं।",
    12: "कृष्ण विनम्रता, प्रेम और समर्पण आधारित भक्ति का व्यावहारिक मार्ग देते हैं।",
    13: "कृष्ण शरीर, आत्मा और सच्चे ज्ञान का भेद समझाते हैं।",
    14: "कृष्ण तीन गुणों और उनसे ऊपर उठने का उपाय बताते हैं।",
    15: "कृष्ण शाश्वत आत्मा और परम सत्य का बोध कराते हैं।",
    16: "कृष्ण दैवी और आसुरी प्रवृत्तियों का अंतर समझाते हैं।",
    17: "कृष्ण श्रद्धा, अनुशासन और संकल्प की शुद्धता का महत्व बताते हैं।",
    18: "कृष्ण समग्र उपदेश का सार देकर कर्तव्य सहित समर्पण का आह्वान करते हैं।",
}

THEME_LABELS_EN = {
    "anxiety": "anxiety and steadiness",
    "career": "work and duty",
    "relationships": "relationships and compassion",
    "anger": "anger and self-mastery",
    "discipline": "discipline and focus",
    "purpose": "purpose and direction",
    "comparison": "comparison and inner worth",
    "mortality": "death, war, and the immortal Self",
}

THEME_LABELS_HI = {
    "anxiety": "चिंता और स्थिरता",
    "career": "काम और कर्तव्य",
    "relationships": "रिश्ते और करुणा",
    "anger": "क्रोध और आत्म-संयम",
    "discipline": "अनुशासन और एकाग्रता",
    "purpose": "उद्देश्य और दिशा",
    "comparison": "तुलना और आत्म-मूल्य",
    "mortality": "मृत्यु, युद्ध, और अविनाशी आत्मा",
}


@dataclass
class GuidanceResult:
    """Normalized guidance payload used by views and UI."""

    guidance: str
    meaning: str
    actions: list[str]
    reflection: str
    response_mode: str


@dataclass
class RetrievalResult:
    """Trace-friendly retrieval output with scores and query signals."""

    verses: list[Verse]
    retrieval_mode: str
    query_themes: list[str]
    query_tokens: list[str]
    retrieval_scores: list[dict]
    query_interpretation: dict[str, object] | None = None


@dataclass
class QueryInterpretation:
    """Structured local interpretation used before retrieval and prompting."""

    emotional_state: str
    life_domain: str
    likely_principles: list[str]
    search_terms: list[str]
    match_strictness: str
    confidence: float

    def as_dict(self) -> dict[str, object]:
        """Expose interpretation in a stable JSON-friendly shape."""
        return {
            "emotional_state": self.emotional_state,
            "life_domain": self.life_domain,
            "likely_principles": self.likely_principles,
            "search_terms": self.search_terms,
            "match_strictness": self.match_strictness,
            "confidence": round(self.confidence, 2),
        }


GREETING_PATTERNS = {
    "hi",
    "hii",
    "hiii",
    "hie",
    "hye",
    "hey",
    "hello",
    "namaste",
    "namaskar",
    "radhe radhe",
    "hare krishna",
    "good morning",
    "good evening",
    "good afternoon",
}


def _is_greeting_like(message: str) -> bool:
    """Detect short greeting-only messages that do not present a real issue yet."""
    normalized = re.sub(r"[^a-zA-Z\s]", " ", message.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return False
    if normalized in GREETING_PATTERNS:
        return True
    tokens = normalized.split()
    return len(tokens) <= 3 and normalized in GREETING_PATTERNS


def is_risky_prompt(message: str) -> bool:
    """Block crisis/medical/legal style prompts with keyword checks."""
    lowered = message.lower()
    return any(keyword in lowered for keyword in RISK_KEYWORDS)


def ensure_seed_verses() -> None:
    """Ensure default verse seed data exists for local/dev environments."""
    global _seed_synced
    # Production already has the full corpus. On process restart, _seed_synced
    # resets, so avoid re-seeding (hundreds of update_or_create calls) just
    # because the worker booted.
    if Verse.objects.exists():
        _seed_synced = True
        return
    if _seed_synced:
        return

    for verse in DEFAULT_VERSES:
        Verse.objects.update_or_create(
            chapter=verse["chapter"],
            verse=verse["verse"],
            defaults={
                "translation": verse["translation"],
                "commentary": verse["commentary"],
                "themes": verse["themes"],
            },
        )
    _seed_synced = True


def detect_themes(message: str) -> set[str]:
    """Public wrapper used by retrieval pipeline for theme detection."""
    return infer_themes_from_text(message)


def interpret_query(message: str) -> QueryInterpretation:
    """Map a plain-language problem into a retrieval-friendly Gita framing."""
    themes = sorted(infer_themes_from_text(message))
    tokens = sorted(_tokenize(message))

    if _is_greeting_like(message):
        emotional_state = "open"
        life_domain = "conversation opening"
        likely_principles = [
            "begin with calm presence",
            "invite the real concern gently",
            "offer a safe reflective space",
        ]
        match_strictness = "none"
    elif "mortality" in themes:
        emotional_state = "fearful"
        life_domain = "existential safety"
        likely_principles = [
            "the Self is not destroyed with the body",
            "act steadily instead of collapsing into panic",
            "grief should be met with higher understanding",
        ]
        match_strictness = "direct"
    elif "anxiety" in themes:
        emotional_state = "anxious"
        life_domain = "inner stability"
        likely_principles = [
            "equanimity amid uncertainty",
            "focus on action rather than results",
            "steady the mind before deciding",
        ]
        match_strictness = "direct"
    elif "anger" in themes:
        emotional_state = "reactive"
        life_domain = "self-mastery"
        likely_principles = [
            "break the chain from desire to anger",
            "respond with steadiness rather than impulse",
            "discipline the senses and mind",
        ]
        match_strictness = "direct"
    elif "relationships" in themes:
        emotional_state = "tender"
        life_domain = "relationships"
        likely_principles = [
            "compassion without attachment",
            "clarity in duty and speech",
            "balance care with self-mastery",
        ]
        match_strictness = "interpretive"
    elif "career" in themes:
        emotional_state = "uncertain"
        life_domain = "work and vocation"
        likely_principles = [
            "act according to dharma",
            "work without anxious attachment to outcomes",
            "clarity grows through sincere action",
        ]
        match_strictness = "interpretive"
    elif "discipline" in themes:
        emotional_state = "scattered"
        life_domain = "habit and discipline"
        likely_principles = [
            "steady practice strengthens the mind",
            "self-mastery comes from repetition and restraint",
            "small disciplined action matters more than intensity",
        ]
        match_strictness = "direct"
    elif "purpose" in themes:
        emotional_state = "confused"
        life_domain = "meaning and direction"
        likely_principles = [
            "clarity comes through right action",
            "dharma is discovered through sincerity and steadiness",
            "confusion lifts when one sees with wisdom",
        ]
        match_strictness = "interpretive"
    elif "comparison" in themes:
        emotional_state = "self-doubting"
        life_domain = "self-worth"
        likely_principles = [
            "do not measure yourself through others",
            "return attention to your own path and duty",
            "inner worth is steadier than praise or blame",
        ]
        match_strictness = "interpretive"
    else:
        emotional_state = "seeking"
        life_domain = "daily life"
        likely_principles = [
            "steady action",
            "clarity before reaction",
            "inner alignment with dharma",
        ]
        match_strictness = "exploratory"

    search_terms = list(dict.fromkeys([*themes, *tokens[:8], *likely_principles[:2]]))
    confidence = min(0.45 + (0.12 * len(themes)), 0.9) if themes else 0.38
    return QueryInterpretation(
        emotional_state=emotional_state,
        life_domain=life_domain,
        likely_principles=likely_principles,
        search_terms=search_terms[:10],
        match_strictness=match_strictness,
        confidence=confidence,
    )


def infer_themes_from_text(text: str) -> set[str]:
    """Infer thematic labels from keyword matches in free text."""
    lowered = text.lower()
    matched = set()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            matched.add(theme)
    return matched


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase content words."""
    raw_tokens = re.findall(r"[a-zA-Z]+", text.lower())
    return {
        token
        for token in raw_tokens
        if token not in STOPWORDS and len(token) > 2
    }


def _score_verse(
    verse: Verse,
    themes: set[str],
    query_tokens: set[str],
) -> int:
    """Compute deterministic hybrid relevance score for a verse."""
    theme_score = sum(theme in verse.themes for theme in themes) * 8
    verse_text = " ".join(
        [verse.translation, " ".join(verse.themes)],
    )
    verse_tokens = _tokenize(verse_text)
    token_score = sum(token in verse_tokens for token in query_tokens) * 2

    lower_verse_text = f"{verse.translation} {' '.join(verse.themes)}".lower()
    keyword_score = 0
    for theme in themes:
        keywords = THEME_KEYWORDS.get(theme, set())
        keyword_score += sum(
            keyword in lower_verse_text
            for keyword in keywords
        )

    prior_score = 0
    verse_ref = _verse_reference(verse)
    for theme in themes:
        if verse_ref in THEME_REFERENCE_PRIORS.get(theme, set()):
            prior_score += 6

    chapter_prior_score = 0
    for theme in themes:
        if verse.chapter in THEME_CHAPTER_PRIORS.get(theme, set()):
            chapter_prior_score += 2

    return int(
        theme_score
        + token_score
        + keyword_score
        + prior_score
        + chapter_prior_score
    )


def _local_query_verse_relevance(*, message: str, verse: Verse) -> int:
    """Compute a lightweight local relevance score for confidence gating."""
    query_tokens = _tokenize(message)
    if not query_tokens:
        return 0

    ref = _verse_reference(verse)
    row = _merged_verse_context(ref)
    angle_text = _additional_angle_text(ref)
    commentary_text = _author_commentary_text(ref, message=message)
    verse_text = (
        f"{verse.translation} {verse.commentary} {' '.join(verse.themes)} "
        f"{row.get('sanskrit', '')} {row.get('hindi', '')} "
        f"{row.get('english', '')} {row.get('word_meaning', '')} "
        f"{angle_text} {commentary_text}"
    )
    verse_tokens = _tokenize(verse_text)
    token_overlap = len(query_tokens.intersection(verse_tokens))

    query_themes = infer_themes_from_text(message)
    theme_overlap = len(set(verse.themes).intersection(query_themes))

    # Weighted toward semantic intent (themes) while still rewarding literal
    # phrase overlap.
    return (theme_overlap * 4) + (token_overlap * 2)


def _retrieval_confidence_high(*, message: str, verses: list[Verse]) -> bool:
    """Decide if retrieved verses are relevant enough to trust directly."""
    if not verses:
        return False

    query_themes = infer_themes_from_text(message)
    if query_themes:
        theme_overlaps = [
            len(set(verse.themes).intersection(query_themes))
            for verse in verses
        ]
        # If nothing matches detected intent themes, treat as weak retrieval.
        if max(theme_overlaps, default=0) == 0:
            return False

    top_score = _local_query_verse_relevance(message=message, verse=verses[0])
    best_score = max(
        _local_query_verse_relevance(message=message, verse=verse)
        for verse in verses
    )

    # When no themes are detected, apply a tighter score requirement so
    # marginal semantic-only matches fall back to curated retrieval.
    if not query_themes:
        return top_score >= 6 and best_score >= 8

    # Use stricter confidence thresholds so weak semantic-only matches fall back
    # to deterministic hybrid/curated retrieval more often.
    return top_score >= 8 or best_score >= 10


def _retrieval_strength(*, message: str, verses: list[Verse]) -> int:
    """Compute deterministic quality score for a retrieval candidate set."""
    if not verses:
        return 0
    return max(
        _local_query_verse_relevance(message=message, verse=verse)
        for verse in verses
    )


def _candidate_pool_limit(limit: int) -> int:
    """Expand retrieval pool so reranker can choose a better final top-k."""
    return max(limit * 4, 12)


def _bridge_rerank_score(*, message: str, verse: Verse) -> int:
    """Score how well a verse bridges battlefield teaching to user context."""
    score = _local_query_verse_relevance(message=message, verse=verse) * 3
    ref = _verse_reference(verse)
    lowered = message.lower()
    themes = infer_themes_from_text(message)

    for theme in themes:
        if ref in THEME_REFERENCE_PRIORS.get(theme, set()):
            score += 8
        if verse.chapter in THEME_CHAPTER_PRIORS.get(theme, set()):
            score += 3

    if any(term in lowered for term in ACTION_OR_DECISION_TERMS):
        if ref in {"2.47", "3.19", "3.30", "18.47", "18.58", "18.66"}:
            score += 10

    if any(term in lowered for term in EMOTION_REACTIVITY_TERMS):
        if ref in {"2.48", "2.63", "3.37", "6.26", "6.35", "16.21"}:
            score += 10

    # Boost Self-immortality and war-origin verses for death/war queries.
    if any(term in lowered for term in MORTALITY_OR_WAR_TERMS):
        if ref in {"2.20", "2.22", "2.23", "2.27", "2.14", "18.66"}:
            score += 12
        if ref in {"2.62", "2.63"}:
            score += 8

    angle_text = _additional_angle_text(ref, limit=2).lower()
    if angle_text and any(token in angle_text for token in lowered.split()):
        score += 4

    # Chapter summaries give broad questions a better chapter-level landing
    # zone without replacing verse-first grounding.
    score += _chapter_summary_match_score(message=message, chapter=verse.chapter)

    return score


def _sparse_lexical_score(*, message: str, verse: Verse) -> int:
    """Compute lexical overlap score to recover exact wording matches."""
    query_tokens = _tokenize(message)
    if not query_tokens:
        return 0

    ref = _verse_reference(verse)
    row = _load_verse_quote_cache().get(ref, {})
    angle_text = _additional_angle_text(ref, limit=2)
    commentary_text = _author_commentary_text(ref, limit=2, message=message)
    verse_text = " ".join(
        [
            verse.translation,
            verse.commentary,
            " ".join(verse.themes),
            row.get("english", ""),
            row.get("hindi", ""),
            row.get("word_meaning", ""),
            angle_text,
            commentary_text,
        ]
    )
    verse_tokens = _tokenize(verse_text)
    exact_overlap = len(query_tokens.intersection(verse_tokens))

    # Reward rare but strong lexical matches without overpowering theme priors.
    return exact_overlap * 3


def _retrieve_sparse_verses_with_trace(
    *,
    message: str,
    limit: int,
) -> RetrievalResult:
    """Retrieve lexical candidates based on exact token overlap."""
    ensure_seed_verses()
    verses = list(Verse.objects.all())
    query_themes = sorted(detect_themes(message))
    query_tokens = sorted(_tokenize(message))

    scored = [
        (_sparse_lexical_score(message=message, verse=verse), verse)
        for verse in verses
    ]
    scored.sort(key=lambda item: (-item[0], item[1].chapter, item[1].verse))
    selected = [(score, verse) for score, verse in scored if score > 0][:limit]

    return RetrievalResult(
        verses=[verse for score, verse in selected],
        retrieval_mode="sparse",
        query_themes=query_themes,
        query_tokens=query_tokens,
        retrieval_scores=[
            {
                "reference": _verse_reference(verse),
                "score": int(score),
            }
            for score, verse in selected
        ],
    )


def _rerank_verses_for_user_context(
    *,
    message: str,
    retrieval: RetrievalResult,
    limit: int,
) -> RetrievalResult:
    """Rerank candidate verses so final top-k better matches user context."""
    if not retrieval.verses:
        return retrieval

    scored = [
        (_bridge_rerank_score(message=message, verse=verse), verse)
        for verse in retrieval.verses
    ]
    scored.sort(key=lambda item: (-item[0], item[1].chapter, item[1].verse))
    selected = scored[:limit]
    return RetrievalResult(
        verses=[verse for _, verse in selected],
        retrieval_mode=retrieval.retrieval_mode,
        query_themes=retrieval.query_themes,
        query_tokens=retrieval.query_tokens,
        retrieval_scores=[
            {
                "reference": _verse_reference(verse),
                "score": int(score),
            }
            for score, verse in selected
        ],
    )


def _merge_candidate_retrievals(
    *,
    retrievals: list[RetrievalResult],
    message: str,
    limit: int,
) -> RetrievalResult:
    """Fuse semantic, hybrid, and sparse candidates into one reranked pool."""
    candidate_by_ref: dict[str, Verse] = {}
    query_themes: list[str] = []
    query_tokens: list[str] = []

    for retrieval in retrievals:
        if not query_themes:
            query_themes = retrieval.query_themes
        if not query_tokens:
            query_tokens = retrieval.query_tokens
        for verse in retrieval.verses:
            candidate_by_ref[_verse_reference(verse)] = verse

    if not candidate_by_ref:
        return RetrievalResult(
            verses=[],
            retrieval_mode="hybrid_fallback",
            query_themes=query_themes,
            query_tokens=query_tokens,
            retrieval_scores=[],
        )

    scored = [
        (_bridge_rerank_score(message=message, verse=verse), verse)
        for verse in candidate_by_ref.values()
    ]
    scored.sort(key=lambda item: (-item[0], item[1].chapter, item[1].verse))
    selected = scored[:limit]
    return RetrievalResult(
        verses=[verse for _, verse in selected],
        retrieval_mode="hybrid",
        query_themes=query_themes,
        query_tokens=query_tokens,
        retrieval_scores=[
            {
                "reference": _verse_reference(verse),
                "score": int(score),
            }
            for score, verse in selected
        ],
    )


def _parse_reference(ref: str) -> tuple[int, int] | None:
    """Parse chapter.verse references into integer tuples."""
    try:
        chapter_str, verse_str = ref.split(".", 1)
        return int(chapter_str), int(verse_str)
    except Exception:
        return None


def _curated_fallback_references_for_message(message: str) -> list[str]:
    """Return deterministic curated reference shortlist for weak retrievals."""
    themes = infer_themes_from_text(message)
    references: list[str] = []

    for theme in sorted(themes):
        references.extend(sorted(THEME_REFERENCE_PRIORS.get(theme, set())))

    if not references:
        references.extend(UNIVERSAL_CURATED_REFERENCES)

    # Preserve order while deduplicating.
    unique = []
    seen = set()
    for ref in references:
        if ref in seen:
            continue
        seen.add(ref)
        unique.append(ref)
    return unique


def _curated_fallback_verses(*, message: str, limit: int) -> list[Verse]:
    """Fetch curated local verses and rank by local relevance."""
    refs = _curated_fallback_references_for_message(message)
    key_pairs = [_parse_reference(ref) for ref in refs]
    key_pairs = [pair for pair in key_pairs if pair]

    if not key_pairs:
        return []

    candidate_by_key = {}
    for chapter, verse in key_pairs:
        row = Verse.objects.filter(chapter=chapter, verse=verse).first()
        if row is not None:
            candidate_by_key[(chapter, verse)] = row

    scored = []
    for ref in refs:
        parsed = _parse_reference(ref)
        if not parsed or parsed not in candidate_by_key:
            continue
        verse = candidate_by_key[parsed]
        score = _local_query_verse_relevance(message=message, verse=verse)
        scored.append((score, verse))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [verse for _, verse in scored[:limit]]


def _fetch_verses_by_references(refs: list[str]) -> list[Verse]:
    """Look up Verse objects from chapter.verse reference strings."""
    ensure_seed_verses()
    verses: list[Verse] = []
    seen: set[str] = set()
    for ref in refs:
        ref = ref.strip()
        if ref in seen:
            continue
        parsed = _parse_reference(ref)
        if not parsed:
            continue
        chapter, verse_num = parsed
        obj = Verse.objects.filter(chapter=chapter, verse=verse_num).first()
        if obj is not None:
            seen.add(ref)
            verses.append(obj)
    return verses


def _verse_reference(verse: Verse) -> str:
    """Format verse primary key as chapter.verse string."""
    return f"{verse.chapter}.{verse.verse}"


def _safe_get_verse_synthesis_record(verse: Verse) -> VerseSynthesis | None:
    """Return cached synthesis record when the table exists; otherwise degrade safely."""
    try:
        return VerseSynthesis.objects.filter(verse=verse).first()
    except (OperationalError, ProgrammingError):
        return None


def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """Return cosine similarity between two equal-length vectors."""
    if not vector_a or not vector_b or len(vector_a) != len(vector_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_query_embedding(message: str) -> list[float] | None:
    """Build embedding for user query; return None on any failure."""
    if not settings.OPENAI_API_KEY:
        return None
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=message,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("Query embedding generation failed: %s", exc)
        return None


def _pgvector_enabled() -> bool:
    """Return True when pgvector retrieval is configured and backend is Postgres."""
    return (
        bool(getattr(settings, "ENABLE_PGVECTOR_RETRIEVAL", False))
        and connection.vendor == "postgresql"
    )


def _pgvector_table_name() -> str:
    """Return configured pgvector index table name."""
    return str(getattr(settings, "PGVECTOR_TABLE", "")).strip()


def _pgvector_index_exists() -> bool:
    """Check if configured pgvector index table exists."""
    table_name = _pgvector_table_name()
    if not table_name:
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [table_name])
        row = cursor.fetchone()
    return bool(row and row[0])


def _to_pgvector_literal(vector: list[float]) -> str:
    """Convert Python embedding list into pgvector literal string."""
    return "[" + ",".join(f"{float(value):.8f}" for value in vector) + "]"


def _semantic_retrieve_verses_pgvector(
    *,
    query_embedding: list[float],
    limit: int,
) -> tuple[list[Verse], list[dict]]:
    """Retrieve nearest verses using pgvector cosine distance."""
    table_name = _pgvector_table_name()
    if not table_name:
        return [], []

    probes = int(getattr(settings, "PGVECTOR_PROBES", 10))
    vector_literal = _to_pgvector_literal(query_embedding)
    query = (
        "SELECT i.verse_id, (i.embedding <=> %s::vector) AS distance "
        f"FROM {table_name} i "
        "ORDER BY i.embedding <=> %s::vector ASC "
        "LIMIT %s"
    )

    with connection.cursor() as cursor:
        cursor.execute("SET ivfflat.probes = %s", [probes])
        cursor.execute(query, [vector_literal, vector_literal, limit])
        rows = cursor.fetchall()

    if not rows:
        return [], []

    verse_ids = [int(row[0]) for row in rows]
    distances_by_id = {int(row[0]): float(row[1]) for row in rows}
    verses_by_id = Verse.objects.in_bulk(verse_ids)
    verses = [
        verses_by_id[verse_id]
        for verse_id in verse_ids
        if verse_id in verses_by_id
    ]
    scores = [
        {
            "reference": _verse_reference(verse),
            # cosine similarity approximation from pgvector distance
            "score": round(1.0 - distances_by_id.get(verse.id, 1.0), 4),
        }
        for verse in verses
    ]
    return verses, scores


def _semantic_retrieve_verses(
    verses: list[Verse],
    query_embedding: list[float],
    limit: int,
) -> list[Verse]:
    """Rank verses by embedding similarity and return top scored set."""
    scored = []
    for verse in verses:
        embedding = (
            verse.embedding if isinstance(verse.embedding, list) else []
        )
        if not embedding:
            continue
        score = _cosine_similarity(query_embedding, embedding)
        scored.append((score, verse))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [(score, verse) for score, verse in scored if score > 0][:limit]
    verses = [verse for score, verse in selected]
    scores = [
        {
            "reference": _verse_reference(verse),
            "score": round(float(score), 4),
        }
        for score, verse in selected
    ]
    return verses, scores


def _hybrid_retrieve_with_trace(
    *,
    verses: list[Verse],
    themes: set[str],
    query_tokens: set[str],
    query_themes: list[str],
    sorted_tokens: list[str],
    limit: int,
) -> RetrievalResult:
    """Run hybrid retrieval and include rich score trace."""
    # Hybrid scoring: theme overlap + token overlap for better relevance.
    scored = [
        (_score_verse(verse, themes, query_tokens), verse)
        for verse in verses
    ]
    scored.sort(
        key=lambda item: (-item[0], item[1].chapter, item[1].verse),
    )
    selected_pairs = [
        (score, verse)
        for score, verse in scored
        if score > 0
    ][:limit]
    selected = [verse for score, verse in selected_pairs]
    score_rows = [
        {"reference": _verse_reference(verse), "score": int(score)}
        for score, verse in selected_pairs
    ]

    if selected:
        return RetrievalResult(
            verses=selected,
            retrieval_mode="hybrid",
            query_themes=query_themes,
            query_tokens=sorted_tokens,
            retrieval_scores=score_rows,
        )

    fallback = verses[:limit]
    fallback_scores = [
        {"reference": _verse_reference(verse), "score": 0}
        for verse in fallback
    ]
    return RetrievalResult(
        verses=fallback,
        retrieval_mode="hybrid_fallback",
        query_themes=query_themes,
        query_tokens=sorted_tokens,
        retrieval_scores=fallback_scores,
    )


def retrieve_semantic_verses_with_trace(
    message: str,
    limit: int = 3,
) -> RetrievalResult:
    """Run semantic-only retrieval and expose non-success reasons."""
    ensure_seed_verses()
    themes = detect_themes(message)
    query_tokens = _tokenize(message)
    verses = list(Verse.objects.all())
    query_themes = sorted(themes)
    sorted_tokens = sorted(query_tokens)

    if not settings.ENABLE_SEMANTIC_RETRIEVAL:
        return RetrievalResult(
            verses=[],
            retrieval_mode="semantic_disabled",
            query_themes=query_themes,
            query_tokens=sorted_tokens,
            retrieval_scores=[],
        )

    query_embedding = _build_query_embedding(message)
    if not query_embedding:
        return RetrievalResult(
            verses=[],
            retrieval_mode="semantic_unavailable",
            query_themes=query_themes,
            query_tokens=sorted_tokens,
            retrieval_scores=[],
        )

    if _pgvector_enabled() and _pgvector_index_exists():
        semantic_verses, semantic_scores = _semantic_retrieve_verses_pgvector(
            query_embedding=query_embedding,
            limit=limit,
        )
        if semantic_verses:
            return RetrievalResult(
                verses=semantic_verses,
                retrieval_mode="semantic",
                query_themes=query_themes,
                query_tokens=sorted_tokens,
                retrieval_scores=semantic_scores,
            )

    semantic_verses, semantic_scores = _semantic_retrieve_verses(
        verses=verses,
        query_embedding=query_embedding,
        limit=limit,
    )
    if semantic_verses:
        return RetrievalResult(
            verses=semantic_verses,
            retrieval_mode="semantic",
            query_themes=query_themes,
            query_tokens=sorted_tokens,
            retrieval_scores=semantic_scores,
        )
    return RetrievalResult(
        verses=[],
        retrieval_mode="semantic_empty",
        query_themes=query_themes,
        query_tokens=sorted_tokens,
        retrieval_scores=[],
    )


def retrieve_hybrid_verses_with_trace(
    message: str,
    limit: int = 3,
) -> RetrievalResult:
    """Run hybrid-only retrieval regardless of semantic availability."""
    ensure_seed_verses()
    themes = detect_themes(message)
    query_tokens = _tokenize(message)
    verses = list(Verse.objects.all())
    return _hybrid_retrieve_with_trace(
        verses=verses,
        themes=themes,
        query_tokens=query_tokens,
        query_themes=sorted(themes),
        sorted_tokens=sorted(query_tokens),
        limit=limit,
    )


def _dual_corpus_rerank(
    *,
    message: str,
    retrieval: RetrievalResult,
    limit: int,
) -> RetrievalResult:
    """Merge Verse + angle candidates and rerank with local scoring only."""
    # Pull extra references from the angle corpus in parallel to canonical
    # verse retrieval. Final payload still returns Verse rows only.
    angle_candidates = _retrieve_angle_reference_candidates(
        message=message,
        limit=max(limit * 3, 6),
    )
    if not angle_candidates:
        return retrieval
    # Only apply dual-corpus merge when angle corpus has meaningful signal.
    if max(score for _, score in angle_candidates) < 6:
        return retrieval

    candidate_by_ref = {
        _verse_reference(verse): verse
        for verse in retrieval.verses
    }
    for reference, _score in angle_candidates:
        parsed = _parse_reference(reference)
        if not parsed:
            continue
        chapter, verse_num = parsed
        verse = Verse.objects.filter(chapter=chapter, verse=verse_num).first()
        if verse is not None:
            candidate_by_ref[reference] = verse

    if not candidate_by_ref:
        return retrieval

    scored: list[tuple[int, Verse]] = []
    for reference, verse in candidate_by_ref.items():
        base_score = _local_query_verse_relevance(message=message, verse=verse)
        angle_score = _angle_match_score(message=message, reference=reference)
        scored.append((base_score + angle_score, verse))

    scored.sort(
        key=lambda item: (-item[0], item[1].chapter, item[1].verse),
    )
    selected = scored[:limit]
    return RetrievalResult(
        verses=[verse for _, verse in selected],
        retrieval_mode=retrieval.retrieval_mode,
        query_themes=retrieval.query_themes,
        query_tokens=retrieval.query_tokens,
        retrieval_scores=[
            {
                "reference": _verse_reference(verse),
                "score": int(score),
            }
            for score, verse in selected
        ],
    )


def retrieve_verses_with_trace(message: str, limit: int = 3) -> RetrievalResult:
    """Preferred retrieval strategy: semantic first, hybrid fallback."""
    interpretation = interpret_query(message)
    if _is_greeting_like(message):
        return RetrievalResult(
            verses=[],
            retrieval_mode="greeting",
            query_themes=[],
            query_tokens=sorted(list(_tokenize(message))),
            retrieval_scores=[],
            query_interpretation=interpretation.as_dict(),
        )
    candidate_limit = _candidate_pool_limit(limit)
    semantic = retrieve_semantic_verses_with_trace(
        message=message,
        limit=candidate_limit,
    )
    if semantic.retrieval_mode != "semantic":
        retrieval = retrieve_hybrid_verses_with_trace(
            message=message,
            limit=candidate_limit,
        )
    else:
        # Cost-safe blending: compare semantic and hybrid retrieval locally and
        # keep whichever has stronger deterministic relevance for this query.
        hybrid = retrieve_hybrid_verses_with_trace(
            message=message,
            limit=candidate_limit,
        )
        semantic_strength = _retrieval_strength(
            message=message,
            verses=semantic.verses,
        )
        hybrid_strength = _retrieval_strength(
            message=message,
            verses=hybrid.verses,
        )
        retrieval = hybrid if hybrid_strength > semantic_strength else semantic

    sparse = _retrieve_sparse_verses_with_trace(
        message=message,
        limit=candidate_limit,
    )
    retrieval = _merge_candidate_retrievals(
        retrievals=[retrieval, sparse],
        message=message,
        limit=limit,
    )

    # Cost-safe relevance gate:
    # If initial retrieval is weak for the exact query, switch to a local
    # curated fallback verse shortlist (no extra LLM calls, no web calls).
    if _retrieval_confidence_high(message=message, verses=retrieval.verses):
        retrieval.query_interpretation = interpretation.as_dict()
        return retrieval

    fallback_verses = _curated_fallback_verses(message=message, limit=limit)
    if not fallback_verses:
        retrieval.query_interpretation = interpretation.as_dict()
        return retrieval

    return RetrievalResult(
        verses=fallback_verses,
        retrieval_mode="curated_fallback",
        query_themes=sorted(list(infer_themes_from_text(message))),
        query_tokens=sorted(list(_tokenize(message))),
        retrieval_scores=[
            {
                "reference": _verse_reference(verse),
                "score": _local_query_verse_relevance(
                    message=message,
                    verse=verse,
                ),
            }
            for verse in fallback_verses
        ],
        query_interpretation=interpretation.as_dict(),
    )


def retrieve_verses(message: str, limit: int = 3) -> list[Verse]:
    """Compatibility helper returning verse list without trace fields."""
    return retrieve_verses_with_trace(message=message, limit=limit).verses


def _normalize_language(language: str) -> str:
    """Normalize caller-provided language value to supported codes."""
    normalized = str(language or "").strip().lower()
    if normalized in SUPPORTED_LANGUAGE_CODES:
        return normalized
    return "en"


def _chapter_perspective(*, chapter: int, language: str) -> str:
    """Return concise chapter context for Krishna-to-Arjuna framing."""
    language = _normalize_language(language)
    if language == "hi":
        return CHAPTER_PERSPECTIVE_HI.get(chapter, CHAPTER_PERSPECTIVE_HI[2])
    return CHAPTER_PERSPECTIVE_EN.get(chapter, CHAPTER_PERSPECTIVE_EN[2])


def _load_verse_quote_cache() -> dict[str, dict[str, str]]:
    """Load multilingual verse metadata from local CSV cache."""
    global _verse_quote_cache
    if _verse_quote_cache is not None:
        return _verse_quote_cache

    _verse_quote_cache = {}
    csv_path = (
        Path(__file__).resolve().parents[1] / "data" / "Bhagwad_Gita.csv"
    )
    if not csv_path.exists():
        return _verse_quote_cache

    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                chapter = str(row.get("Chapter", "")).strip()
                verse = str(row.get("Verse", "")).strip()
                if not chapter or not verse:
                    continue
                ref = f"{chapter}.{verse}"
                _verse_quote_cache[ref] = {
                    "sanskrit": str(row.get("Shloka", "")).strip(),
                    "transliteration": str(
                        row.get("Transliteration", "")
                    ).strip(),
                    "hindi": str(row.get("HinMeaning", "")).strip(),
                    "english": str(row.get("EngMeaning", "")).strip(),
                    "word_meaning": str(row.get("WordMeaning", "")).strip(),
                }
    except Exception as exc:
        logger.warning("Verse quote cache load failed: %s", exc)
    return _verse_quote_cache


def _load_additional_angle_cache() -> dict[str, list[dict[str, str]]]:
    """Load additive verse-angle rows merged from external datasets."""
    global _verse_additional_angle_cache
    if _verse_additional_angle_cache is not None:
        return _verse_additional_angle_cache

    _verse_additional_angle_cache = {}
    json_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "gita_additional_angles.json"
    )
    if not json_path.exists():
        return _verse_additional_angle_cache

    try:
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        for row in rows:
            ref = str(row.get("reference", "")).strip()
            if not ref:
                continue
            _verse_additional_angle_cache.setdefault(ref, []).append(
                {
                    "english": str(row.get("english", "")).strip(),
                    "hindi": str(row.get("hindi", "")).strip(),
                    "sanskrit": str(row.get("sanskrit", "")).strip(),
                    "word_meaning": str(row.get("word_meaning", "")).strip(),
                    "source": str(row.get("source", "")).strip(),
                }
            )
    except Exception as exc:
        logger.warning("Additional angle cache load failed: %s", exc)
    return _verse_additional_angle_cache


def _vedic_slok_path_for_reference(reference: str) -> Path:
    """Return the JSON file path that contains multi-author commentary for a verse."""
    slok_dir = Path(__file__).resolve().parents[1] / "data" / "slok"
    chapter, verse = (0, 0)
    try:
        chapter_str, verse_str = str(reference).split(".", 1)
        chapter = int(chapter_str)
        verse = int(verse_str)
    except Exception:
        return slok_dir / "__invalid__.json"
    return slok_dir / f"bhagavadgita_chapter_{chapter}_slok_{verse}.json"


def _load_vedic_slok_row(reference: str) -> dict[str, object]:
    """Load one verse's Vedic slok JSON (lazy, cached) to avoid large cold-start stalls."""
    reference = str(reference or "").strip()
    if not reference:
        return {}
    if reference in _vedic_slok_cache:
        return _vedic_slok_cache[reference]

    path = _vedic_slok_path_for_reference(reference)
    if not path.exists():
        _vedic_slok_cache[reference] = {}
        return {}

    commentary_fields = ("et", "ec", "ht", "hc", "sc")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        commentaries: list[dict[str, str]] = []
        for value in raw.values():
            if not isinstance(value, dict):
                continue
            author = str(value.get("author", "")).strip()
            parts = [str(value.get(field, "")).strip() for field in commentary_fields]
            parts = [part for part in parts if part]
            if not author or not parts:
                continue
            commentaries.append({"author": author, "text": " ".join(parts)})

        row = {
            "speaker": str(raw.get("speaker", "")).strip(),
            "slok": str(raw.get("slok", "")).strip(),
            "transliteration": str(raw.get("transliteration", "")).strip(),
            "commentaries": commentaries,
        }
        _vedic_slok_cache[reference] = row
        return row
    except Exception as exc:
        logger.warning("Vedic slok row load failed (%s): %s", reference, exc)
        _vedic_slok_cache[reference] = {}
        return {}


def _merged_verse_context(reference: str) -> dict[str, object]:
    """Return one merged context payload for a verse reference."""
    reference = str(reference or "").strip()
    if not reference:
        return {}
    cached = _merged_verse_context_cache.get(reference)
    if cached is not None:
        return cached

    quote_cache = _load_verse_quote_cache()
    additional_cache = _load_additional_angle_cache()
    quote_row = quote_cache.get(reference, {})
    angle_rows = additional_cache.get(reference, [])
    vedic_row = _load_vedic_slok_row(reference)

    merged: dict[str, object] = {
        "sanskrit": str(
            quote_row.get("sanskrit", "") or vedic_row.get("slok", "")
        ).strip(),
        "transliteration": str(
            quote_row.get("transliteration", "")
            or vedic_row.get("transliteration", "")
        ).strip(),
        "hindi": str(quote_row.get("hindi", "")).strip(),
        "english": str(quote_row.get("english", "")).strip(),
        "word_meaning": str(quote_row.get("word_meaning", "")).strip(),
        "angles": angle_rows,
        "commentaries": list(vedic_row.get("commentaries", [])),
    }

    # Fill blanks from additional-angle source when canonical CSV does not
    # have that specific field populated for the same reference.
    for angle in angle_rows:
        if not merged["sanskrit"]:
            merged["sanskrit"] = str(angle.get("sanskrit", "")).strip()
        if not merged["transliteration"]:
            merged["transliteration"] = str(angle.get("transliteration", "")).strip()
        if not merged["hindi"]:
            merged["hindi"] = str(angle.get("hindi", "")).strip()
        if not merged["english"]:
            merged["english"] = str(angle.get("english", "")).strip()
        if not merged["word_meaning"]:
            merged["word_meaning"] = str(angle.get("word_meaning", "")).strip()

    _merged_verse_context_cache[reference] = merged
    return merged


def _load_chapter_summary_cache() -> dict[int, dict[str, object]]:
    """Derive chapter summaries from in-repo data when no JSON file exists."""
    global _chapter_summary_cache
    if _chapter_summary_cache is not None:
        return _chapter_summary_cache

    chapter_dir = Path(__file__).resolve().parents[1] / "data" / "chapter"
    if chapter_dir.exists():
        file_summaries: dict[int, dict[str, object]] = {}
        try:
            for path in sorted(chapter_dir.glob("*.json")):
                row = json.loads(path.read_text(encoding="utf-8"))
                chapter = row.get("chapter_number")
                if not chapter:
                    continue
                meaning = row.get("meaning", {}) if isinstance(row.get("meaning"), dict) else {}
                summary = row.get("summary", {}) if isinstance(row.get("summary"), dict) else {}
                file_summaries[int(chapter)] = {
                    "en": str(summary.get("en", "") or meaning.get("en", "")).strip(),
                    "hi": str(summary.get("hi", "") or meaning.get("hi", "")).strip(),
                }
        except Exception as exc:
            logger.warning("Chapter summary cache load failed: %s", exc)
        if file_summaries:
            ensure_seed_verses()
            verses = list(Verse.objects.all().only("chapter", "verse", "themes"))
            chapter_theme_counts: dict[int, dict[str, int]] = {}
            for verse in verses:
                counts = chapter_theme_counts.setdefault(verse.chapter, {})
                for theme in verse.themes:
                    counts[theme] = counts.get(theme, 0) + 1
            for chapter, payload in file_summaries.items():
                counts = chapter_theme_counts.get(chapter, {})
                payload["themes"] = [
                    theme
                    for theme, _ in sorted(
                        counts.items(),
                        key=lambda item: (-item[1], item[0]),
                    )[:4]
                ]
            _chapter_summary_cache = file_summaries
            return _chapter_summary_cache

    ensure_seed_verses()
    verses = list(Verse.objects.all().only("chapter", "verse", "themes"))
    chapter_theme_counts: dict[int, dict[str, int]] = {}

    for verse in verses:
        counts = chapter_theme_counts.setdefault(verse.chapter, {})
        for theme in verse.themes:
            counts[theme] = counts.get(theme, 0) + 1

    chapter_summaries: dict[int, dict[str, object]] = {}
    for chapter in range(1, 19):
        counts = chapter_theme_counts.get(chapter, {})
        ranked_themes = [
            theme
            for theme, _ in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:4]
        ]
        theme_line_en = ", ".join(
            THEME_LABELS_EN.get(theme, theme.replace("_", " "))
            for theme in ranked_themes
        )
        theme_line_hi = ", ".join(
            THEME_LABELS_HI.get(theme, theme)
            for theme in ranked_themes
        )
        base_en = CHAPTER_PERSPECTIVE_EN.get(chapter, CHAPTER_PERSPECTIVE_EN[2])
        base_hi = CHAPTER_PERSPECTIVE_HI.get(chapter, CHAPTER_PERSPECTIVE_HI[2])
        summary_en = base_en
        summary_hi = base_hi
        if theme_line_en:
            summary_en = f"{base_en} Key life themes: {theme_line_en}."
        if theme_line_hi:
            summary_hi = f"{base_hi} प्रमुख जीवन-विषय: {theme_line_hi}।"
        chapter_summaries[chapter] = {
            "en": summary_en,
            "hi": summary_hi,
            "themes": ranked_themes,
        }

    _chapter_summary_cache = chapter_summaries
    return _chapter_summary_cache


def _chapter_summary_match_score(*, message: str, chapter: int) -> int:
    """Boost chapters whose derived summary better matches the query intent."""
    summary = _load_chapter_summary_cache().get(chapter)
    if not summary:
        return 0

    query_tokens = _tokenize(message)
    query_themes = infer_themes_from_text(message)
    summary_text = " ".join(
        [
            str(summary.get("en", "")),
            str(summary.get("hi", "")),
            " ".join(summary.get("themes", [])),
        ]
    )
    summary_tokens = _tokenize(summary_text)
    summary_themes = set(summary.get("themes", []))
    token_overlap = len(query_tokens.intersection(summary_tokens))
    theme_overlap = len(query_themes.intersection(summary_themes))
    prior_overlap = sum(
        chapter in THEME_CHAPTER_PRIORS.get(theme, set())
        for theme in query_themes
    )
    return (theme_overlap * 5) + (token_overlap * 2) + (prior_overlap * 3)


def _author_commentary_entries(reference: str) -> list[dict[str, str]]:
    """Return normalized multi-author commentary rows for one reference."""
    rows = _merged_verse_context(reference).get("commentaries", [])
    return list(rows) if isinstance(rows, list) else []


def _detect_text_language(text: str) -> str:
    """Roughly detect whether text is Hindi/Devanagari or English-dominant."""
    normalized = str(text).strip()
    if not normalized:
        return "en"
    hindi_chars = sum(1 for c in normalized if "\u0900" <= c <= "\u097F")
    return "hi" if hindi_chars > len(normalized) * 0.2 else "en"


def _clean_commentary_text(text: str, *, max_chars: int = 280) -> str:
    """Trim raw commentary down to readable prose for synthesis and prompt use."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = re.sub(r"।।\s*\d+\.\d+\s*।।", "", cleaned)
    cleaned = re.sub(r"\b\d{1,2}\.\d{1,3}\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -|:;,.")
    if not cleaned:
        return ""

    fragments = re.split(r"(?<=[.!?।])\s+", cleaned)
    selected: list[str] = []
    for fragment in fragments:
        fragment = fragment.strip(" -|:;,.")
        if not fragment:
            continue
        digit_ratio = sum(ch.isdigit() for ch in fragment) / max(len(fragment), 1)
        if digit_ratio > 0.18:
            continue
        if len(fragment) < 24:
            continue
        selected.append(fragment)
        if sum(len(item) for item in selected) >= max_chars:
            break

    if selected:
        cleaned = " ".join(selected)

    if len(cleaned) > max_chars:
        clipped = cleaned[:max_chars].rsplit(" ", 1)[0].strip()
        cleaned = f"{clipped}..."
    return cleaned.strip()


def _preferred_commentary_entries(
    reference: str,
    *,
    language: str = "en",
    limit: int = 3,
    message: str = "",
) -> list[dict[str, str]]:
    """Return the cleanest, most relevant commentary entries for one language."""
    normalized_language = _normalize_language(language)
    rows = []
    for entry in _author_commentary_entries(reference):
        cleaned_text = _clean_commentary_text(entry.get("text", ""))
        if not cleaned_text:
            continue
        rows.append(
            {
                "author": str(entry.get("author", "")).strip(),
                "text": cleaned_text,
                "language": _detect_text_language(cleaned_text),
            }
        )

    rows = sorted(
        rows,
        key=lambda entry: (
            0 if entry.get("language") == normalized_language else 1,
            -_author_commentary_match_score(message=message, entry=entry),
            str(entry.get("author", "")).lower(),
        ),
    )
    return rows[:limit]


def _author_commentary_match_score(*, message: str, entry: dict[str, str]) -> int:
    """Score one author perspective against the user's query."""
    text = str(entry.get("text", "")).strip()
    if not text:
        return 0

    query_tokens = _tokenize(message)
    query_themes = infer_themes_from_text(message)
    commentary_tokens = _tokenize(text)
    commentary_themes = infer_themes_from_text(text)
    token_overlap = len(query_tokens.intersection(commentary_tokens))
    theme_overlap = len(query_themes.intersection(commentary_themes))
    return (theme_overlap * 4) + (token_overlap * 2)


def _author_commentary_text(
    reference: str,
    limit: int = 3,
    *,
    message: str = "",
) -> str:
    """Serialize the most query-relevant author commentary snippets."""
    rows = _preferred_commentary_entries(
        reference,
        language="en",
        limit=limit,
        message=message,
    )
    snippets = []
    for row in rows:
        author = str(row.get("author", "")).strip()
        text = str(row.get("text", "")).strip()
        if author and text:
            snippets.append(f"{author}: {text}")
    return " || ".join(snippets)


def _additional_angle_text(reference: str, limit: int = 2) -> str:
    """Serialize compact angle snippets for retrieval and prompt context."""
    rows = list(_merged_verse_context(reference).get("angles", []))[:limit]
    snippets = []
    for row in rows:
        english = row.get("english", "")
        hindi = row.get("hindi", "")
        word_meaning = row.get("word_meaning", "")
        parts = [part for part in [english, hindi, word_meaning] if part]
        if parts:
            snippets.append(" | ".join(parts))
    return " || ".join(snippets)


def _angle_match_score(*, message: str, reference: str) -> int:
    """Return deterministic relevance score from additive-angle corpus text."""
    angle_text = _additional_angle_text(reference, limit=3)
    if not angle_text:
        return 0

    query_tokens = _tokenize(message)
    if not query_tokens:
        return 0

    angle_tokens = _tokenize(angle_text)
    token_overlap = len(query_tokens.intersection(angle_tokens))
    query_themes = infer_themes_from_text(message)
    angle_themes = infer_themes_from_text(angle_text)
    theme_overlap = len(query_themes.intersection(angle_themes))
    return (theme_overlap * 3) + (token_overlap * 2)


def _retrieve_angle_reference_candidates(
    *,
    message: str,
    limit: int,
) -> list[tuple[str, int]]:
    """Find top references from additional-angle corpus for this query."""
    cache = _load_additional_angle_cache()
    if not cache:
        return []

    scored: list[tuple[int, str]] = []
    for reference in cache.keys():
        score = _angle_match_score(message=message, reference=reference)
        if score > 0:
            scored.append((score, reference))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:limit]
    return [(reference, score) for score, reference in top]


def _strip_leading_ref(text: str, ref: str) -> str:
    """Trim leading reference markers like '2.47' from quote text."""
    cleaned = text.strip()
    pattern = rf"^{re.escape(ref)}\s*[-.:)]?\s*"
    return re.sub(pattern, "", cleaned).strip()


def _primary_verse_quote(*, verse: Verse | None, language: str) -> tuple[str, str]:
    """Return (reference, exact quote) for primary verse in target language."""
    if verse is None:
        return "", ""

    ref = _verse_reference(verse)
    language = _normalize_language(language)
    row = _merged_verse_context(ref)
    if language == "hi":
        quote = row.get("sanskrit", "").strip()
        if quote:
            return ref, quote
        return ref, ""

    # English path prefers exact CSV meaning, then DB translation fallback.
    quote = _strip_leading_ref(row.get("english", "").strip(), ref)
    if quote:
        return ref, quote
    return ref, verse.translation.strip()


def _guidance_with_primary_quote(
    *,
    guidance: str,
    primary_verse: Verse | None,
    language: str,
) -> str:
    """Prepend primary verse quote in language-aware format."""
    ref, quote = _primary_verse_quote(verse=primary_verse, language=language)
    if not ref or not quote:
        return guidance

    if language == "hi":
        prefix = f"गीता {ref} में कृष्ण कहते हैं: \"{quote}\""
    else:
        prefix = f"In Bhagavad Gita {ref}, Krishna says: \"{quote}\""
    return f"{prefix}\n\n{guidance}"

def _is_context_relevant_response(
    *,
    message: str,
    guidance: str,
    meaning: str,
) -> bool:
    """Ensure reply is tied to the user's concrete question, not generic."""
    message_tokens = _tokenize(message)
    if not message_tokens:
        return True

    response_tokens = _tokenize(f"{guidance} {meaning}")
    overlap = message_tokens.intersection(response_tokens)

    # Require at least one direct concept overlap for very short prompts,
    # and stronger overlap for richer prompts to avoid vague answers.
    if len(message_tokens) <= 3:
        return len(overlap) >= 1
    if len(message_tokens) <= 8:
        return len(overlap) >= 2
    return len(overlap) >= 3


def _build_mortality_fallback(
    *,
    message: str,
    verses: list[Verse],
    refs: str,
    primary_ref: str,
    primary_verse: Verse | None,
    language: str,
) -> GuidanceResult:
    """Mortality/war-specific fallback when LLM is unavailable."""
    if language == "hi":
        guidance = (
            "प्रिय साधक, तुम्हारे मन में युद्ध, विनाश और मृत्यु का भय है। "
            "गीता इसी भय के बीच कही गई थी — कुरुक्षेत्र के रणक्षेत्र में, जहाँ "
            "अर्जुन भी ठीक ऐसे ही भयभीत और हतप्रभ था। कृष्ण ने सबसे पहले "
            "उसे बताया कि आत्मा अजर, अमर और अविनाशी है (2.20) — शस्त्र इसे "
            "काट नहीं सकते, अग्नि जला नहीं सकती (2.23)। शरीर नश्वर है, पर "
            "तुम्हारा सबसे गहरा अस्तित्व किसी युद्ध से नष्ट नहीं हो सकता। "
            "कृष्ण कहते हैं: मा शुचः — शोक मत करो (18.66)। भय को अपने "
            f"विवेक पर हावी न होने दो। इन श्लोकों से दिशा लो: {refs}।"
        )
        meaning = (
            "गीता के अनुसार विनाश की जड़ बाहरी शस्त्रों में नहीं, बल्कि "
            "आसक्ति, काम, क्रोध और मोह की आंतरिक शृंखला में है (2.62-63)। "
            "तुम्हारे प्रसंग में इसका अर्थ है: भय स्वाभाविक है, पर भय ही सत्य "
            "नहीं है। तुम्हारी आत्मा अविनाशी है और तुम्हारा कर्तव्य आज स्थिर रहना है।"
        )
        actions = [
            "शांत बैठो, धीमी सांस लो, और स्वयं से कहो: 'यह भय गुज़रेगा, मैं स्पष्टता से कर्म करूंगा।'",
            "गीता 2.20 और 2.23 पढ़ो — आत्मा की अमरता पर चिंतन करो।",
            "केवल विश्वसनीय समाचार स्रोत देखो; भय बढ़ाने वाली सूचनाओं से दूर रहो।",
        ]
        reflection = "क्या मैं कल्पित विनाश में जी रहा हूँ, या इस क्षण में स्थिरता और विवेक के साथ?"
    else:
        guidance = (
            "Dear seeker, your heart is gripped by fear of war, destruction, "
            "and death. The Gita was spoken on exactly such a battlefield — "
            "Kurukshetra — where Arjuna too was paralyzed by the same dread. "
            "Krishna's very first teaching was this: the Self (atman) is never "
            "born and never dies (2.20). Weapons cannot cut it, fire cannot "
            "burn it (2.23). The body is mortal — death is certain for every "
            "being born (2.27) — but your deepest reality is beyond "
            "destruction. Krishna says: 'Ma shuchah' — do not despair "
            "(18.66). Do not let fear crush your wisdom. "
            f"Let these verses guide you: {refs}."
        )
        meaning = (
            "According to the Gita, destruction begins not with weapons but "
            "inside the mind — through the chain of attachment, desire, anger, "
            "and delusion (2.62-63). In your context, this means: fear is "
            "natural, but fear is not always truth. Your Self is indestructible, "
            "and your duty right now is to stay steady, protect yourself wisely, "
            "and act with clarity rather than panic."
        )
        actions = [
            "Sit down, breathe slowly, and tell yourself: 'This fear is passing. I will act with clarity.'",
            "Read Gita 2.20 and 2.23 — reflect on the immortality of the Self.",
            "Limit news to trustworthy sources only; do not doom-scroll — that feeds the fear cycle described in 2.62-63.",
        ]
        reflection = (
            "Am I living in imagined destruction, or can I meet this moment "
            "with steadiness, faith, and wisdom?"
        )
    guidance = _guidance_with_primary_quote(
        guidance=guidance,
        primary_verse=primary_verse,
        language=language,
    )
    return GuidanceResult(
        guidance=guidance,
        meaning=meaning,
        actions=actions,
        reflection=reflection,
        response_mode="fallback",
    )


def _build_fallback_guidance(
    message: str,
    verses: list[Verse],
    *,
    language: str = "en",
) -> GuidanceResult:
    """Create deterministic, safe guidance when LLM is unavailable."""
    language = _normalize_language(language)
    if _is_greeting_like(message):
        if language == "hi":
            return GuidanceResult(
                guidance=(
                    "नमस्ते। मैं यहाँ भगवद्गीता के आधार पर शांत, स्पष्ट और व्यावहारिक "
                    "मार्गदर्शन देने के लिए हूँ।"
                ),
                meaning=(
                    "आप अपनी स्थिति सरल शब्दों में लिखिए, और मैं सबसे प्रासंगिक "
                    "शिक्षा, श्लोक और अगला कदम खोजने की कोशिश करूंगा।"
                ),
                actions=[
                    "एक वाक्य में लिखिए: अभी आपको सबसे ज़्यादा किस बात की चिंता है?",
                    "यदि चाहें, अपनी भावना और तात्कालिक प्रश्न भी साथ में लिखें।",
                ],
                reflection="इस समय आपके मन में सबसे मुख्य प्रश्न क्या है?",
                response_mode="fallback",
            )
        return GuidanceResult(
            guidance=(
                "Hello. I’m here to offer calm, practical guidance rooted in the "
                "Bhagavad Gita."
            ),
            meaning=(
                "You can share your situation in simple words, and I’ll try to find "
                "the most relevant teaching, verse, and next step."
            ),
            actions=[
                "Write your issue in one sentence, using your own words.",
                "If helpful, mention what you feel and what decision or pain is most present right now.",
            ],
            reflection="What is the one thing most active in your heart or mind right now?",
            response_mode="fallback",
        )

    refs = ", ".join(f"{verse.chapter}.{verse.verse}" for verse in verses)
    primary_verse = verses[0] if verses else None
    primary_ref = _verse_reference(primary_verse) if primary_verse else "2.47"
    chapter_context = _chapter_perspective(
        chapter=primary_verse.chapter if primary_verse else 2,
        language=language,
    )

    # Detect mortality/war queries for a dedicated fallback template.
    is_mortality = any(
        term in message.lower() for term in MORTALITY_OR_WAR_TERMS
    )

    if is_mortality:
        return _build_mortality_fallback(
            message=message,
            verses=verses,
            refs=refs,
            primary_ref=primary_ref,
            primary_verse=primary_verse,
            language=language,
        )

    if language == "hi":
        guidance = (
            f"प्रिय साधक, तुम्हारे प्रश्न '{message}' के संदर्भ में "
            f"{primary_ref} की शिक्षा अत्यंत प्रासंगिक है। कृष्ण ने अर्जुन से यह "
            f"इसलिए कहा क्योंकि {chapter_context}। तुम्हारी स्थिति में भी यही "
            "सिद्धांत लागू होता है: पहले अपने भ्रम या पीड़ा का मूल पहचानो, फिर "
            "वर्तमान में धर्मसंगत, स्पष्ट और साहसी कर्म चुनो। "
            f"इन श्लोकों से दिशा लो: {refs}।"
        )
        meaning = (
            "यह शिक्षा केवल सांत्वना नहीं देती, बल्कि अर्जुन के मोह को कर्तव्य की "
            "स्पष्टता में बदलती है। तुम्हारे प्रसंग में इसका अर्थ है कि परिणाम के "
            "भय या भावनात्मक उलझन से ऊपर उठकर सही अगला कदम चुनना।"
        )
        actions = [
            f"अपने प्रश्न '{message}' को एक वाक्य में स्पष्ट लिखो, ताकि निर्णय का केंद्र साफ रहे।",
            "अगले 24 घंटों के भीतर एक ठोस पहला कदम चुनो और उसे पूरा करो।",
            "कर्म के बाद परिणाम-चिंता छोड़कर समीक्षा करो: क्या यह कदम मुझे अधिक स्पष्टता और शांति दे रहा है?",
        ]
        reflection = "मेरे प्रश्न के संदर्भ में आज का सबसे धर्मसंगत और व्यावहारिक एक कदम क्या है?"
    else:
        guidance = (
            f"Dear seeker, for your exact question '{message}', the teaching of "
            f"{primary_ref} is deeply relevant. Krishna said this to Arjuna because "
            f"{chapter_context}. The same principle applies to your situation: "
            "first recognize the real source of confusion or pain, then choose "
            "a clear, dharmic next action now, instead of getting trapped "
            f"in fear of outcomes. Let these verses guide you: {refs}."
        )
        meaning = (
            "This teaching shows why Krishna guided Arjuna beyond emotional "
            "confusion toward right action. In your context, it means you should "
            "not let fear, attachment, or agitation make the decision for you."
        )
        actions = [
            f"Write your exact dilemma in one sentence: '{message}'.",
            "Choose one concrete next step you can complete in the next 24 hours and execute it.",
            "After acting, review calmly: did this step increase clarity, steadiness, and integrity?",
        ]
        reflection = (
            "What is the most dharmic and practical next action for my exact situation today?"
        )
    guidance = _guidance_with_primary_quote(
        guidance=guidance,
        primary_verse=primary_verse,
        language=language,
    )
    return GuidanceResult(
        guidance=guidance,
        meaning=meaning,
        actions=actions,
        reflection=reflection,
        response_mode="fallback",
    )


def _verse_reference_set(verses: list[Verse]) -> set[str]:
    """Build allowed citation set from retrieved verses."""
    return {f"{verse.chapter}.{verse.verse}" for verse in verses}


def _serialize_verses_for_prompt(verses: list[Verse], *, message: str = "") -> str:
    """Serialize retrieved verses into rich prompt context text.

    Provides the LLM with translations, meanings, multi-author commentary,
    and additional interpretive angles so it can craft deeply informed guidance.
    """
    lines = []
    for verse in verses:
        ref = _verse_reference(verse)
        row = _merged_verse_context(ref)
        angle = _additional_angle_text(ref, limit=3)
        commentary = _author_commentary_text(ref, limit=3, message=message)
        synthesis = _safe_get_verse_synthesis_record(verse)
        synthesis_text = ""
        if synthesis is not None:
            synthesis_text = (
                f"(cached_overview_en: {synthesis.overview_en[:280]}) "
                f"(cached_commentary_consensus_en: {synthesis.commentary_consensus_en[:280]}) "
                f"(cached_life_application_en: {synthesis.life_application_en[:220]})"
            )
        lines.append(
            (
                f"{verse.chapter}.{verse.verse}: {verse.translation} "
                f"(themes: {', '.join(verse.themes)}) "
                f"(hindi_meaning: {row.get('hindi', '')[:200]}) "
                f"(english_meaning: {row.get('english', '')[:200]}) "
                f"(word_meaning: {row.get('word_meaning', '')[:200]}) "
                f"(additional_angles: {angle[:400]}) "
                f"(author_commentary: {commentary[:500]}) "
                f"{synthesis_text}"
            )
        )
    return "\n".join(lines)


def _serialize_conversation_context(conversation_messages) -> str:
    """Serialize recent thread context for conversation-aware guidance."""
    if not conversation_messages:
        return ""

    lines = []
    for message in conversation_messages[-6:]:
        role = getattr(message, "role", "")
        content = getattr(message, "content", "")
        if not content:
            continue
        speaker = "User" if role == "user" else "Guide"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _extract_references(text: str) -> set[str]:
    """Extract chapter.verse references from free-form text."""
    return set(re.findall(r"\b\d{1,2}\.\d{1,3}\b", text))


def _parse_json_payload(output_text: str) -> dict:
    """Parse model output to JSON, tolerating wrapped prose/markdown."""
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", output_text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output.")
    return json.loads(match.group(0))


def _is_grounded_response(
    guidance: str,
    meaning: str,
    references: list[str],
    allowed_references: set[str],
) -> bool:
    """Validate that cited references are within retrieved context."""
    if not references:
        return False

    normalized_refs = {ref.strip() for ref in references if ref.strip()}
    text_refs = _extract_references(f"{guidance} {meaning}")
    all_refs = normalized_refs | text_refs
    return bool(all_refs) and all_refs.issubset(allowed_references)


def _validate_and_correct_verses(
    message: str,
    verses: list[Verse],
) -> list[Verse]:
    """Ask LLM whether retrieved verses are relevant; swap if not.

    Returns original verses when:
    - no API key configured
    - LLM confirms verses are relevant
    - LLM call fails (graceful degradation)
    """
    if not settings.OPENAI_API_KEY or not verses:
        return verses

    verse_summaries = []
    for v in verses[:5]:
        verse_summaries.append(
            f"{v.chapter}.{v.verse}: {v.translation[:200]}"
        )
    verses_text = "\n".join(verse_summaries)

    prompt = (
        "You are a Bhagavad Gita verse-relevance evaluator.\n\n"
        f"User question: {message}\n\n"
        f"Retrieved verses:\n{verses_text}\n\n"
        "Task:\n"
        "1. Decide if the retrieved verses are relevant to the user's question.\n"
        "2. If YES (at least 1 verse clearly addresses the user's concern), "
        "respond with EXACTLY this JSON: {\"relevant\": true}\n"
        "3. If NO (none of the retrieved verses meaningfully address the question), "
        "respond with JSON: {\"relevant\": false, \"better_refs\": [\"chapter.verse\", ...]} "
        "where better_refs contains 2-4 Bhagavad Gita verse references (e.g. \"2.47\") "
        "that would genuinely address the user's concern. Only suggest verses you are "
        "confident exist in the Bhagavad Gita (chapters 1-18).\n\n"
        "Return ONLY the JSON object, no other text."
    )

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            input=[{"role": "user", "content": prompt}],
        )
        payload = _parse_json_payload(response.output_text)

        if payload.get("relevant", True):
            return verses

        better_refs = payload.get("better_refs", [])
        if not isinstance(better_refs, list) or not better_refs:
            return verses

        # Sanitise refs — only allow valid chapter.verse format
        sanitised = [
            ref for ref in better_refs
            if isinstance(ref, str) and _parse_reference(ref.strip())
        ][:5]

        if not sanitised:
            return verses

        corrected = _fetch_verses_by_references(sanitised)
        if not corrected:
            return verses

        logger.info(
            "Verse correction: swapped [%s] → [%s] for query: %s",
            ", ".join(f"{v.chapter}.{v.verse}" for v in verses[:5]),
            ", ".join(f"{v.chapter}.{v.verse}" for v in corrected),
            message[:80],
        )
        return corrected

    except Exception as exc:
        logger.warning("Verse validation LLM call failed: %s", exc)
        return verses


def build_guidance(
    message: str,
    verses: list[Verse],
    conversation_messages=None,
    language: str = "en",
    query_interpretation: dict[str, object] | None = None,
    mode: str = "simple",
    max_output_tokens: int = 350,
) -> GuidanceResult:
    """Generate grounded guidance via OpenAI with strict fallback path."""
    language = _normalize_language(language)
    # Truncate oversized inputs before any LLM processing.
    max_chars = getattr(settings, "MAX_ASK_INPUT_CHARS", 2200)
    if len(message) > max_chars:
        message = message[:max_chars]
    query_interpretation = query_interpretation or interpret_query(message).as_dict()
    if _is_greeting_like(message):
        return _build_fallback_guidance(
            message,
            verses=[],
            language=language,
        )
    if not settings.OPENAI_API_KEY:
        return _build_fallback_guidance(
            message,
            verses,
            language=language,
        )

    # Detect specific topic from user message
    message_lower = message.lower()
    detected_topic = "general life guidance"
    topic_advice = ""

    if any(word in message_lower for word in ["study", "studies", "exam", "school", "college", "learn", "education", "marks", "grades", "homework", "test"]):
        detected_topic = "STUDIES AND EDUCATION"
        topic_advice = (
            "Give advice about: concentration techniques, study schedules, "
            "overcoming procrastination, memory improvement, reducing exam anxiety, "
            "finding motivation to study, dealing with difficult subjects. "
            "Suggest specific study tips like Pomodoro technique, active recall, etc."
        )
    elif any(word in message_lower for word in ["relationship", "love", "breakup", "marriage", "partner", "girlfriend", "boyfriend", "spouse", "husband", "wife", "dating"]):
        detected_topic = "RELATIONSHIPS AND LOVE"
        topic_advice = (
            "Give advice about: healthy attachment, communication, trust, "
            "dealing with heartbreak, balancing love and personal growth, "
            "understanding others' perspectives."
        )
    elif any(word in message_lower for word in ["anxiety", "stress", "worried", "fear", "panic", "nervous", "tension", "overwhelm"]):
        detected_topic = "ANXIETY AND STRESS"
        topic_advice = (
            "Give advice about: calming techniques, breathing exercises, "
            "staying present, reducing overthinking, acceptance practices."
        )
    elif any(word in message_lower for word in ["job", "career", "work", "office", "boss", "colleague", "profession", "salary", "promotion"]):
        detected_topic = "CAREER AND WORK"
        topic_advice = (
            "Give advice about: finding purpose in work, dealing with workplace challenges, "
            "balancing ambition with contentment, handling office politics."
        )
    elif any(word in message_lower for word in ["angry", "anger", "rage", "frustrated", "irritated", "annoyed"]):
        detected_topic = "ANGER MANAGEMENT"
        topic_advice = (
            "Give advice about: controlling impulses, finding inner peace, "
            "responding instead of reacting, understanding anger triggers."
        )
    elif any(word in message_lower for word in ["sad", "depressed", "lonely", "hopeless", "unhappy", "miserable"]):
        detected_topic = "SADNESS AND EMOTIONAL PAIN"
        topic_advice = (
            "Give advice about: finding inner strength, accepting difficult emotions, "
            "connecting with purpose, self-compassion practices."
        )
    elif any(word in message_lower for word in ["war", "death", "die", "dying", "destroy", "destruction", "kill", "weapon", "battle", "conflict", "world war", "nuclear", "safe", "safety", "apocalypse"]):
        detected_topic = "WAR, DEATH, AND THE IMMORTAL SELF"
        topic_advice = (
            "Give advice about: why war and conflict happen according to the Gita "
            "(attachment, desire, anger chain in 2.62-63), the immortality of the "
            "Self (atman is never born and never dies, 2.20; weapons cannot cut it, "
            "2.23), the temporary nature of pain and pleasure (2.14), that death of "
            "the body is certain but the Self survives (2.27), and how to find "
            "steadiness amid chaos (2.47, 18.66). Address their existential fear "
            "compassionately. Do NOT give generic duty advice. Explain what the Gita "
            "says about: 1) why destruction happens, 2) what is truly indestructible, "
            "3) how to act with calm wisdom rather than panic."
        )

    allowed_refs = _verse_reference_set(verses)
    verses_context = _serialize_verses_for_prompt(verses, message=message)
    primary_verse = verses[0] if verses else None
    primary_reference = _verse_reference(primary_verse) if primary_verse else ""
    primary_chapter_context = _chapter_perspective(
        chapter=primary_verse.chapter if primary_verse else 2,
        language=language,
    )
    conversation_context = _serialize_conversation_context(
        conversation_messages,
    )
    system_prompt = (
        "You are a Bhagavad Gita guidance assistant. Return valid JSON only "
        "with keys: "
        "guidance, meaning, actions, reflection, verse_references. "
        "Speak in a deeply compassionate, serene, guru-like voice inspired "
        "by Krishna's wisdom. Do not claim literal divine identity. "
        "Be calm, emotionally satisfying, and spiritually grounding. "
        "CRITICAL: Your advice must be DIRECTLY RELEVANT to the user's specific "
        "problem. If they ask about studies, give study advice. If they ask about "
        "relationships, give relationship advice. DO NOT default to generic "
        "'do your duty' responses. Make your guidance PRACTICAL and ACTIONABLE "
        "for their exact situation. "
        "VERSE RELEVANCE: First evaluate whether the provided verses "
        "truly address the user's concern. If they do, use them. If none of "
        "the provided verses are relevant, you may reference other Bhagavad "
        "Gita verses you know are more appropriate — include those in "
        "verse_references. Prefer provided verses when they fit. "
        "Keep advice safe and "
        "non-medical/non-legal. Always answer the user's latest message "
        "as the primary task. Use conversation history only as supporting "
        "context for continuity, not as the main question to answer. "
        "If language_code is 'hi', write all user-facing text in natural "
        "Hindi (Devanagari). If language_code is 'en', write in English."
    )
    user_prompt = (
        f"language_code: {language}\n\n"
        f"DETECTED TOPIC: {detected_topic}\n"
        f"TOPIC-SPECIFIC GUIDANCE REQUIRED: {topic_advice}\n\n"
        f"Structured query interpretation: {json.dumps(query_interpretation, ensure_ascii=False)}\n\n"
        f"User problem:\n{message}\n\n"
        f"Recent conversation context:\n{conversation_context or 'None'}\n\n"
        f"Primary verse candidate by retrieval rank: "
        f"{primary_reference or 'None'}\n"
        f"Context for why Krishna said this to Arjuna: "
        f"{primary_chapter_context}\n\n"
        f"Available verse context:\n{verses_context}\n\n"
        "Requirements:\n"
        f"- MANDATORY: This is about {detected_topic}. Your entire response MUST be "
        f"specifically about {detected_topic.lower()}. DO NOT give generic duty advice.\n"
        f"- {topic_advice}\n"
        "- answer the latest user problem above, not the older history\n"
        "- first line must directly address the user's exact situation using THEIR words\n"
        "- give PRACTICAL, SPECIFIC advice for their exact problem:\n"
        "  * For studies: concentration techniques, discipline, overcoming procrastination\n"
        "  * For relationships: trust, communication, attachment vs love\n"
        "  * For anxiety: calming techniques, present-moment focus\n"
        "  * For work: prioritization, dealing with colleagues, finding purpose\n"
        "- use a soothing, reassuring, devotional-guru tone that increases "
        "the seeker's calmness and curiosity for the next step\n"
        "- structure the answer logic in this order: "
        "1) acknowledge the user's specific struggle with empathy, "
        "2) what Krishna taught about this type of challenge, "
        "3) concrete steps the user can take TODAY for their specific situation\n"
        "- explicitly connect Krishna's teaching to the user's exact problem, "
        "not just quote verses generically\n"
        "- use the structured query interpretation to decide whether the best verse match "
        "is direct, interpretive, or exploratory, and shape the answer honestly\n"
        "- choose one most relevant verse as the primary anchor (prefer the "
        "first retrieved verse unless another is clearly more relevant)\n"
        "- include one short direct quote from the chosen primary verse "
        "translation in guidance or meaning\n"
        "- do not merely summarize the verse; interpret Krishna's intention "
        "and bridge it to the user's SPECIFIC dilemma\n"
        "- if author commentary perspectives are present in the verse context, "
        "use them only to better understand the verse, not to override the verse "
        "itself or cite authors in place of Krishna's teaching\n"
        "- if the user asks a practical or emotional question, show how the "
        "battlefield teaching becomes a life principle for that modern context\n"
        "- for decision dilemmas (e.g., option A vs option B), give one clear "
        "recommended default path for the next 14 days, explain why, and include "
        "a measurable decision checkpoint\n"
        "- for every question type, explicitly reference the user's concrete context "
        "and keywords from their message\n"
        "- avoid generic motivational wording; ensure recommendation is specific "
        "to the user query\n"
        "- when recent conversation context exists, use it only to better "
        "understand the latest problem and maintain continuity\n"
        "- do not drift back to older unresolved topics unless the latest "
        "message clearly asks to revisit them\n"
        "- guidance: 2-4 sentences, MUST mention user's specific topic\n"
        "- meaning: 1-2 sentences explaining how this applies to THEIR situation\n"
        "- actions: array of 2-3 concrete actions SPECIFIC to their problem "
        "(e.g., for studies: 'Set a 25-minute focused study timer', "
        "NOT generic 'do your duty')\n"
        "- reflection: one question about THEIR specific situation\n"
        "- verse_references: array of chapter.verse references. Prefer "
        "verses from the provided context, but if none are relevant you may "
        "include other Gita verse references you are confident about\n"
        "- write guidance/meaning/actions/reflection in the specified "
        "language_code\n"
        + (
            "\n"
            "DEEP MODE ACTIVE — this is a paid deep-reflection request. "
            "Expand every section significantly beyond the simple baseline:\n"
            "- guidance: 4-6 sentences with richer emotional and spiritual depth\n"
            "- meaning: 2-3 sentences with Mahabharata/Upanishad historical context "
            "for why Krishna said this to Arjuna in that exact moment\n"
            "- actions: 3-5 concrete, sequenced actions with reasoning for each\n"
            "- reflection: 2-3 deep introspective questions, not just one\n"
            "- Include the emotional/psychological dimension: name the inner state "
            "the user is probably experiencing and validate it before offering guidance\n"
            "- Connect to a yogic or breathwork practice specifically aligned to "
            "the verse's energy (e.g., pranayama for anger, nadi shodhana for anxiety)\n"
            if mode == "deep" else ""
        )
    )

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            max_output_tokens=max_output_tokens,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        payload = _parse_json_payload(response.output_text)

        guidance = str(payload.get("guidance", "")).strip()
        meaning = str(payload.get("meaning", "")).strip()
        reflection = str(payload.get("reflection", "")).strip()
        actions = payload.get("actions", [])
        references = payload.get("verse_references", [])

        if not isinstance(actions, list):
            actions = []
        actions = [
            str(action).strip()
            for action in actions
            if str(action).strip()
        ][:3]

        if not isinstance(references, list):
            references = []
        references = [
            str(ref).strip()
            for ref in references
            if str(ref).strip()
        ]

        # Expand allowed refs: accept LLM-suggested refs that exist
        # in our DB so the grounding check doesn't reject corrections.
        extra_refs = {
            ref for ref in references if ref not in allowed_refs
        }
        if extra_refs:
            verified = _fetch_verses_by_references(list(extra_refs))
            for v in verified:
                allowed_refs.add(f"{v.chapter}.{v.verse}")

        if (
            not guidance
            or not meaning
            or not reflection
            or len(actions) < 2
            or not _is_context_relevant_response(
                message=message,
                guidance=guidance,
                meaning=meaning,
            )
            or not _is_grounded_response(
                guidance,
                meaning,
                references,
                allowed_refs,
            )
        ):
            return _build_fallback_guidance(
                message,
                verses,
                language=language,
            )

        guidance = _guidance_with_primary_quote(
            guidance=guidance,
            primary_verse=primary_verse,
            language=language,
        )

        return GuidanceResult(
            guidance=guidance,
            meaning=meaning,
            actions=actions,
            reflection=reflection,
            response_mode="llm",
        )
    except Exception as exc:
        logger.warning("OpenAI guidance generation failed: %s", exc)
        return _build_fallback_guidance(
            message,
            verses,
            language=language,
        )


# --- Chapter and Verse Browsing APIs ---

_chapter_metadata_cache: dict[int, dict[str, object]] | None = None


def _load_chapter_metadata_cache() -> dict[int, dict[str, object]]:
    """Load all chapter JSON files into a cache."""
    global _chapter_metadata_cache
    if _chapter_metadata_cache is not None:
        return _chapter_metadata_cache

    _chapter_metadata_cache = {}
    chapter_dir = Path(__file__).resolve().parents[1] / "data" / "chapter"
    if not chapter_dir.exists():
        return _chapter_metadata_cache

    try:
        for path in sorted(chapter_dir.glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            chapter_num = row.get("chapter_number")
            if not chapter_num:
                continue
            meaning = row.get("meaning", {}) if isinstance(row.get("meaning"), dict) else {}
            summary = row.get("summary", {}) if isinstance(row.get("summary"), dict) else {}
            _chapter_metadata_cache[int(chapter_num)] = {
                "chapter_number": int(chapter_num),
                "name": str(row.get("name", "")).strip(),
                "translation": str(row.get("translation", "")).strip(),
                "transliteration": str(row.get("transliteration", "")).strip(),
                "verses_count": int(row.get("verses_count", 0)),
                "meaning_en": str(meaning.get("en", "")).strip(),
                "meaning_hi": str(meaning.get("hi", "")).strip(),
                "summary_en": str(summary.get("en", "")).strip(),
                "summary_hi": str(summary.get("hi", "")).strip(),
            }
    except Exception as exc:
        logger.warning("Chapter metadata cache load failed: %s", exc)
    return _chapter_metadata_cache


def get_all_chapters() -> list[dict[str, object]]:
    """Return list of all chapters with metadata for listing screen."""
    cache = _load_chapter_metadata_cache()
    return [cache[i] for i in sorted(cache.keys())]


def get_chapter_detail(chapter_number: int) -> dict[str, object] | None:
    """Return full chapter detail including summary."""
    cache = _load_chapter_metadata_cache()
    return cache.get(chapter_number)


def get_chapter_verses(chapter_number: int) -> list[dict[str, object]]:
    """Return all verses for a chapter with basic info."""
    ensure_seed_verses()
    verses = Verse.objects.filter(chapter=chapter_number).order_by("verse")
    result = []
    for verse in verses:
        ref = _verse_reference(verse)
        row = _merged_verse_context(ref)
        result.append({
            "reference": ref,
            "chapter": verse.chapter,
            "verse": verse.verse,
            "slok": str(row.get("sanskrit", "")).strip(),
            "translation": verse.translation,
            "speaker": "",
        })
    return result


def get_verse_detail(chapter: int, verse: int) -> dict[str, object] | None:
    """Return full verse detail with all commentaries."""
    ensure_seed_verses()
    verse_obj = Verse.objects.filter(chapter=chapter, verse=verse).first()
    if verse_obj is None:
        return None

    ref = _verse_reference(verse_obj)
    row = _merged_verse_context(ref)
    vedic = _load_vedic_slok_row(ref)

    # Build commentaries list from vedic cache
    commentaries = []
    for entry in vedic.get("commentaries", []):
        author = str(entry.get("author", "")).strip()
        text = str(entry.get("text", "")).strip()
        if author and text:
            # Detect language: if majority is Devanagari, mark as Hindi
            hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
            lang = "hi" if hindi_chars > len(text) * 0.3 else "en"
            commentaries.append({
                "author": author,
                "text": text,
                "language": lang,
            })

    synthesis = get_or_create_verse_synthesis(verse_obj)

    return {
        "reference": ref,
        "chapter": verse_obj.chapter,
        "verse": verse_obj.verse,
        "speaker": str(vedic.get("speaker", "")).strip(),
        "slok": str(vedic.get("slok", row.get("sanskrit", ""))).strip(),
        "transliteration": str(
            vedic.get("transliteration", row.get("transliteration", ""))
        ).strip(),
        "translation": verse_obj.translation,
        "themes": verse_obj.themes,
        "hindi_meaning": str(row.get("hindi", "")).strip(),
        "english_meaning": str(row.get("english", "")).strip(),
        "word_meaning": str(row.get("word_meaning", "")).strip(),
        "commentaries": commentaries,
        "synthesis": synthesis,
    }


def _verse_synthesis_source_text(verse: Verse) -> str:
    """Build stable source text for verse synthesis generation and invalidation."""
    ref = _verse_reference(verse)
    row = _merged_verse_context(ref)
    vedic = _load_vedic_slok_row(ref)
    commentary_lines = [
        f"{entry.get('author', '').strip()}: {entry.get('text', '').strip()}"
        for entry in _author_commentary_entries(ref)
        if str(entry.get("author", "")).strip() and str(entry.get("text", "")).strip()
    ]
    angle_lines = [
        " | ".join(
            part
            for part in [
                str(item.get("source", "")).strip(),
                str(item.get("english", "")).strip(),
                str(item.get("hindi", "")).strip(),
            ]
            if part
        )
        for item in list(row.get("angles", []))
    ]
    parts = [
        f"Reference: {ref}",
        f"Sanskrit: {str(vedic.get('slok', row.get('sanskrit', ''))).strip()}",
        f"Transliteration: {str(vedic.get('transliteration', row.get('transliteration', ''))).strip()}",
        f"Translation: {verse.translation}",
        f"English meaning: {str(row.get('english', '')).strip()}",
        f"Hindi meaning: {str(row.get('hindi', '')).strip()}",
        f"Word meaning: {str(row.get('word_meaning', '')).strip()}",
        f"Themes: {', '.join(verse.themes)}",
        f"Additional angles: {' || '.join(angle_lines)}",
        f"Commentaries: {' || '.join(commentary_lines)}",
    ]
    return "\n".join(part for part in parts if part.strip())


def _verse_synthesis_source_hash(verse: Verse) -> str:
    """Create a deterministic hash of verse source material."""
    return hashlib.sha256(
        f"{VERSE_SYNTHESIS_SCHEMA_VERSION}\n{_verse_synthesis_source_text(verse)}".encode("utf-8"),
    ).hexdigest()


def _normalize_string_list(value: object, *, limit: int = 4) -> list[str]:
    """Normalize list-like model output into compact string arrays."""
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ][:limit]


def _build_fallback_verse_synthesis_payload(verse: Verse) -> dict[str, object]:
    """Create deterministic verse synthesis when no LLM call is available."""
    ref = _verse_reference(verse)
    row = _merged_verse_context(ref)
    english_commentaries = _preferred_commentary_entries(
        ref,
        language="en",
        limit=3,
    )
    hindi_commentaries = _preferred_commentary_entries(
        ref,
        language="hi",
        limit=3,
    )
    author_names = ", ".join(
        str(entry.get("author", "")).strip()
        for entry in english_commentaries
        if str(entry.get("author", "")).strip()
    )
    english = str(row.get("english", "")).strip() or verse.translation
    hindi = str(row.get("hindi", "")).strip()
    word_meaning = str(row.get("word_meaning", "")).strip()
    commentary_focus_en = " ".join(
        str(entry.get("text", "")).strip()
        for entry in english_commentaries
        if str(entry.get("text", "")).strip()
    )[:300]
    commentary_focus_hi = " ".join(
        str(entry.get("text", "")).strip()
        for entry in hindi_commentaries
        if str(entry.get("text", "")).strip()
    )[:300]
    themes = ", ".join(verse.themes) if verse.themes else "daily life guidance"
    compact_theme_text = (
        ", ".join(verse.themes[:3]) if verse.themes else "daily life guidance"
    )

    overview_en = (
        f"Bhagavad Gita {ref} teaches steadiness in action through {compact_theme_text}. "
        f"Krishna's central message here is: {english}"
    ).strip()
    overview_hi = (
        f"भगवद्गीता {ref} का मुख्य संदेश है: {hindi or english} "
        f"यह श्लोक {(' और '.join(verse.themes[:2]) if verse.themes else 'दैनिक जीवन की दिशा')} में स्थिर बुद्धि सिखाता है।"
    ).strip()
    commentary_consensus_en = (
        "Across the available commentaries, this verse is consistently read as a teaching "
        "of inner discipline and selfless action, not passive withdrawal. "
        f"{'Key voices here include ' + author_names + '. ' if author_names else ''}"
        f"{commentary_focus_en or word_meaning or english}"
    ).strip()
    commentary_consensus_hi = (
        "उपलब्ध टीकाओं का सम्मिलित संकेत यह है कि यह श्लोक केवल सिद्धांत नहीं, "
        "निष्काम कर्म, भीतरी अनुशासन और शांत दृष्टि की साधना सिखाता है। "
        f"{commentary_focus_hi or hindi or english}"
    ).strip()
    life_application_en = (
        "In modern life, use this verse before any important step: focus on the sincerity "
        "of your effort, loosen anxiety about results, and act from steadiness rather than panic."
    )
    life_application_hi = (
        "आधुनिक जीवन में यह श्लोक हमें याद दिलाता है कि फल की चिंता से पहले कर्म की "
        "शुद्धता पर ध्यान दें, और भय या उतावलेपन से नहीं बल्कि स्थिरता से कदम उठाएँ।"
    )
    key_points_en = [
        english,
        commentary_focus_en or "The commentaries emphasize steady, selfless action.",
        "Use this verse as a practical checkpoint before acting under pressure.",
    ]
    key_points_hi = [
        hindi or english,
        commentary_focus_hi or "टीकाएं इस श्लोक को निष्काम कर्म और भीतर की स्थिरता से जोड़ती हैं।",
        "इसे किसी भी महत्वपूर्ण कर्म से पहले आत्म-परीक्षण के सूत्र की तरह उपयोग किया जा सकता है।",
    ]
    return {
        "overview_en": overview_en,
        "overview_hi": overview_hi,
        "commentary_consensus_en": commentary_consensus_en,
        "commentary_consensus_hi": commentary_consensus_hi,
        "life_application_en": life_application_en,
        "life_application_hi": life_application_hi,
        "key_points_en": key_points_en,
        "key_points_hi": key_points_hi,
    }


def _validate_verse_synthesis_payload(
    payload: dict[str, object],
    *,
    verse: Verse,
) -> dict[str, object]:
    """Normalize and complete verse synthesis payload from model output."""
    fallback = _build_fallback_verse_synthesis_payload(verse)
    cleaned = {
        "overview_en": str(payload.get("overview_en", "")).strip(),
        "overview_hi": str(payload.get("overview_hi", "")).strip(),
        "commentary_consensus_en": str(payload.get("commentary_consensus_en", "")).strip(),
        "commentary_consensus_hi": str(payload.get("commentary_consensus_hi", "")).strip(),
        "life_application_en": str(payload.get("life_application_en", "")).strip(),
        "life_application_hi": str(payload.get("life_application_hi", "")).strip(),
        "key_points_en": _normalize_string_list(payload.get("key_points_en")),
        "key_points_hi": _normalize_string_list(payload.get("key_points_hi")),
    }
    for key, fallback_value in fallback.items():
        if isinstance(fallback_value, list):
            if not cleaned[key]:
                cleaned[key] = fallback_value
        elif not cleaned[key]:
            cleaned[key] = fallback_value
    return cleaned


def _verse_synthesis_embedding_text(record: VerseSynthesis) -> str:
    """Serialize cached synthesis for semantic reuse."""
    return (
        f"Verse {record.verse.chapter}.{record.verse.verse}\n"
        f"Overview EN: {record.overview_en}\n"
        f"Overview HI: {record.overview_hi}\n"
        f"Commentary Consensus EN: {record.commentary_consensus_en}\n"
        f"Commentary Consensus HI: {record.commentary_consensus_hi}\n"
        f"Life Application EN: {record.life_application_en}\n"
        f"Life Application HI: {record.life_application_hi}\n"
        f"Key Points EN: {' | '.join(record.key_points_en)}\n"
        f"Key Points HI: {' | '.join(record.key_points_hi)}"
    )


def _refresh_verse_synthesis_embedding(record: VerseSynthesis) -> None:
    """Attach an embedding to cached synthesis for later retrieval reuse."""
    if not settings.OPENAI_API_KEY:
        return
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=_verse_synthesis_embedding_text(record),
        )
        record.embedding = response.data[0].embedding
        record.save(update_fields=["embedding", "updated_at"])
    except Exception as exc:  # pragma: no cover - network failures
        logger.warning("Verse synthesis embedding refresh failed: %s", exc)


def _serialize_cached_verse_synthesis(
    record: VerseSynthesis,
    *,
    cached: bool,
) -> dict[str, object]:
    """Expose stored synthesis in a stable API shape for the UI."""
    return {
        "generation_source": record.generation_source,
        "overview_en": record.overview_en,
        "overview_hi": record.overview_hi,
        "commentary_consensus_en": record.commentary_consensus_en,
        "commentary_consensus_hi": record.commentary_consensus_hi,
        "life_application_en": record.life_application_en,
        "life_application_hi": record.life_application_hi,
        "key_points_en": list(record.key_points_en or []),
        "key_points_hi": list(record.key_points_hi or []),
        "cached": cached,
    }


def get_or_create_verse_synthesis(verse: Verse) -> dict[str, object]:
    """Return cached multilingual verse synthesis, generating it once when needed."""
    expected_hash = _verse_synthesis_source_hash(verse)
    existing = _safe_get_verse_synthesis_record(verse)
    if (
        existing is not None
        and existing.source_hash == expected_hash
        and existing.overview_en
        and existing.overview_hi
    ):
        return _serialize_cached_verse_synthesis(existing, cached=True)

    payload = _build_fallback_verse_synthesis_payload(verse)
    generation_source = VerseSynthesis.SOURCE_FALLBACK
    if settings.OPENAI_API_KEY:
        system_prompt = (
            "You are a Bhagavad Gita verse synthesis assistant. "
            "Return valid JSON only with keys: "
            "overview_en, overview_hi, commentary_consensus_en, commentary_consensus_hi, "
            "life_application_en, life_application_hi, key_points_en, key_points_hi. "
            "Ground everything strictly in the supplied verse data, meanings, and "
            "multi-author commentary. Interconnect the authors' perspectives into a "
            "single coherent understanding without inventing claims."
        )
        user_prompt = (
            f"Create a rich multilingual synthesis for Bhagavad Gita {verse.chapter}.{verse.verse}.\n\n"
            "Requirements:\n"
            "- overview_en: 2-3 sentences in English summarizing the verse's core wisdom\n"
            "- overview_hi: 2-3 sentences in natural Hindi (Devanagari)\n"
            "- commentary_consensus_en/hi: explain how the various commentaries connect, agree, "
            "or add nuance\n"
            "- life_application_en/hi: explain how a seeker can apply this verse in modern life\n"
            "- key_points_en/hi: arrays of 3 short bullet-style insights\n"
            "- keep Krishna's teaching central; use commentators only as interpretive support\n"
            "- do not mention missing data or say 'based on the provided text'\n\n"
            f"Verse source material:\n{_verse_synthesis_source_text(verse)}"
        )
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.responses.create(
                model=settings.OPENAI_MODEL,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            payload = _validate_verse_synthesis_payload(
                _parse_json_payload(response.output_text),
                verse=verse,
            )
            generation_source = VerseSynthesis.SOURCE_LLM
        except Exception as exc:  # pragma: no cover - network failures
            logger.warning("Verse synthesis generation failed: %s", exc)

    try:
        record = existing or VerseSynthesis(verse=verse)
    except (OperationalError, ProgrammingError):
        return _build_fallback_verse_synthesis_payload(verse) | {
            "generation_source": VerseSynthesis.SOURCE_FALLBACK,
            "cached": False,
        }
    record.source_hash = expected_hash
    record.generation_source = generation_source
    record.overview_en = str(payload.get("overview_en", "")).strip()
    record.overview_hi = str(payload.get("overview_hi", "")).strip()
    record.commentary_consensus_en = str(payload.get("commentary_consensus_en", "")).strip()
    record.commentary_consensus_hi = str(payload.get("commentary_consensus_hi", "")).strip()
    record.life_application_en = str(payload.get("life_application_en", "")).strip()
    record.life_application_hi = str(payload.get("life_application_hi", "")).strip()
    record.key_points_en = _normalize_string_list(payload.get("key_points_en"))
    record.key_points_hi = _normalize_string_list(payload.get("key_points_hi"))
    try:
        record.save()
    except (OperationalError, ProgrammingError):
        return _build_fallback_verse_synthesis_payload(verse) | {
            "generation_source": VerseSynthesis.SOURCE_FALLBACK,
            "cached": False,
        }

    if settings.OPENAI_API_KEY and not record.embedding:
        _refresh_verse_synthesis_embedding(record)

    return _serialize_cached_verse_synthesis(record, cached=False)


# --- Mantra Generation ---

MOOD_VERSE_MAP = {
    "calm": ["2.48", "2.70", "6.35", "12.15"],
    "focus": ["6.12", "6.26", "3.19", "2.47"],
    "courage": ["2.3", "2.31", "2.37", "18.66"],
    "peace": ["2.66", "2.71", "5.29", "12.12"],
    "strength": ["3.30", "6.5", "18.58", "2.47"],
    "clarity": ["2.50", "3.35", "18.63", "5.20"],
}


def get_mantra_for_mood(mood: str, language: str = "en") -> dict[str, object] | None:
    """Return a suitable verse as a mantra for the given mood."""
    import random

    language = _normalize_language(language)
    refs = MOOD_VERSE_MAP.get(mood, MOOD_VERSE_MAP["peace"])
    ref = random.choice(refs)
    parsed = _parse_reference(ref)
    if not parsed:
        return None

    chapter, verse = parsed
    verse_obj = Verse.objects.filter(chapter=chapter, verse=verse).first()
    if verse_obj is None:
        return None

    row = _merged_verse_context(ref)
    vedic = _load_vedic_slok_row(ref)

    if language == "hi":
        meaning = row.get("hindi", "") or verse_obj.translation
        intro = "इस मंत्र को दिन में तीन बार दोहराएं:"
    else:
        meaning = row.get("english", "") or verse_obj.translation
        intro = "Repeat this mantra three times today:"

    return {
        "reference": ref,
        "mood": mood,
        "slok": str(vedic.get("slok", row.get("sanskrit", ""))).strip(),
        "transliteration": str(
            vedic.get("transliteration", row.get("transliteration", ""))
        ).strip(),
        "meaning": meaning.strip(),
        "instruction": intro,
        "language": language,
    }


# --- Quote Art Generation ---

QUOTE_ART_STYLES = {
    "divine": {
        "name": "Divine",
        "description": "Golden temple aesthetic with warm tones",
        "background_color": "#1a1a2e",
        "text_color": "#ffd700",
        "accent_color": "#ff6b35",
        "font_style": "serif",
        "gradient": ["#1a1a2e", "#16213e", "#0f3460"],
    },
    "minimal": {
        "name": "Minimal",
        "description": "Clean modern design with subtle gradients",
        "background_color": "#fafafa",
        "text_color": "#2d3436",
        "accent_color": "#6c5ce7",
        "font_style": "sans-serif",
        "gradient": ["#fafafa", "#f5f5f5", "#eeeeee"],
    },
    "nature": {
        "name": "Nature",
        "description": "Forest and lotus imagery with earthy tones",
        "background_color": "#1b4332",
        "text_color": "#d8f3dc",
        "accent_color": "#95d5b2",
        "font_style": "serif",
        "gradient": ["#1b4332", "#2d6a4f", "#40916c"],
    },
    "cosmic": {
        "name": "Cosmic",
        "description": "Stars and universe with deep purple",
        "background_color": "#0d0221",
        "text_color": "#e0aaff",
        "accent_color": "#c77dff",
        "font_style": "sans-serif",
        "gradient": ["#0d0221", "#240046", "#3c096c"],
    },
}


def get_quote_art_styles() -> list[dict[str, str]]:
    """Return available quote art styles for UI selection."""
    return [
        {
            "id": style_id,
            "name": style["name"],
            "description": style["description"],
            "preview_colors": {
                "background": style["background_color"],
                "text": style["text_color"],
                "accent": style["accent_color"],
            },
        }
        for style_id, style in QUOTE_ART_STYLES.items()
    ]


def generate_quote_art_data(
    *,
    verse_reference: str,
    style: str = "divine",
    language: str = "en",
    custom_quote: str | None = None,
) -> dict[str, object] | None:
    """Generate quote art data for a verse reference."""
    language = _normalize_language(language)
    parsed = _parse_reference(verse_reference)
    if not parsed:
        return None

    chapter, verse = parsed
    verse_obj = Verse.objects.filter(chapter=chapter, verse=verse).first()
    if verse_obj is None:
        return None

    ref = verse_reference
    row = _merged_verse_context(ref)
    vedic = _load_vedic_slok_row(ref)

    # Get quote text
    if custom_quote:
        quote_text = custom_quote.strip()
    elif language == "hi":
        quote_text = row.get("hindi", "") or verse_obj.translation
    else:
        quote_text = row.get("english", "") or verse_obj.translation

    # Get Sanskrit shloka
    sanskrit = str(vedic.get("slok", row.get("sanskrit", ""))).strip()

    # Get style configuration
    style_config = QUOTE_ART_STYLES.get(style, QUOTE_ART_STYLES["divine"])

    # Build art data payload
    return {
        "verse_reference": ref,
        "chapter": chapter,
        "verse": verse,
        "quote_text": quote_text.strip(),
        "sanskrit_text": sanskrit,
        "transliteration": str(
            vedic.get("transliteration", row.get("transliteration", ""))
        ).strip(),
        "language": language,
        "style": {
            "id": style,
            "name": style_config["name"],
            "background_color": style_config["background_color"],
            "text_color": style_config["text_color"],
            "accent_color": style_config["accent_color"],
            "font_style": style_config["font_style"],
            "gradient": style_config["gradient"],
        },
        "attribution": f"Bhagavad Gita {ref}",
        "share_text": _build_share_text(
            reference=ref,
            quote=quote_text,
            language=language,
        ),
    }


def _build_share_text(
    *,
    reference: str,
    quote: str,
    language: str,
) -> str:
    """Build shareable text for social media."""
    # Truncate quote if too long for social sharing
    max_quote_len = 200
    truncated = quote[:max_quote_len] + "..." if len(quote) > max_quote_len else quote

    if language == "hi":
        return (
            f'"{truncated}"\n\n'
            f"— भगवद्गीता {reference}\n\n"
            "#BhagavadGita #गीता #Krishna #Wisdom"
        )
    return (
        f'"{truncated}"\n\n'
        f"— Bhagavad Gita {reference}\n\n"
        "#BhagavadGita #Krishna #Wisdom #SpiritualQuotes"
    )


def get_featured_quotes(language: str = "en", limit: int = 5) -> list[dict[str, object]]:
    """Return featured verses for quote art suggestions."""
    language = _normalize_language(language)
    featured_refs = [
        "2.47",  # Karma yoga - most famous
        "2.14",  # Impermanence
        "6.5",   # Be your own friend
        "18.66", # Surrender
        "2.48",  # Equanimity
        "3.35",  # Swadharma
        "6.35",  # Mind control
        "12.13", # Compassion
    ]

    results = []
    for ref in featured_refs[:limit]:
        data = generate_quote_art_data(
            verse_reference=ref,
            style="divine",
            language=language,
        )
        if data:
            results.append({
                "reference": ref,
                "preview_quote": data["quote_text"][:100] + "..."
                if len(data["quote_text"]) > 100
                else data["quote_text"],
                "sanskrit_preview": data["sanskrit_text"][:80] + "..."
                if len(data["sanskrit_text"]) > 80
                else data["sanskrit_text"],
            })

    return results
