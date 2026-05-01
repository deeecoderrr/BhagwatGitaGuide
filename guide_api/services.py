from __future__ import annotations

"""Domain services for safety checks, retrieval, and guidance generation."""

from dataclasses import dataclass, field
import csv
import hashlib
import json
import logging
import math
import re
import threading
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from openai import OpenAI

from guide_api.data.default_verses import DEFAULT_VERSES
from guide_api.models import Verse, VerseSynthesis

logger = logging.getLogger(__name__)
_seed_synced = False
SUPPORTED_LANGUAGE_CODES = {"en", "hi", "hinglish"}

# Roman Hindi tokens often mixed with English (Hinglish). Used when UI language
# is English but the user writes in casual Romanized Hindi.
_HINGLISH_LEXICON = frozenset({
    "aaj", "aane", "aapse", "aap", "aapka", "aapke", "aapko", "aati", "aaya",
    "aaye", "abhi", "agar", "aisa", "aise", "aisi", "andar", "apna", "apne",
    "apni", "aur", "bahut", "bas", "bata", "batao", "bataiye", "bhi", "bilkul",
    "bura", "chaahiye", "chaiye", "chahiye", "chal", "chale", "chalta", "chalo",
    "chhod", "chhodo", "dikkat", "dil", "dimaag", "din", "dunga", "dungi",
    "dukh", "ek", "galat", "ghar", "gussa", "hai", "hain", "halat", "ham",
    "hamara", "hamare", "hamko", "han", "haan", "hoga", "hogi", "hoon", "ho",
    "hoga", "hua", "hue", "hum", "humko", "jaisa", "jaise", "jaana", "jab",
    "jaldi", "jindagi", "zindagi", "kab", "kabhi", "karna", "karte", "karti",
    "karun", "karu", "kar", "karke", "karo", "karta", "karti", "kaise", "kaisa",
    "kaisi", "kuch", "kuchh", "kyun", "kyu", "kya", "khud", "lag", "lagta",
    "lagti", "lagte", "liye", "lo", "mat", "matlab", "mujhe", "mujhko", "mera",
    "meri", "mere", "mana", "mann", "mein", "main", "mai", "mil", "mila",
    "nahi", "nahin", "na", "pata", "par", "pehle", "phir", "pyaar", "pyar",
    "raat", "raha", "rahe", "rahi", "raho", "raha", "reh", "sab", "sabse",
    "saath", "samajh", "samajhta", "samajhti", "samay", "sahi", "sach", "se",
    "sirf", "soch", "sochta", "sochti", "suno", "tab", "tera", "teri", "tere",
    "tum", "tumhara", "tumhari", "tumko", "tumhe", "theek", "thik", "thi",
    "the", "tha", "thi", "tension", "pareshaan", "pareshan", "shaanti", "shanti",
    "sakta", "sakti", "sakte", "sabko", "unko", "unhe", "unka", "usi", "uska",
    "uski", "uske", "uss", "usse", "waqt", "waise", "waisa", "wahi", "yeh",
    "ye", "yahi", "zaroor", "zyada", "zada", "baar", "baarish", "bekaar",
    "bekar", "bhagwan", "bhagwan", "bhool", "bura", "cheez", "darr", "dar",
    "dekho", "dekha", "dost", "dosti", "duniya", "fir", "fikar", "galat",
    "ghabra", "har", "humne", "humko", "izzat", "jhoot", "jhooth", "kaha",
    "kahaa", "kahin", "kam", "karne", "khushi", "kitna", "kitni", "koi",
    "koshish", "kripya", "lagao", "ladai", "ladna", "maaf", "mafi", "mano",
    "manta", "mat", "mehnat", "milna", "milta", "milti", "mujhse", "naam",
    "neeche", "nikal", "pakka", "pal", "pehchaan", "pyaara", "pyaari",
    "qismat", "kismat", "ro", "rona", "ruk", "rukna", "sachchi", "sachha",
    "samay", "samjho", "shaam", "shuru", "sir", "subah", "sukh", "taaki",
    "tak", "tarah", "tha", "the", "thoda", "thodi", "toh", "to", "tyohar",
    "udhar", "uff", "ufff", "uljhan", "upar", "waala", "waale", "wali",
    "wala", "wali", "wale", "yaad", "yaar", "yahan", "yeh", "yun", "yoon",
})


def _devanagari_letter_ratio(text: str) -> float:
    """Share of alphabetic characters that are Devanagari (Hindi script)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    dev = sum(0x0900 <= ord(c) <= 0x097F for c in letters)
    return dev / len(letters)


def _detect_roman_hinglish(text: str) -> bool:
    """True when the message is mostly Latin script but uses Roman Hindi."""
    raw = re.findall(r"[a-zA-Z]+", str(text or "").lower())
    if len(raw) < 2:
        return False
    hits = sum(1 for w in raw if w in _HINGLISH_LEXICON)
    if hits < 2:
        return False
    return hits >= 3 or (hits / len(raw)) >= 0.18


def resolve_guidance_language(requested_language: str, message: str) -> str:
    """Map UI language + message script/register to a guidance language code.

    When the user selects English but writes in Roman Hinglish, answers should
    come back in the same casual Roman Hindi + English mix. When they write in
    Devanagari with English UI selected, prefer full Hindi.
    """
    base = _normalize_language(requested_language)
    if base == "hi":
        return "hi"
    if base != "en":
        return base
    msg = str(message or "").strip()
    if _devanagari_letter_ratio(msg) >= 0.18:
        return "hi"
    if _detect_roman_hinglish(msg):
        return "hinglish"
    return "en"
VERSE_SYNTHESIS_SCHEMA_VERSION = "v2"
_verse_quote_cache: dict[str, dict[str, str]] | None = None
_verse_additional_angle_cache: dict[str, list[dict[str, str]]] | None = None
_merged_verse_context_cache: dict[str, dict[str, object]] = {}
_chapter_summary_cache: dict[int, dict[str, object]] | None = None
_vedic_slok_cache: dict[str, dict[str, object]] = {}
_verse_list_cache: list[Verse] | None = None

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
    "integrity": {
        "ethics",
        "ethical",
        "integrity",
        "honest",
        "honesty",
        "truthful",
        "truthfulness",
        "conflict of interest",
        "confidential",
        "confidentiality",
        "whistleblow",
        "professional conduct",
        "professional ethics",
        "lawyer",
        "attorney",
        "counsel",
        "court",
        "client",
        "clients",
        "bar council",
        "bribe",
        "corruption",
        "नैतिकता",
        "ईमानदारी",
        "वकील",
        "अदालत",
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
    "integrity": {
        "2.19",
        "2.21",
        "3.21",
        "12.16",
        "12.17",
        "17.14",
        "17.15",
        "18.42",
        "18.46",
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
    "integrity": {2, 3, 12, 17, 18},
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
    intent_type: str = "life_guidance"
    show_meaning: bool = True
    show_actions: bool = True
    show_reflection: bool = True
    show_related_verses: bool = True
    # If None, API/chat-ui may build "related verses" via get_related_verses.
    # If set (possibly empty), only these refs are shown as related exploration.
    related_verses_refs: list[str] | None = None


@dataclass
class IntentAnalysis:
    """High-level user-intent routing signal for answer generation."""

    intent_type: str
    explicit_references: list[str] = field(default_factory=list)
    chapter_number: int | None = None
    needs_retrieval: bool = True
    show_actions: bool = True
    show_reflection: bool = True
    show_related_verses: bool = True
    asks_for_application: bool = False
    asks_for_context: bool = False
    asks_for_simple_explanation: bool = False

    def as_dict(self) -> dict[str, object]:
        """Expose stable intent metadata for debugging and prompting."""
        return {
            "intent_type": self.intent_type,
            "explicit_references": list(self.explicit_references),
            "chapter_number": self.chapter_number,
            "needs_retrieval": self.needs_retrieval,
            "show_actions": self.show_actions,
            "show_reflection": self.show_reflection,
            "show_related_verses": self.show_related_verses,
            "asks_for_application": self.asks_for_application,
            "asks_for_context": self.asks_for_context,
            "asks_for_simple_explanation": self.asks_for_simple_explanation,
        }


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

VERSE_REFERENCE_PATTERN = re.compile(
    r"\b(?:bg\s*)?(\d{1,2})\s*[\.:]\s*(\d{1,3})\b",
    flags=re.IGNORECASE,
)

PROBLEM_HINTS = {
    "feel",
    "feeling",
    "stuck",
    "confused",
    "anxious",
    "angry",
    "worried",
    "stress",
    "stressed",
    "lost",
    "hurt",
    "career",
    "relationship",
    "discipline",
    "purpose",
    "problem",
    "issue",
}

# If the user asks how teaching applies to them or what they should do, route to
# life_guidance before study-style detection — otherwise bare "what"/"?" misroutes.
_LIFE_APPLICATION_PHRASES = frozenset({
    "apply",
    "application",
    "in my life",
    "for my life",
    "for me",
    "my situation",
    "today",
    "what should i do",
    "how should i act",
    "what can i do",
    "how do i",
    "how can i",
    "i don't know what to do",
    "i do not know what to do",
})

# Word tokens that suggest a scriptural / conceptual question (not "what" alone).
_KNOWLEDGE_TOPIC_TOKENS = frozenset({
    "verse",
    "verses",
    "sloka",
    "shloka",
    "chapter",
    "krishna",
    "arjuna",
    "gita",
    "gitopadesha",
    "bhagavad",
    "dharma",
    "karma",
    "bhakti",
    "yoga",
    "moksha",
    "sattva",
    "rajas",
    "tamas",
    "atman",
    "brahman",
    "prakriti",
    "upanishad",
    "mahabharata",
    "pandava",
    "kurukshetra",
    "kunti",
    "bhishma",
    "drona",
    "duryodhana",
    "pandu",
    "vyasa",
    "sannyasa",
    "tyaga",
    "jnana",
})

_INTENT_TRIVIAL_ACK = frozenset({
    "ok",
    "okay",
    "k",
    "thanks",
    "thank you",
    "ty",
    "cool",
    "nice",
    "bye",
    "goodbye",
    "got it",
    "sure",
    "yes",
    "no",
    "yep",
    "nope",
    "lol",
    "haha",
})

# When heuristics fall through to casual_chat, catch substantive asks without maintaining
# an exhaustive keyword list (LLM + these patterns handle the rest).
_LIFE_SIGNAL_RE = re.compile(
    r"\b("
    r"help\s+me|i\s+need|i\s+want|i\s+wish|i\s+feel|'?i'?m\s+|we\s+need|"
    r"should\s+i|how\s+do\s+i|what\s+should\s+i|can\s+you\s+help|"
    r"afraid|scared|worried|sad|angry|depressed|lonely|jealous|guilt|ashamed|"
    r"hurt|hurting|struggle|stuck|lost|confused|stress|anxious|overwhelm|"
    r"divorce|marriage|wedding|wife|husband|spouse|partner|affair|cheat|"
    r"boss|job|career|work|office|salary|fired|quit|money|debt|loan|rent|"
    r"legal|lawyer|laywer|court|custody|mother|father|parent|child|kids|family|"
    r"friend|enemy|addict|alcohol|smoke|drug|health|sleep|doctor|death|die|"
    r"kill|fight|abuse|attack|steal|greed|lust|ego|stubborn|hate"
    r")\b",
    re.IGNORECASE,
)
_FIRST_PERSON_RE = re.compile(
    r"\b(i|me|my|mine|myself|'?i'?m|'?i'?ve|'?i'?ll|we|us|our|ours)\b",
    re.IGNORECASE,
)
_KNOWLEDGE_LEAD_RE = re.compile(
    r"^\s*(what|why|how|who|when|where|which|define|describe|explain|compare|"
    r"contrast|is\s+it\s+true|list|name)\b",
    re.IGNORECASE,
)


def _heuristic_is_knowledge_question(lowered: str, text: str) -> bool:
    """Detect definitional / study questions without treating every 'what?' as knowledge.

    The old gate matched any of hundreds of substrings (e.g. ``what``) plus ``?``,
    which mislabeled almost all personal dilemmas as ``knowledge_question``.
    """
    norm = re.sub(r"\s+", " ", lowered.strip())
    if not norm:
        return False
    tokens = set(re.findall(r"[a-z]+", lowered))

    if tokens & _KNOWLEDGE_TOPIC_TOKENS:
        return True

    scripture_cue = bool(
        tokens
        & {
            "gita",
            "bhagavad",
            "krishna",
            "arjuna",
            "verse",
            "verses",
            "chapter",
            "sloka",
            "shloka",
        }
    )
    study_verbs = {
        "explain",
        "define",
        "describe",
        "compare",
        "contrast",
        "summarize",
        "summary",
        "teaching",
        "teaches",
        "taught",
    }
    if scripture_cue and (tokens & study_verbs):
        return True

    if _KNOWLEDGE_LEAD_RE.match(norm):
        return True

    word_count = len(norm.split())
    if "?" in text and 3 <= word_count <= 16 and not _FIRST_PERSON_RE.search(norm):
        return True
    return False


def _warrants_ambiguous_intent_refinement(text: str) -> bool:
    """Whether a message that failed earlier intent rules should be disambiguated."""
    stripped = str(text or "").strip()
    if len(stripped) < 8:
        return False
    norm = re.sub(r"\s+", " ", stripped.lower())
    tokens = norm.split()
    if len(tokens) < 3:
        return False
    if norm in _INTENT_TRIVIAL_ACK:
        return False
    return True


def _heuristic_resolve_ambiguous_casual(
    *,
    text: str,
    lowered: str,
    asks_for_context: bool,
    asks_for_simple_explanation: bool,
) -> IntentAnalysis | None:
    """Non-LLM fallback when the API key is missing or LLM refinement fails."""
    norm = re.sub(r"\s+", " ", lowered.strip())
    words = norm.split()
    life_hit = bool(_LIFE_SIGNAL_RE.search(norm) or _FIRST_PERSON_RE.search(norm))
    # Two-word cries for help ("help me", "i need") must still route to guidance +
    # retrieval; otherwise they become casual_chat with empty verses and the main
    # LLM habitually cites the same famous verse (e.g. 2.47).
    if life_hit and len(words) >= 2:
        return IntentAnalysis(
            intent_type="life_guidance",
            show_actions=True,
            show_reflection=True,
            show_related_verses=True,
            asks_for_application=True,
        )
    if len(words) >= 10:
        return IntentAnalysis(
            intent_type="life_guidance",
            show_actions=True,
            show_reflection=True,
            show_related_verses=True,
            asks_for_application=True,
        )
    knowledgeish = _heuristic_is_knowledge_question(lowered, text)
    if knowledgeish:
        if life_hit:
            return IntentAnalysis(
                intent_type="life_guidance",
                show_actions=True,
                show_reflection=True,
                show_related_verses=True,
                asks_for_application=True,
            )
        return IntentAnalysis(
            intent_type="knowledge_question",
            needs_retrieval=True,
            show_actions=False,
            show_reflection=False,
            show_related_verses=True,
            asks_for_context=asks_for_context,
            asks_for_simple_explanation=asks_for_simple_explanation,
        )
    return None


def _refine_intent_via_llm(
    message: str,
    *,
    asks_for_context: bool,
    asks_for_simple_explanation: bool,
) -> IntentAnalysis | None:
    """Use a small LLM call to separate life guidance from study chat from pure casual."""
    if not _llm_generation_enabled():
        return None
    if getattr(settings, "DISABLE_INTENT_LLM_REFINEMENT", False):
        return None
    max_in = int(getattr(settings, "MAX_ASK_INPUT_CHARS", 2200))
    clipped = str(message or "").strip()[:max_in]
    prompt = (
        "You route user messages for a Bhagavad Gita guidance app.\n"
        "Return ONLY valid JSON: "
        '{"intent_type":"life_guidance"|"knowledge_question"|"casual_chat",'
        '"reason":"one short phrase"}\n\n'
        "Definitions:\n"
        "- life_guidance: personal situations, emotions, relationships, work, money, "
        "health stress, ethical dilemmas, decisions, pain, anger, desire, family "
        "conflict, or any message mainly seeking support or practical wisdom "
        '(including "help me…", "should I…"). Include legal-adjacent life problems '
        "(classify here so the app can respond compassionately; it does not give "
        "legal advice).\n"
        "- knowledge_question: wants scripture/teaching explanation—definitions, "
        "verse/chapter meaning, concepts—without mainly venting a personal story.\n"
        "- casual_chat: thanks-only, hi-only, idle filler, meta about the app, or "
        "clearly off-topic with no sincere ask.\n\n"
        "User message:\n---\n"
        f"{clipped}\n---"
    )
    intent_model = getattr(settings, "OPENAI_INTENT_MODEL", "") or settings.OPENAI_MODEL
    timeout_seconds = float(getattr(settings, "OPENAI_INTENT_TIMEOUT_SECONDS", 8))
    try:
        out_text = _responses_output_text(
            model=intent_model,
            input_messages=[{"role": "user", "content": prompt}],
            max_output_tokens=int(
                getattr(settings, "INTENT_REFINEMENT_MAX_TOKENS", 120),
            ),
            timeout_seconds=timeout_seconds,
            json_mode=True,
        )
        payload = _parse_json_payload(out_text)
        it = str(payload.get("intent_type", "")).strip()
    except Exception as exc:
        logger.warning("Intent LLM refinement failed: %s", exc)
        return None

    if it == "life_guidance":
        return IntentAnalysis(
            intent_type="life_guidance",
            show_actions=True,
            show_reflection=True,
            show_related_verses=True,
            asks_for_application=True,
        )
    if it == "knowledge_question":
        return IntentAnalysis(
            intent_type="knowledge_question",
            needs_retrieval=True,
            show_actions=False,
            show_reflection=False,
            show_related_verses=True,
            asks_for_context=asks_for_context,
            asks_for_simple_explanation=asks_for_simple_explanation,
        )
    if it == "casual_chat":
        return IntentAnalysis(
            intent_type="casual_chat",
            needs_retrieval=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    return None


def _resolve_default_casual_intent(
    *,
    text: str,
    lowered: str,
    asks_for_context: bool,
    asks_for_simple_explanation: bool,
) -> IntentAnalysis:
    """Last-resort intent when earlier heuristics did not classify the message."""
    # Heuristic first: avoids an extra LLM round-trip when patterns already match
    # (e.g. "help me…", first-person, long messages, define/… questions).
    heur = _heuristic_resolve_ambiguous_casual(
        text=text,
        lowered=lowered,
        asks_for_context=asks_for_context,
        asks_for_simple_explanation=asks_for_simple_explanation,
    )
    if heur is not None:
        return heur
    if _warrants_ambiguous_intent_refinement(text):
        refined = _refine_intent_via_llm(
            message=text,
            asks_for_context=asks_for_context,
            asks_for_simple_explanation=asks_for_simple_explanation,
        )
        if refined is not None:
            return refined
    return IntentAnalysis(
        intent_type="casual_chat",
        needs_retrieval=False,
        show_actions=False,
        show_reflection=False,
        show_related_verses=False,
    )


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


def _is_short_gratitude_like(message: str) -> bool:
    """Thanks / closing lines that are not scripture questions (avoid ethics fallback)."""
    n = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not n:
        return False
    if n in _INTENT_TRIVIAL_ACK:
        return True
    tokens = re.findall(r"[a-z]+", n)
    gratitude_markers = frozenset({"thank", "thanks", "grateful", "blessed"})
    if not any(t in gratitude_markers for t in tokens):
        return False
    if len(tokens) > 14:
        return False
    # Real follow-up questions mixed with thanks should use normal guidance.
    if any(
        phrase in n
        for phrase in (
            "explain",
            "what does",
            "why did",
            "chapter",
            "verse",
            "shloka",
            "sloka",
            "mean ",
            "meaning ",
        )
    ):
        return False
    return True


def _extract_explicit_references(message: str) -> list[str]:
    """Return direct chapter.verse references mentioned in user text."""
    refs = []
    for chapter, verse in VERSE_REFERENCE_PATTERN.findall(str(message or "")):
        ref = f"{int(chapter)}.{int(verse)}"
        if ref not in refs:
            refs.append(ref)
    return refs


def _extract_chapter_number(message: str) -> int | None:
    """Return requested chapter number for chapter-summary questions."""
    match = re.search(r"\bchapter\s+(\d{1,2})\b", str(message or ""), re.IGNORECASE)
    if not match:
        return None
    chapter = int(match.group(1))
    if 1 <= chapter <= 18:
        return chapter
    return None


def classify_user_intent(message: str, *, mode: str = "simple") -> IntentAnalysis:
    """Classify the user input so answers match the request shape."""
    text = normalize_chat_user_message(str(message or "").strip())
    lowered = text.lower()
    refs = _extract_explicit_references(text)
    chapter_number = _extract_chapter_number(text)
    asks_for_application = any(
        phrase in lowered
        for phrase in _LIFE_APPLICATION_PHRASES
    )
    asks_for_context = any(
        phrase in lowered
        for phrase in {
            "why did krishna",
            "why krishna said",
            "context",
            "to arjuna",
            "when krishna said",
            "why did he say",
        }
    )
    asks_for_simple_explanation = any(
        phrase in lowered
        for phrase in {
            "simple language",
            "simple words",
            "simply explain",
            "easy language",
            "easy words",
        }
    )

    if _is_greeting_like(text):
        return IntentAnalysis(
            intent_type="greeting",
            needs_retrieval=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )

    if refs:
        return IntentAnalysis(
            intent_type="verse_explanation",
            explicit_references=refs,
            needs_retrieval=False,
            show_actions=asks_for_application or mode == "deep",
            show_reflection=asks_for_application and mode == "deep",
            show_related_verses=True,
            asks_for_application=asks_for_application,
            asks_for_context=asks_for_context,
            asks_for_simple_explanation=asks_for_simple_explanation,
        )

    if chapter_number and any(
        token in lowered for token in {"summary", "about", "teach", "teaches", "meaning", "explain"}
    ):
        return IntentAnalysis(
            intent_type="chapter_explanation",
            chapter_number=chapter_number,
            needs_retrieval=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
            asks_for_context=True,
        )

    if any(phrase in lowered for phrase in {"what can you do", "who are you", "help me use this app"}):
        return IntentAnalysis(
            intent_type="casual_chat",
            needs_retrieval=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )

    has_problem_shape = (
        any(word in lowered for word in PROBLEM_HINTS)
        or (" i " in f" {lowered} " and any(theme in lowered for theme in THEME_KEYWORDS))
    )
    if has_problem_shape:
        return IntentAnalysis(
            intent_type="life_guidance",
            show_actions=True,
            show_reflection=True,
            show_related_verses=True,
            asks_for_application=True,
        )

    if asks_for_application:
        return IntentAnalysis(
            intent_type="life_guidance",
            show_actions=True,
            show_reflection=True,
            show_related_verses=True,
            asks_for_application=True,
        )

    norm = re.sub(r"\s+", " ", lowered.strip())
    tokens = set(re.findall(r"[a-z]+", lowered))

    if _LIFE_SIGNAL_RE.search(norm):
        return IntentAnalysis(
            intent_type="life_guidance",
            show_actions=True,
            show_reflection=True,
            show_related_verses=True,
            asks_for_application=asks_for_application,
        )

    # First-person questions are usually dilemmas, not trivia — unless clearly scriptural.
    if _FIRST_PERSON_RE.search(norm) and "?" in text:
        if len(tokens & _KNOWLEDGE_TOPIC_TOKENS) < 2:
            return IntentAnalysis(
                intent_type="life_guidance",
                show_actions=True,
                show_reflection=True,
                show_related_verses=True,
                asks_for_application=asks_for_application,
            )

    if _heuristic_is_knowledge_question(lowered, text):
        return IntentAnalysis(
            intent_type="knowledge_question",
            needs_retrieval=True,
            show_actions=False,
            show_reflection=False,
            show_related_verses=True,
            asks_for_context=asks_for_context,
            asks_for_simple_explanation=asks_for_simple_explanation,
        )

    return _resolve_default_casual_intent(
        text=text,
        lowered=lowered,
        asks_for_context=asks_for_context,
        asks_for_simple_explanation=asks_for_simple_explanation,
    )


def empty_retrieval_result(
    *,
    intent: IntentAnalysis,
    query_interpretation: dict[str, object] | None = None,
    retrieval_mode: str = "none",
) -> RetrievalResult:
    """Return a trace object for non-retrieval answer paths."""
    return RetrievalResult(
        verses=[],
        retrieval_mode=retrieval_mode,
        query_themes=[],
        query_tokens=[],
        retrieval_scores=[],
        query_interpretation=query_interpretation or {
            "intent_type": intent.intent_type,
            "life_domain": "conversation",
            "match_strictness": "none",
            "confidence": 0.4,
        },
    )


def is_risky_prompt(message: str) -> bool:
    """Block crisis/medical/legal style prompts with keyword checks."""
    lowered = message.lower()
    return any(keyword in lowered for keyword in RISK_KEYWORDS)


def ensure_seed_verses() -> None:
    """Ensure default verse seed data exists for local/dev environments."""
    global _seed_synced
    # Tests roll back the DB between cases, but this module flag survives. If the
    # table is empty we must seed again even when _seed_synced is True.
    if not Verse.objects.exists():
        _seed_synced = False
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
    """Map a plain-language problem into a retrieval-friendly Gita framing.

    Result is cached by message content for 10 minutes — the function is
    deterministic and called up to 3 times per Ask pipeline for the same message.
    """
    _iq_key = "iq:" + hashlib.md5(message.encode("utf-8", errors="replace")).hexdigest()
    _cached = cache.get(_iq_key)
    if _cached is not None:
        return _cached
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
    elif "integrity" in themes:
        emotional_state = "conscientious"
        life_domain = "integrity and professional duty"
        likely_principles = [
            "truthfulness and steadiness in right action",
            "duty performed without attachment to gain or ego",
            "self-mastery so choices align with the higher good",
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
    result = QueryInterpretation(
        emotional_state=emotional_state,
        life_domain=life_domain,
        likely_principles=likely_principles,
        search_terms=search_terms[:10],
        match_strictness=match_strictness,
        confidence=confidence,
    )
    cache.set(_iq_key, result, 600)  # 10 min — deterministic so safe to cache
    return result


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


def get_related_verses(
    *,
    message: str,
    seed_verses: list[Verse],
    limit: int = 5,
) -> list[Verse]:
    """Return additional verses a user might want to explore next.

    Deterministic, fast, and safe for request-time use.
    """
    if limit <= 0:
        return []

    themes = infer_themes_from_text(message)
    # Broaden exploration using themes already present in the selected verses.
    for verse in seed_verses:
        themes.update(verse.themes or [])

    query_tokens = _tokenize(message)
    excluded = {_verse_reference(verse) for verse in seed_verses}

    candidates = Verse.objects.all()
    scored: list[tuple[int, Verse]] = []
    for verse in candidates:
        ref = _verse_reference(verse)
        if ref in excluded:
            continue
        score = _score_verse(verse=verse, themes=themes, query_tokens=query_tokens)
        if score <= 0:
            continue
        scored.append((score, verse))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [verse for _, verse in scored[:limit]]


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


def _parse_related_verse_references_from_llm(
    payload: dict,
    *,
    primary_refs: list[str],
) -> list[str] | None:
    """Parse optional LLM-chosen related verse refs; None means caller may use heuristics."""
    if "related_verse_references" not in payload:
        return None
    raw = payload.get("related_verse_references")
    if not isinstance(raw, list):
        return []
    primary_set = {str(p).strip() for p in primary_refs if p}
    seen: set[str] = set()
    candidates: list[str] = []
    for item in raw:
        s = str(item).strip()
        if not s or s in primary_set or s in seen:
            continue
        seen.add(s)
        candidates.append(s)
    verified = _fetch_verses_by_references(candidates[:8])
    return [f"{v.chapter}.{v.verse}" for v in verified]


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


# Module-level singleton so each gevent worker reuses one HTTP connection pool
# instead of opening a new pool on every request.  Protected by a lock so
# concurrent greenlets from the same worker do not race during first init.
_openai_client_lock = threading.Lock()
_openai_client_singleton: OpenAI | None = None
_openai_client_key: tuple | None = None  # (api_key, timeout) — recreate on change


def _openai_client() -> OpenAI:
    """Return a cached OpenAI client; recreate only when key/timeout changes."""
    global _openai_client_singleton, _openai_client_key
    timeout_seconds = float(getattr(settings, "OPENAI_REQUEST_TIMEOUT_SECONDS", 60))
    max_retries = int(getattr(settings, "OPENAI_MAX_RETRIES", 0))
    api_key = settings.OPENAI_API_KEY
    cache_key = (api_key, timeout_seconds, max_retries)
    if _openai_client_singleton is not None and _openai_client_key == cache_key:
        return _openai_client_singleton
    with _openai_client_lock:
        # Double-check after acquiring lock.
        if _openai_client_singleton is not None and _openai_client_key == cache_key:
            return _openai_client_singleton
        try:
            client = OpenAI(
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
        except TypeError:
            client = OpenAI(api_key=api_key)
        _openai_client_singleton = client
        _openai_client_key = cache_key
    return _openai_client_singleton


def _use_local_llm() -> bool:
    """When True, JSON/text guidance uses Ollama instead of OpenAI."""
    return bool(getattr(settings, "USE_LOCAL_LLM", False))


def _llm_generation_enabled() -> bool:
    """Enough config to run guidance-style LLM calls (cloud OpenAI or local Ollama)."""
    return _use_local_llm() or bool(getattr(settings, "OPENAI_API_KEY", ""))


def _ollama_client() -> OpenAI:
    """OpenAI-compatible client pointing at Ollama (typically :11434/v1)."""
    timeout_seconds = float(getattr(settings, "OPENAI_REQUEST_TIMEOUT_SECONDS", 120))
    max_retries = int(getattr(settings, "OPENAI_MAX_RETRIES", 0))
    base = (getattr(settings, "OLLAMA_BASE_URL", "") or "http://127.0.0.1:11434/v1").rstrip(
        "/",
    )
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    api_key = getattr(settings, "OLLAMA_API_KEY", None) or "ollama"
    try:
        return OpenAI(
            base_url=base,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
    except TypeError:
        return OpenAI(base_url=base, api_key=api_key)


def _effective_llm_model(requested_model: str | None) -> str:
    """Cloud uses ``requested_model`` (or OPENAI_MODEL); local uses ``OLLAMA_MODEL``."""
    if _use_local_llm():
        local = getattr(settings, "OLLAMA_MODEL", "").strip()
        return local or "gemma4:latest"
    chosen = (requested_model or "").strip()
    return chosen or settings.OPENAI_MODEL


def _responses_output_text(
    *,
    model: str,
    input_messages: list[dict[str, str]],
    max_output_tokens: int | None = None,
    timeout_seconds: float | None = None,
    json_mode: bool = False,
) -> str:
    """Responses API on OpenAI cloud, or chat.completions on local Ollama."""
    effective_model = _effective_llm_model(model)
    if _use_local_llm():
        client = _ollama_client()
        kwargs: dict[str, object] = {
            "model": effective_model,
            "messages": list(input_messages),
        }
        if max_output_tokens is not None:
            kwargs["max_tokens"] = max_output_tokens
        if timeout_seconds is not None:
            kwargs["timeout"] = timeout_seconds
        # Ollama: nudge toward valid JSON (fences are still stripped in _parse_json_payload).
        kwargs["extra_body"] = {"format": "json"}
        try:
            response = client.chat.completions.create(**kwargs)
        except TypeError:
            kwargs.pop("timeout", None)
            response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        return (message.content or "").strip()

    client = _openai_client()
    kwargs = {
        "model": effective_model,
        "input": input_messages,
    }
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if timeout_seconds is not None:
        kwargs["timeout"] = timeout_seconds
    if json_mode:
        kwargs["text"] = {"format": {"type": "json_object"}}
    try:
        response = client.responses.create(**kwargs)
    except TypeError:
        kwargs.pop("timeout", None)
        response = client.responses.create(**kwargs)
    except Exception:
        # Older API surfaces or model backends may reject text.format; retry once
        # without forcing JSON mode so call sites can still apply their fallback path.
        if json_mode:
            kwargs.pop("text", None)
            response = client.responses.create(**kwargs)
        else:
            raise
    return response.output_text


def verse_embedding_document(verse: Verse) -> str:
    """Single source of truth for text embedded per verse (DB JSON + pgvector sync).

    Kept in sync with ``embed_gita_verses`` / ``sync_pgvector_embeddings`` so
    query vectors and verse vectors live in the same semantic space.
    """
    themes = ", ".join(verse.themes) if verse.themes else "none"
    ref = f"{verse.chapter}.{verse.verse}"
    row = _merged_verse_context(ref)
    additional_angles = _additional_angle_text(ref, limit=3)
    commentary_text = _author_commentary_text(ref, limit=3)
    try:
        synthesis = VerseSynthesis.objects.filter(verse=verse).first()
    except (OperationalError, ProgrammingError):
        synthesis = None
    overview = (getattr(synthesis, "overview_en", "") or "").strip()
    consensus = (getattr(synthesis, "commentary_consensus_en", "") or "").strip()
    life_app = (getattr(synthesis, "life_application_en", "") or "").strip()
    life_snip = life_app[:520] if life_app else ""
    return (
        f"Bhagavad Gita {ref} — semantic retrieval document\n"
        f"Sanskrit: {row.get('sanskrit', '')}\n"
        f"Transliteration: {row.get('transliteration', '')}\n"
        f"Hindi Meaning: {row.get('hindi', '')}\n"
        f"English Meaning: {row.get('english', '')}\n"
        f"Word Meaning: {row.get('word_meaning', '')}\n"
        f"Additional Angles: {additional_angles}\n"
        f"Author Commentary Perspectives: {commentary_text}\n"
        f"Cached Verse Overview EN: {overview}\n"
        f"Cached Commentary Consensus EN: {consensus}\n"
        f"Cached Life Application EN (snippet for matching real-life asks): {life_snip}\n"
        f"Translation: {verse.translation}\n"
        f"Commentary: {verse.commentary}\n"
        f"Themes (for retrieval): {themes}"
    )


def _query_text_for_embedding(message: str) -> str:
    """Compose text for the query embedding so it aligns with verse documents."""
    max_chars = int(getattr(settings, "OPENAI_EMBEDDING_QUERY_MAX_CHARS", 8000))
    normalized = normalize_chat_user_message(message)
    if not getattr(settings, "OPENAI_QUERY_EMBEDDING_ENRICHED", True):
        return normalized[:max_chars]
    interp = interpret_query(normalized)
    themes = sorted(infer_themes_from_text(normalized))
    lines = [
        "Seeker message:",
        normalized,
        "",
        f"Life domain: {interp.life_domain}",
        f"Emotional tone: {interp.emotional_state}",
    ]
    if themes:
        lines.append(f"Themes: {', '.join(themes)}")
    lines.append(f"Guidance angles: {'; '.join(interp.likely_principles[:5])}")
    lines.append(f"Retrieval keywords: {', '.join(interp.search_terms)}")
    return "\n".join(lines)[:max_chars]


def query_embedding_input_text(message: str) -> str:
    """Public helper: text sent to the embeddings API for user-message retrieval."""
    return _query_text_for_embedding(message)


def _query_embedding_cache_key(input_text: str) -> str:
    """Stable cache key for query vectors (model + exact embedding input)."""
    digest = hashlib.sha256()
    digest.update(str(settings.OPENAI_EMBEDDING_MODEL).encode())
    digest.update(b"\0")
    digest.update(input_text.encode("utf-8"))
    return f"gita:qemb:v1:{digest.hexdigest()}"


def _query_embedding_cache_ttl_seconds() -> int | None:
    ttl = int(getattr(settings, "OPENAI_QUERY_EMBEDDING_CACHE_TTL_SECONDS", 86400))
    return ttl if ttl > 0 else None


def _openai_verse_relevance_model() -> str:
    """Model for verse relevance JSON (defaults to main chat model)."""
    alt = getattr(settings, "OPENAI_VERSE_RELEVANCE_MODEL", "").strip()
    return alt or settings.OPENAI_MODEL


def _openai_verse_suggest_model() -> str:
    """Model for empty-retrieval verse suggest JSON (defaults to main chat model)."""
    alt = getattr(settings, "OPENAI_VERSE_SUGGEST_MODEL", "").strip()
    return alt or settings.OPENAI_MODEL


def _build_query_embedding(message: str) -> list[float] | None:
    """Build embedding for user query; return None on any failure."""
    if not settings.OPENAI_API_KEY:
        return None
    input_text = _query_text_for_embedding(message)
    use_cache = bool(getattr(settings, "OPENAI_QUERY_EMBEDDING_CACHE_ENABLED", True))
    ttl = _query_embedding_cache_ttl_seconds()
    cache_key = _query_embedding_cache_key(input_text)
    if use_cache and ttl is not None:
        cached = cache.get(cache_key)
        if isinstance(cached, list) and cached:
            return cached
    try:
        client = _openai_client()
        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=input_text,
        )
        embedding = response.data[0].embedding
    except Exception as exc:
        logger.warning("Query embedding generation failed: %s", exc)
        return None
    if use_cache and ttl is not None and embedding:
        cache.set(cache_key, embedding, ttl)
    return embedding


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


def _get_all_verses_cached() -> list[Verse]:
    """Return all Gita verses from memory cache, loading once if needed."""
    global _verse_list_cache
    if _verse_list_cache is None:
        _verse_list_cache = list(Verse.objects.all())
    return _verse_list_cache


def retrieve_semantic_verses_with_trace(
    message: str,
    limit: int = 3,
) -> RetrievalResult:
    """Run semantic-only retrieval and expose non-success reasons."""
    ensure_seed_verses()
    themes = detect_themes(message)
    query_tokens = _tokenize(message)
    verses = _get_all_verses_cached()
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
    verses = _get_all_verses_cached()
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
    """Preferred retrieval strategy: semantic first, hybrid fallback.

    Semantic (embedding API) and hybrid (keyword, in-memory) retrieval run in
    parallel threads so the embedding round-trip does not block the cheaper
    heuristic pass.  Sparse retrieval is also launched in parallel.
    """
    import concurrent.futures

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

    # Fire all three retrieval strategies in parallel.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_semantic = executor.submit(
            retrieve_semantic_verses_with_trace,
            message=message,
            limit=candidate_limit,
        )
        f_hybrid = executor.submit(
            retrieve_hybrid_verses_with_trace,
            message=message,
            limit=candidate_limit,
        )
        f_sparse = executor.submit(
            _retrieve_sparse_verses_with_trace,
            message=message,
            limit=candidate_limit,
        )
        semantic = f_semantic.result()
        hybrid = f_hybrid.result()
        sparse = f_sparse.result()

    if semantic.retrieval_mode != "semantic":
        retrieval = hybrid
    else:
        # Keep whichever of semantic / hybrid has stronger local relevance.
        semantic_strength = _retrieval_strength(message=message, verses=semantic.verses)
        hybrid_strength = _retrieval_strength(message=message, verses=hybrid.verses)
        retrieval = hybrid if hybrid_strength > semantic_strength else semantic

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
    # English and Hinglish prompts use the same English chapter blurbs.
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
    global _merged_verse_context_cache
    reference = str(reference or "").strip()
    if not reference:
        return {}
    if _merged_verse_context_cache is None:
        _merged_verse_context_cache = {}
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
    tone: str = "classic",
) -> str:
    """Prepend primary verse quote in language-aware format."""
    ref, quote = _primary_verse_quote(verse=primary_verse, language=language)
    if not ref or not quote:
        return guidance

    is_plain = str(tone).lower().strip() == "plain"
    if language == "hi":
        prefix = (
            f"गीता {ref}: \"{quote}\""
            if is_plain
            else f"गीता {ref} में कृष्ण कहते हैं: \"{quote}\""
        )
    elif language == "hinglish":
        prefix = (
            f"Bhagavad Gita {ref}: \"{quote}\""
            if is_plain
            else (
                f"Bhagavad Gita {ref} mein Krishna kehte hain: \"{quote}\""
            )
        )
    else:
        prefix = (
            f"Bhagavad Gita {ref}: \"{quote}\""
            if is_plain
            else f"In Bhagavad Gita {ref}, Krishna says: \"{quote}\""
        )
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
    elif language == "hinglish":
        guidance = (
            "Dost, tumhare dil mein war, destruction aur death ka darr hai. "
            "Gita bilkul aisi hi battlefield par boli gayi — Kurukshetra — jahan "
            "Arjuna bhi waise hi freeze ho gaya tha. Krishna ne sabse pehle "
            "yeh sikhaya: atma na kabhi paida hoti hai na marti (2.20); shastra "
            "use kaat nahi sakte, agni jala nahi sakti (2.23). Sharir mortal hai, "
            "par tumhari sabse geheri reality destruction se pare hai. Krishna kehte "
            f"hain: Ma shuchah — despair mat karo (18.66). Dar ko apni wisdom par "
            f"hawi mat hone do. In verses se direction lo: {refs}."
        )
        meaning = (
            "Gita ke hisaab se destruction shuru hota hai weapons se nahi, mind ke "
            "andar — attachment, desire, anger, delusion ki chain se (2.62–63). "
            "Tumhare context mein: fear natural hai, par har fear truth nahi. "
            "Tumhara Self indestructible hai; abhi tumhara duty steady rehna, wisely "
            "protect karna, aur panic ke bajay clarity se act karna hai."
        )
        actions = [
            "Baitho, slow breath lo, aur khud se bolo: yeh dar guzar raha hai, main clarity se act karunga.",
            "Gita 2.20 aur 2.23 padho — Self ki immortality par thoda reflect karo.",
            "Sirf trustworthy news sources; doom-scroll mat karo — yeh fear cycle (2.62–63) ko feed karta hai.",
        ]
        reflection = (
            "Main imagined destruction mein toh nahi ji raha, ya is moment ko "
            "steadiness aur wisdom ke saath meet kar sakta hoon?"
        )
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


def _build_principle_only_fallback_guidance(
    message: str,
    *,
    language: str = "en",
) -> GuidanceResult:
    """Short Gita-grounded reply without citing specific verse numbers."""
    language = _normalize_language(language)
    intent = classify_user_intent(message)
    if language == "hi":
        return GuidanceResult(
            guidance=(
                "आपके प्रश्न की गहराई स्पष्ट है। भगवद्गीता सिखाती है कि सत्य, विवेक और "
                "भीतर की स्पष्टता के बिना कर्म भटक सकता है — परिणाम के भय या लोभ में "
                "निर्णय न करें। जटिल नैतिक या व्यावसायिक मामलों में विवेकी मानव मार्गदर्शन "
                "और अपने क्षेत्र के नियमों का सम्मान करें। यहाँ चिकित्सा या कानूनी सलाह नहीं दी जा रही।"
            ),
            meaning=(
                "गीता का केंद्र है: मोह से मुक्त होकर धर्म-संगत कर्तव्य की पहचान, "
                "और मन की स्थिरता।"
            ),
            actions=[
                "अपनी दुविधा को एक वाक्य में लिखें — क्या नैतिक रूप से सबसे महत्वपूर्ण बात क्या है?",
                "एक विश्वसनीय वरिष्ठ या मार्गदर्शक से मानवीय परामर्श लें (जहाँ लागू हो)।",
                "आज के लिए एक छोटा कदम चुनें जो सत्य और शांति दोनों की दिशा में हो।",
            ],
            reflection=(
                "क्या मैं स्पष्टता और करुणा दोनों के साथ अगला कदम चुन सकता हूँ?"
            ),
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_actions=intent.show_actions,
            show_reflection=intent.show_reflection,
            show_related_verses=False,
        )
    if language == "hinglish":
        return GuidanceResult(
            guidance=(
                "Tumhare sawal mein sach-much ek ethical tension hai. Bhagavad Gita "
                "sikhati hai: satya, clear discernment, aur steady action—bina iske "
                "ki fear, greed ya confusion tumhe slave bana de. Complex professional "
                "ya legal matters mein wise human mentors lo aur apne jurisdiction ke "
                "rules follow karo. Yeh medical ya legal advice nahi hai."
            ),
            meaning=(
                "Gita ka core yeh hai: clearly dekho, integrity se act karo, aur inner "
                "steadiness cultivate karo—reactive grasping ke bajay."
            ),
            actions=[
                "Apni dilemma ek sentence mein likho: abhi ethically sabse important kya hai?",
                "Trustworthy elder, teacher, ya professional advisor se consult karo jahan zaroori ho.",
                "Aaj ek chhota step chuno jo clarity aur peace ki taraf ho, integrity hurt kiye bina.",
            ],
            reflection=(
                "Ek dharmic next step main courage aur humility dono ke saath kaise le sakta hoon?"
            ),
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_actions=intent.show_actions,
            show_reflection=intent.show_reflection,
            show_related_verses=False,
        )
    return GuidanceResult(
        guidance=(
            "Your question points to a real ethical tension. The Bhagavad Gita teaches "
            "truthfulness, clear discernment, and steady action without being enslaved "
            "by fear, greed, or confusion. In complex professional or legal matters, seek "
            "wise human mentors and follow lawful rules in your jurisdiction. This is not "
            "medical or legal advice."
        ),
        meaning=(
            "The Gita's core is to see clearly, act with integrity, and cultivate inner "
            "steadiness rather than reactive grasping."
        ),
        actions=[
            "Write your dilemma in one sentence: what matters most ethically right now?",
            "Consult a trustworthy elder, teacher, or professional advisor where appropriate.",
            "Choose one small step today that moves toward clarity and peace without harming integrity.",
        ],
        reflection=(
            "What is one dharmic next step I can take with both courage and humility?"
        ),
        response_mode="fallback",
        intent_type=intent.intent_type,
        show_actions=intent.show_actions,
        show_reflection=intent.show_reflection,
        show_related_verses=False,
    )


def _build_fallback_guidance(
    message: str,
    verses: list[Verse],
    *,
    language: str = "en",
    honor_empty_verse_context: bool = False,
) -> GuidanceResult:
    """Create deterministic, safe guidance when LLM is unavailable."""
    language = _normalize_language(language)
    intent = classify_user_intent(message)
    # Gratitude / short acks must never hit the legal-ethics principle-only stub.
    if _is_short_gratitude_like(message):
        return _build_gratitude_ack_reply(language=language, intent=intent)
    if _is_greeting_like(message):
        return _build_compassionate_chat_reply(
            message,
            language=language,
            intent=intent,
        )

    if intent.intent_type == "casual_chat":
        return _build_compassionate_chat_reply(
            message,
            language=language,
            intent=intent,
        )

    # Verse-optional fallbacks used to always use the ethics template; restrict
    # that path to professional-role questions so other empty-retrieval cases get
    # normal verse-grounded or curated fallbacks below.
    if (
        honor_empty_verse_context
        and not verses
        and _is_professional_ethics_query(message)
    ):
        return _build_principle_only_fallback_guidance(message, language=language)

    if intent.intent_type == "knowledge_question" and verses:
        if _should_avoid_knowledge_fallback_template(message):
            return _build_principle_only_fallback_guidance(message, language=language)
        primary_verse = verses[0]
        ref = _verse_reference(primary_verse)
        detail = get_verse_detail(primary_verse.chapter, primary_verse.verse) or {}
        chapter_context = _chapter_perspective(
            chapter=primary_verse.chapter,
            language=language,
        )
        if language == "hi":
            return GuidanceResult(
                guidance=(
                    f"आपके प्रश्न के संदर्भ में {ref} सबसे प्रासंगिक श्लोकों में से है। "
                    f"कृष्ण ने यह बात अर्जुन से इसलिए कही क्योंकि {chapter_context}। "
                    "इसलिए उत्तर को केवल सलाह की तरह नहीं, बल्कि एक दार्शनिक "
                    "स्पष्टता की तरह समझना चाहिए।"
                ),
                meaning=(
                    f"{detail.get('translation', primary_verse.translation)} "
                    "इसका सार यह है कि गीता बाहरी घटना से अधिक भीतरी दृष्टि को बदलती है।"
                ).strip(),
                actions=[],
                reflection="",
                response_mode="fallback",
                intent_type=intent.intent_type,
                show_actions=False,
                show_reflection=False,
                show_related_verses=True,
            )
        if language == "hinglish":
            return GuidanceResult(
                guidance=(
                    f"Tumhare sawal ke liye {ref} sabse relevant verses mein se ek hai. "
                    f"Krishna ne yeh Arjuna se isliye kaha kyunki {chapter_context}. "
                    "Isliye answer ko pehle clarification ki tarah samjho—forced self-help "
                    "advice ki tarah nahi."
                ),
                meaning=(
                    f"{detail.get('translation', primary_verse.translation)} "
                    "Gehera point yeh hai ki Gita seeker ki way of seeing badalti hai—sirf "
                    "immediate mood par fix nahi."
                ).strip(),
                actions=[],
                reflection="",
                response_mode="fallback",
                intent_type=intent.intent_type,
                show_actions=False,
                show_reflection=False,
                show_related_verses=True,
            )
        return GuidanceResult(
            guidance=(
                f"For your question, {ref} is one of the most relevant verses. "
                f"Krishna says this to Arjuna because {chapter_context}. So the answer "
                "should be understood first as clarification, not as forced self-help advice."
            ),
            meaning=(
                f"{detail.get('translation', primary_verse.translation)} "
                "The deeper point is that the Gita changes the seeker's way of seeing, "
                "not just their immediate mood."
            ).strip(),
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_actions=False,
            show_reflection=False,
            show_related_verses=True,
        )

    # Principle-only disclaimer: legal/professional-role stressors. Do not use
    # the broad life-signal heuristic here — it matches normal emotions (e.g.
    # anger) and skipped verse-grounded fallbacks when the LLM was unavailable.
    if (
        intent.intent_type == "life_guidance"
        and _is_professional_ethics_query(message)
    ):
        return _build_principle_only_fallback_guidance(message, language=language)

    if intent.intent_type == "knowledge_question" and not verses:
        ensure_seed_verses()
        filled = _curated_fallback_verses(message=message, limit=3)
        if not filled:
            filled = list(Verse.objects.order_by("chapter", "verse")[:3])
        if filled:
            return _build_fallback_guidance(message, filled, language=language)

    ensure_seed_verses()
    if not verses:
        verses = _curated_fallback_verses(message=message, limit=3)
    if not verses:
        verses = list(Verse.objects.order_by("chapter", "verse")[:3])

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
    elif language == "hinglish":
        guidance = (
            f"Tumhare exact sawal '{message}' ke liye {primary_ref} ki teaching bahut relevant hai. "
            f"Krishna ne yeh Arjuna se isliye kaha kyunki {chapter_context}. "
            "Wahi principle tumhari situation par bhi lagta hai: pehle confusion ya pain "
            "ka asli source pehchano, phir abhi ek clear, dharmic next action chuno—outcomes "
            f"ke dar mein phase karne ke bajay. In verses se direction lo: {refs}."
        )
        meaning = (
            "Yeh teaching dikhati hai Krishna ne Arjuna ko emotional confusion se nikaal kar "
            "right action ki taraf kaise guide kiya. Tumhare context mein matlab: fear, "
            "attachment, ya agitation ko tumhare decision-maker mat banne do."
        )
        actions = [
            f"Apni dilemma ek sentence mein likho: '{message}'.",
            "Agle 24 ghante mein ek concrete step chuno aur use poora karo.",
            "Action ke baad calmly review karo: kya is step ne clarity, steadiness, integrity badhayi?",
        ]
        reflection = (
            "Aaj meri exact situation ke liye sabse dharmic aur practical next action kya hai?"
        )
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
        intent_type=intent.intent_type,
        show_actions=intent.show_actions,
        show_reflection=intent.show_reflection,
        show_related_verses=intent.show_related_verses,
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

    max_turns = int(getattr(settings, "MAX_CONVERSATION_CONTEXT_TURNS", 6))
    max_chars = int(getattr(settings, "MAX_CONVERSATION_CONTEXT_CHARS", 4000))
    if max_turns <= 0:
        return ""
    recent = conversation_messages[-max_turns:]

    lines = []
    for message in recent:
        role = getattr(message, "role", "")
        content = getattr(message, "content", "")
        if not content:
            continue
        speaker = "User" if role == "user" else "Guide"
        lines.append(f"{speaker}: {content}")
    text = "\n".join(lines)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    parts = text.split("\n")
    while len(parts) > 1 and len("\n".join(parts)) > max_chars:
        parts.pop(0)
    trimmed = "\n".join(parts)
    if len(trimmed) > max_chars:
        trimmed = trimmed[-max_chars:].lstrip()
    return trimmed


def _is_minimal_context_life_message(message: str) -> bool:
    """Detect very short generic pleas so prompts can avoid repetitive default verses."""
    norm = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if len(norm.split()) > 6:
        return False
    return bool(
        re.match(
            r"^(help(\s+me|\s+us)?|please\s+help|need\s+help|i\s+need\s+help|"
            r"someone\s+help|support\s+me|save\s+me)\s*!*\??$",
            norm,
        )
    )


def _extract_references(text: str) -> set[str]:
    """Extract chapter.verse references from free-form text."""
    return set(re.findall(r"\b\d{1,2}\.\d{1,3}\b", text))


def _strip_markdown_json_fence(text: str) -> str:
    """Remove ``` or ```json fences that local models often wrap JSON in."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_payload(output_text: str) -> dict:
    """Parse model output to JSON, tolerating prose/markdown fences and nesting."""
    raw = (output_text or "").strip().replace("\ufeff", "")
    layered = [_strip_markdown_json_fence(raw), raw]

    decoder = json.JSONDecoder()
    for blob in layered:
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = 0
        while True:
            idx = blob.find("{", start)
            if idx == -1:
                break
            try:
                parsed, _end = decoder.raw_decode(blob, idx)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            start = idx + 1

    raise ValueError("No JSON object found in model output.")


def _is_grounded_response(
    guidance: str,
    meaning: str,
    references: list[str],
    allowed_references: set[str],
    *,
    verse_optional: bool = False,
) -> bool:
    """Validate that cited references are within retrieved context.

    When ``verse_optional`` is True and the model returns no ``verse_references``,
    the answer must not smuggle chapter.verse numbers into prose (anti-hallucination).
    """
    normalized_refs = {ref.strip() for ref in references if ref.strip()}
    text_refs = _extract_references(f"{guidance} {meaning}")
    if verse_optional and not normalized_refs:
        return not bool(text_refs)
    if not normalized_refs:
        return False
    all_refs = normalized_refs | text_refs
    return bool(all_refs) and all_refs.issubset(allowed_references)


def _user_seeks_personal_action_or_ethics(message: str) -> bool:
    """True when the user asks what to do / how it applies to them (aligns with intent)."""
    lowered = re.sub(r"\s+", " ", str(message or "").strip().lower())
    return any(phrase in lowered for phrase in _LIFE_APPLICATION_PHRASES)


def _should_avoid_knowledge_fallback_template(message: str) -> bool:
    """When the LLM is off, skip the generic 'verse X is most relevant' knowledge stub."""
    lowered = re.sub(r"\s+", " ", str(message or "").strip().lower())
    text = str(message or "").strip()
    if _user_seeks_personal_action_or_ethics(message):
        return True
    if _is_professional_ethics_query(message):
        return True
    if _LIFE_SIGNAL_RE.search(lowered):
        return True
    tokens = set(re.findall(r"[a-z]+", lowered))
    if _FIRST_PERSON_RE.search(lowered) and "?" in text:
        return len(tokens & _KNOWLEDGE_TOPIC_TOKENS) < 2
    return False


def normalize_chat_user_message(message: str) -> str:
    """Strip accidental leading ``You `` from pasted SEO/UI copy (e.g. ``You i am…``)."""
    s = str(message or "").strip()
    if not s:
        return s
    prefix = s[:16].lower()
    if prefix.startswith("you i ") or prefix.startswith("you we "):
        return s[4:].lstrip()
    if re.match(r"^you\s+i['’]", s, re.IGNORECASE):
        return re.sub(r"^you\s+", "", s, count=1, flags=re.IGNORECASE).lstrip()
    return s


def _is_professional_ethics_query(message: str) -> bool:
    """Heuristic: legal/professional-role stress (not legal advice — prompt disclaimer).

    Kept intentionally **narrow**. Broad substring matches previously misfired:
    - ``"counsel"`` matches inside ``counselling`` / counselor words.
    - Bare ``clients`` matches freelancers, therapists, designers, etc.
    - ``fighting for`` matches non-legal struggle; pair with legal cues.
    - ``my case`` matches the idiom ``in my case`` (unrelated to courts).
    """
    n = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not n:
        return False

    phrase_needles = (
        "lawyer",
        "laywer",
        "attorney",
        "bar council",
        "law firm",
        "legal ethics",
        "legal advice",
        "represent a client",
        "representing a client",
        "defend someone",
        "defending someone",
        "court case",
        "litigation",
        "plaintiff",
        "defendant",
        "whose case",
    )
    if any(p in n for p in phrase_needles):
        return True

    # Standalone word — substring "counsel" must NOT match inside "counselling".
    if re.search(r"\bcounsel\b", n):
        return True

    # "fighting for" alone is too broad (family, health, ideals). Require legal-ish
    # context similar to the lawyer / court ethical-conflict scenarios we test.
    if "fighting for" in n and any(
        k in n
        for k in (
            "case",
            "court",
            "client",
            "lawyer",
            "laywer",
            "attorney",
            "legal",
            "trial",
            "lawsuit",
            "litigation",
            "innocent",
            "guilty",
            "defendant",
            "plaintiff",
            "witness",
            "evidence",
        )
    ):
        return True

    # Skip the English idiom "in my case, ..." (not a lawsuit).
    if re.search(r"\bmy case\b", n) and not re.search(r"\bin my case\b", n):
        return True

    # "Client(s)" appears in many professions — only flag with legal/court cues.
    if re.search(r"\bclients?\b", n):
        legal_cues = (
            "lawyer",
            "laywer",
            "attorney",
            "legal",
            "court",
            "litigation",
            "lawsuit",
            "plaintiff",
            "defendant",
            "trial",
            "judge",
            "jurisdiction",
            "testimony",
            "evidence",
            "appeal",
            "barrister",
            "solicitor",
            "subpoena",
            "affidavit",
            "arraignment",
            "prosecut",
            "defense counsel",
            "district attorney",
        )
        if any(c in n for c in legal_cues):
            return True

    return False


# Verses that catalogue demoniacal nature / destruction — never map to clients or parties.
_LEGAL_ETHICS_VERSE_DROP_REFS = frozenset({
    "16.7",
    "16.8",
    "16.9",
    "16.10",
    "16.11",
    "16.12",
    "16.13",
    "16.14",
    "16.15",
    "16.16",
    "16.17",
    "16.18",
})


def _strip_inappropriate_verses_for_legal_ethics(
    message: str,
    verses: list[Verse],
) -> list[Verse]:
    """Remove ślokas that are easily misread as labeling people in advocacy ethics asks."""
    if not verses or not _is_professional_ethics_query(message):
        return verses
    ref_set = {f"{v.chapter}.{v.verse}" for v in verses}
    if not ref_set & _LEGAL_ETHICS_VERSE_DROP_REFS:
        return verses
    kept = [
        v for v in verses
        if f"{v.chapter}.{v.verse}" not in _LEGAL_ETHICS_VERSE_DROP_REFS
    ]
    return kept


def _validate_and_correct_verses(
    message: str,
    verses: list[Verse],
) -> list[Verse]:
    """Ask LLM whether retrieved verses fit the question (uses commentary + translation).

    Returns:
    - Same list when verses are relevant or on failure (graceful degradation).
    - A replaced list when ``better_refs`` load from DB.
    - An empty list when the model sets ``no_appropriate_verse`` (do not cite ślokas).
    """
    if not _llm_generation_enabled() or not verses:
        return verses

    blocks = []
    for v in verses[:6]:
        ref = _verse_reference(v)
        comm = _author_commentary_text(ref, limit=4, message=message)
        angles = _additional_angle_text(ref, limit=2)
        row = _merged_verse_context(ref)
        eng_mean = str(row.get("english", "") or "")[:220]
        blocks.append(
            f"--- {ref} ---\n"
            f"Translation (excerpt): {v.translation[:320]}\n"
            f"English meaning (excerpt): {eng_mean}\n"
            f"Additional angles (excerpt): {angles[:420]}\n"
            f"Author commentary (query-ranked excerpts): {comm[:720]}\n"
        )
    verses_text = "\n".join(blocks)

    legal_ethics_extra = ""
    if _is_professional_ethics_query(message):
        legal_ethics_extra = (
            "\nLEGAL / ADVOCACY ETHICS (user may be a lawyer or officer of the court):\n"
            "- NEVER treat verses that describe demoniacal nature, 'enemies of the "
            "world', ruin, or destruction as if they referred to clients, opponents, "
            "or parties in a case. Reject candidates in that category.\n"
            "- Prefer satya, measured speech, inner clarity, or verse-free principles "
            "(no_appropriate_verse) over any śloka that could insult a person.\n"
            "- When in doubt, choose {\"relevant\": false, \"no_appropriate_verse\": true}.\n"
        )

    prompt = (
        "You are a Bhagavad Gita verse-relevance evaluator. You have translation, "
        "meaning, angles, and classical/modern commentary excerpts so you can judge "
        "fit beyond surface keywords.\n\n"
        f"User question:\n{message}\n\n"
        f"Candidate verses (with commentary context):\n{verses_text}\n\n"
        "Rules:\n"
        "- Do NOT map Kurukshetra battlefield 'duty' to modern professional/legal "
        "rules unless the user clearly asks in that metaphorical spirit; for legal "
        "ethics, prefer teachings on truthfulness, discernment, non-harm to integrity, "
        "and humility rather than warrior-role verses.\n"
        f"{legal_ethics_extra}"
        "- If at least one candidate truly fits the user's concern, respond with "
        "EXACTLY: {\"relevant\": true}\n"
        "- If none fit but you can name better chapter.verse refs that would fit, "
        "respond: {\"relevant\": false, \"better_refs\": [\"chapter.verse\", ...]} "
        "(2-5 refs, Bhagavad Gita chapters 1-18 only).\n"
        "- If no single śloka should be cited (question too narrow, mismatched, or "
        "only general principles apply), respond: "
        "{\"relevant\": false, \"no_appropriate_verse\": true}\n"
        "  In that case omit better_refs or set it to [].\n\n"
        "Return ONLY JSON, no other text."
    )
    json_tokens = int(getattr(settings, "OPENAI_JSON_TASK_MAX_OUTPUT_TOKENS", 160))
    timeout_seconds = float(
        getattr(settings, "OPENAI_VERSE_RELEVANCE_TIMEOUT_SECONDS", 10),
    )

    try:
        out_text = _responses_output_text(
            model=_openai_verse_relevance_model(),
            input_messages=[{"role": "user", "content": prompt}],
            max_output_tokens=json_tokens,
            timeout_seconds=timeout_seconds,
            json_mode=True,
        )
        payload = _parse_json_payload(out_text)

        if payload.get("relevant", True):
            return verses

        if payload.get("no_appropriate_verse"):
            logger.info(
                "Verse relevance: no appropriate verse for query: %s",
                message[:120],
            )
            return []

        better_refs = payload.get("better_refs", [])
        if not isinstance(better_refs, list) or not better_refs:
            return verses

        sanitised = [
            ref for ref in better_refs
            if isinstance(ref, str) and _parse_reference(ref.strip())
        ][:5]
        if _is_professional_ethics_query(message):
            sanitised = [
                ref for ref in sanitised
                if ref.strip() not in _LEGAL_ETHICS_VERSE_DROP_REFS
            ]

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


def _suggest_verse_refs_llm(message: str) -> list[Verse]:
    """Second-pass: propose a few refs when retrieval/relevance left none."""
    if not _llm_generation_enabled():
        return []

    legal_extra = ""
    if _is_professional_ethics_query(message):
        legal_extra = (
            "This may involve legal advocacy: do NOT suggest verses from the "
            "demoniacal catalogue (Bhagavad Gita chapter 16.7–16.18) or any line that "
            "could be read as labeling clients or parties. Prefer [] or speech/truth "
            "verses (e.g. 17.15) only if clearly helpful.\n\n"
        )
    prompt = (
        "You suggest Bhagavad Gita chapter.verse references for a seeker's question.\n"
        "Use thematic knowledge (truthfulness, disciplined action, inner steadiness, "
        "discernment, humility). Do not treat Kurukshetra combat duty as direct advice "
        "for modern professional ethics unless the question is clearly spiritual.\n\n"
        f"{legal_extra}"
        f"Question:\n{message}\n\n"
        "Return ONLY JSON: {\"refs\": [\"2.47\", \"16.1\", ...]} with 1-4 refs, or "
        "{\"refs\": []} if general principles without numbered verses are better.\n"
        "Only chapters 1-18."
    )
    json_tokens = int(getattr(settings, "OPENAI_JSON_TASK_MAX_OUTPUT_TOKENS", 160))
    timeout_seconds = float(
        getattr(settings, "OPENAI_VERSE_SUGGEST_TIMEOUT_SECONDS", 10),
    )
    try:
        out_text = _responses_output_text(
            model=_openai_verse_suggest_model(),
            input_messages=[{"role": "user", "content": prompt}],
            max_output_tokens=json_tokens,
            timeout_seconds=timeout_seconds,
            json_mode=True,
        )
        payload = _parse_json_payload(out_text)
        raw = payload.get("refs", [])
        if not isinstance(raw, list):
            return []
        sanitised = [
            r for r in raw
            if isinstance(r, str) and _parse_reference(r.strip())
        ][:4]
        if _is_professional_ethics_query(message):
            sanitised = [
                r for r in sanitised
                if r.strip() not in _LEGAL_ETHICS_VERSE_DROP_REFS
            ]
        if not sanitised:
            return []
        got = _fetch_verses_by_references(sanitised)
        if got:
            logger.info(
                "Verse suggest LLM: proposed [%s] for: %s",
                ", ".join(f"{v.chapter}.{v.verse}" for v in got),
                message[:80],
            )
        return got
    except Exception as exc:
        logger.warning("Verse suggest LLM failed: %s", exc)
        return []


def refine_verses_for_guidance(message: str, verses: list[Verse]) -> list[Verse]:
    """Post-retrieval: commentary-aware relevance pass; optional verse suggest if empty."""
    message = normalize_chat_user_message(str(message or "").strip())
    out: list[Verse] = list(verses)
    out = _strip_inappropriate_verses_for_legal_ethics(message, out)

    if not _llm_generation_enabled():
        return out

    refined: list[Verse] = list(out)
    if refined and not getattr(settings, "DISABLE_VERSE_RELEVANCE_LLM", False):
        refined = _validate_and_correct_verses(message, refined)

    refined = _strip_inappropriate_verses_for_legal_ethics(message, refined)

    if refined:
        return refined

    if getattr(settings, "DISABLE_LLM_VERSE_SUGGEST_WHEN_EMPTY", False):
        return refined

    suggested = _suggest_verse_refs_llm(message)
    suggested = _strip_inappropriate_verses_for_legal_ethics(message, suggested)
    return suggested if suggested else refined


def _trim_actions(actions: object, *, limit: int = 3) -> list[str]:
    """Normalize optional action items returned by the model."""
    if not isinstance(actions, list):
        return []
    return [
        str(action).strip()
        for action in actions
        if str(action).strip()
    ][:limit]


def _build_gratitude_ack_reply(
    *,
    language: str,
    intent: IntentAnalysis,
) -> GuidanceResult:
    """Short acknowledgment for thanks-only messages (not the legal-ethics fallback)."""
    language = _normalize_language(language)
    if language == "hi":
        guidance = (
            "आपका धन्यवाद। यदि मन में कोई और प्रश्न उठे—चाहे छोटा हो या भारी—"
            "आप यहाँ फिर से पूछ सकते हैं। शांति के साथ अपना मार्ग जारी रखें।"
        )
    elif language == "hinglish":
        guidance = (
            "Thank you—dil se. Agar aur koi sawal ho, chhota ho ya bada, yahan "
            "wapas pooch sakte ho. Apna raasta shaanti ke saath chalate raho."
        )
    else:
        guidance = (
            "You’re welcome—truly. If another question arises, small or heavy, "
            "you can ask again here. May you walk your path with steadiness."
        )
    return GuidanceResult(
        guidance=guidance,
        meaning="",
        actions=[],
        reflection="",
        response_mode="fallback",
        intent_type=intent.intent_type,
        show_meaning=False,
        show_actions=False,
        show_reflection=False,
        show_related_verses=False,
    )


def _build_compassionate_chat_reply(
    message: str,
    *,
    language: str,
    intent: IntentAnalysis,
) -> GuidanceResult:
    """Return a warm, non-forced reply for greetings and casual chat."""
    if _is_short_gratitude_like(message):
        return _build_gratitude_ack_reply(language=language, intent=intent)
    if language == "hi":
        if intent.intent_type == "greeting":
            return GuidanceResult(
                guidance=(
                    "नमस्ते। मैं यहाँ शांत मन से आपकी बात सुनने और भगवद्गीता के "
                    "प्रकाश में उत्तर देने के लिए हूँ।"
                ),
                meaning="",
                actions=[],
                reflection="",
                response_mode="fallback",
                intent_type=intent.intent_type,
                show_meaning=False,
                show_actions=False,
                show_reflection=False,
                show_related_verses=False,
            )
        return GuidanceResult(
            guidance=(
                "मैं आपकी बात उसी रूप में उत्तर दूँगा जैसी आपने पूछी है। यदि प्रश्न "
                "गीता, कृष्ण, अर्जुन, किसी श्लोक, या जीवन-संदर्भ से जुड़ा होगा, तो "
                "मैं उसी के अनुसार सरल और स्नेहपूर्ण उत्तर दूँगा।"
            ),
            meaning="",
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_meaning=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    if language == "hinglish":
        if intent.intent_type == "greeting":
            return GuidanceResult(
                guidance=(
                    "Namaste. Main yahan hoon tumhe Bhagavad Gita ki roshni mein "
                    "aram se aur seedha jawab dene ke liye—bina zabardasti ke."
                ),
                meaning="",
                actions=[],
                reflection="",
                response_mode="fallback",
                intent_type=intent.intent_type,
                show_meaning=False,
                show_actions=False,
                show_reflection=False,
                show_related_verses=False,
            )
        return GuidanceResult(
            guidance=(
                "Main tumhari baat waise hi jawab dunga jaise tumne puchi hai. "
                "Agar tum scripture ya life guidance chahte ho, toh usi hisaab se "
                "practical aur dayalu jawab milega—Gita ke spirit mein."
            ),
            meaning="",
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_meaning=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    if intent.intent_type == "greeting":
        return GuidanceResult(
            guidance=(
                "Hello. I’m here to answer you gently and clearly in the light "
                "of the Bhagavad Gita, without forcing your question into advice "
                "if that is not what you asked."
            ),
            meaning="",
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_meaning=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    return GuidanceResult(
        guidance=(
            "I’ll answer your question as it was asked. If you want scripture "
            "explanation, I’ll explain it. If you want life guidance, I’ll make it "
            "practical and compassionate in the spirit of the Bhagavad Gita."
        ),
        meaning="",
        actions=[],
        reflection="",
        response_mode="fallback",
        intent_type=intent.intent_type,
        show_meaning=False,
        show_actions=False,
        show_reflection=False,
        show_related_verses=False,
    )


def _supporting_verses_for_reference(reference: str) -> list[Verse]:
    """Return a small support set for exact-verse explanation questions."""
    parsed = _parse_reference(reference)
    if not parsed:
        return []
    chapter, verse_no = parsed
    seed = Verse.objects.filter(chapter=chapter, verse=verse_no).first()
    if seed is None:
        return []
    support = [seed]
    for verse in get_related_verses(message=reference, seed_verses=[seed], limit=4):
        if all(_verse_reference(existing) != _verse_reference(verse) for existing in support):
            support.append(verse)
    return support[:4]


def _build_fallback_verse_explanation(
    *,
    message: str,
    verse: Verse,
    support_verses: list[Verse],
    language: str,
    intent: IntentAnalysis,
) -> GuidanceResult:
    """Create a deterministic exact-verse explanation when LLM is unavailable."""
    ref = _verse_reference(verse)
    detail = get_verse_detail(verse.chapter, verse.verse) or {}
    synthesis = get_or_create_verse_synthesis(verse)
    chapter_context = _chapter_perspective(chapter=verse.chapter, language=language)
    commentary_entries = detail.get("commentaries", []) if isinstance(detail, dict) else []
    commentary_summary = ", ".join(
        str(item.get("author", "")).strip()
        for item in commentary_entries[:3]
        if str(item.get("author", "")).strip()
    )
    support_refs = [_verse_reference(item) for item in support_verses if _verse_reference(item) != ref][:3]
    if language == "hi":
        guidance = (
            f"भगवद्गीता {ref} का सरल अर्थ यह है कि कृष्ण अर्जुन को कर्म पर टिकना "
            "सिखा रहे हैं, फल पर नहीं। उन्होंने यह बात इसलिए कही क्योंकि "
            f"{chapter_context}। यह श्लोक अर्जुन के मोह को शांत करके उसे "
            "कर्तव्य की स्पष्टता देना चाहता है।"
        )
        meaning = (
            f"मुख्य संदेश: {detail.get('translation', verse.translation)} "
            f"{synthesis.get('commentary_consensus_hi', '')}".strip()
        )
        if commentary_summary:
            meaning = (
                f"{meaning} उपलब्ध प्रसिद्ध टीकाकारों के दृष्टिकोण में भी यही बात "
                "उभरती है कि यह श्लोक आसक्ति छोड़कर सजग कर्म की शिक्षा देता है।"
            ).strip()
        actions = []
        reflection = ""
        if intent.asks_for_application:
            actions = [
                "आज एक ऐसा काम चुनिए जिसे आप ईमानदारी से कर सकते हैं, बिना परिणाम के भय में फँसे।",
                "अपने मन से पूछिए: मैं अभी कर्म पर केंद्रित हूँ या फल की चिंता पर?",
            ]
            reflection = "मेरे जीवन में कहाँ परिणाम-चिंता मुझे सही कर्म से दूर ले जाती है?"
        return GuidanceResult(
            guidance=guidance,
            meaning=meaning,
            actions=actions,
            reflection=reflection,
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_actions=bool(actions),
            show_reflection=bool(reflection),
            show_related_verses=bool(support_refs),
        )
    if language == "hinglish":
        tr = detail.get("translation", verse.translation)
        guidance = (
            f"Bhagavad Gita {ref} mein Krishna Arjuna ko yeh sikha rahe hain ki "
            f"sahi karma par tikna hai, result par emotional ownership nahi. "
            f"Unhone yeh isliye kaha kyunki {chapter_context}. Yeh shloka Arjuna "
            "ke mann ko steady karna chahta hai taaki woh attachment ya fear mein "
            "collapse na karein."
        )
        meaning = (
            f"Seedha matlab: {tr} "
            f"{synthesis.get('commentary_consensus_en', '')}".strip()
        )
        if commentary_summary:
            meaning = (
                f"{meaning} Bade commentaries bhi yahi stress karte hain: disciplined "
                "action, inner steadiness, aur outcome par possessiveness chhodna."
            ).strip()
        actions = []
        reflection = ""
        if intent.asks_for_application:
            actions = [
                "Aaj ek kaam chuno jo tum sincerely kar sako—bina result ke saath deal "
                "karne ke pressure ke.",
                "Jab outcome ki anxiety aaye, yaad karo: mera kaam effort aur clarity "
                "hai, fruit ka owner main nahi hoon.",
            ]
            reflection = (
                "Meri life mein kahan result ka dar meri action ki quality kharab kar "
                "raha hai?"
            )
        return GuidanceResult(
            guidance=guidance,
            meaning=meaning,
            actions=actions,
            reflection=reflection,
            response_mode="fallback",
            intent_type=intent.intent_type,
            show_actions=bool(actions),
            show_reflection=bool(reflection),
            show_related_verses=bool(support_refs),
        )
    guidance = (
        f"Bhagavad Gita {ref} is Krishna teaching Arjuna to stay rooted in right "
        f"action rather than becoming emotionally owned by the result. He says this "
        f"because {chapter_context}. The verse is meant to steady Arjuna's mind so "
        "he can act clearly instead of collapsing into attachment, fear, or paralysis."
    )
    meaning = (
        f"Simple meaning: {detail.get('translation', verse.translation)} "
        f"{synthesis.get('commentary_consensus_en', '')}".strip()
    )
    if commentary_summary:
        meaning = (
            f"{meaning} Across major commentarial traditions, the shared emphasis is "
            "on disciplined action, inner steadiness, and freedom from possessiveness "
            "about outcomes."
        ).strip()
    actions = []
    reflection = ""
    if intent.asks_for_application:
        actions = [
            "Choose one duty in front of you today and do it sincerely without mentally bargaining over the result.",
            "When anxiety about outcome rises, remind yourself: my work is effort and clarity, not ownership of the fruit.",
        ]
        reflection = (
            "Where in my present life am I letting fear of results disturb the quality of my action?"
        )
    return GuidanceResult(
        guidance=guidance,
        meaning=meaning,
        actions=actions,
        reflection=reflection,
        response_mode="fallback",
        intent_type=intent.intent_type,
        show_actions=bool(actions),
        show_reflection=bool(reflection),
        show_related_verses=bool(support_refs),
    )


def build_verse_explanation(
    *,
    message: str,
    verse: Verse,
    support_verses: list[Verse],
    language: str = "en",
    mode: str = "simple",
    conversation_messages=None,
    max_output_tokens: int = 350,
    intent: IntentAnalysis | None = None,
) -> GuidanceResult:
    """Explain a specific verse directly, with context and selective application."""
    language = _normalize_language(language)
    intent = intent or IntentAnalysis(intent_type="verse_explanation", explicit_references=[_verse_reference(verse)])
    detail = get_verse_detail(verse.chapter, verse.verse) or {}
    chapter_context = _chapter_perspective(chapter=verse.chapter, language=language)
    synthesis = get_or_create_verse_synthesis(verse)
    commentary_entries = detail.get("commentaries", []) if isinstance(detail, dict) else []
    commentary_text = "\n".join(
        f"- {item.get('author', '').strip()}: {str(item.get('text', '')).strip()[:240]}"
        for item in commentary_entries[:5]
        if str(item.get("author", "")).strip() and str(item.get("text", "")).strip()
    )
    support_text = _serialize_verses_for_prompt(support_verses, message=message)
    conversation_context = _serialize_conversation_context(conversation_messages)
    ref = _verse_reference(verse)
    if not _llm_generation_enabled():
        return _build_fallback_verse_explanation(
            message=message,
            verse=verse,
            support_verses=support_verses,
            language=language,
            intent=intent,
        )

    system_prompt = (
        "You are a deeply compassionate Bhagavad Gita teacher—voice of a loving "
        "parent or creator with a beloved child. Return valid JSON only with keys: "
        "guidance, meaning, actions, reflection, verse_references. "
        "Answer exactly what was asked; no filler, no unrelated domains. "
        "AUDIENCE: Write so teenagers, elders, and non-specialists all understand—"
        "soft, patient, emotionally intelligent; plain words before Sanskrit; define "
        "any technical term in one short phrase. Length is flexible: use as many "
        "sentences as needed for clarity, but never confuse complexity with depth—"
        "simple language can go deep. "
        "When you unpack the śloka: (1) what Arjuna was facing in that beat of the "
        "dialogue, (2) why Krishna chose this reply, (3) weave classical voices "
        "(Advaita emphasis, Viśiṣṭādvaita devotion, Dvaita distinction) only as "
        "plain-language insight from commentary_samples—no name-dropping parade. "
        "If application is not requested, do not prescribe habits or homework. "
        "LANGUAGE: follow language_code — hi = Devanagari Hindi; en = English; "
        "hinglish = casual Roman Hinglish (Roman Hindi + everyday English), not "
        "formal Devanagari."
    )
    deep_verse_stories = ""
    if mode == "deep":
        deep_verse_stories = (
            "\nDEEP MODE: In guidance and/or meaning, weave 1–2 brief, relevant "
            "illustrations from the wider Hindu tradition (Itihāsa—Rāmāyaṇa, "
            "Mahābhārata; Purāṇas; Veda/Upaniṣad narratives where apt) or a clearly "
            "factual, widely known real-life parallel. Name the figure (e.g. Rāma, "
            "Sītā, Hanumān, Yudhiṣṭhira, Vidura, Dhruva, Prahlāda, Mirā, Rāmānuja—"
            "only when standard lore fits the user's question and this verse). Show "
            "the human challenge and how clarity, surrender, courage, or discernment "
            "opened a path—never as gossip; always as a lamp for the seeker's own "
            "situation. Do NOT invent obscure tales or fake citations; if unsure, "
            "stay thematic without forcing names.\n"
        )

    user_prompt = (
        f"language_code: {language}\n"
        f"user_question: {message}\n"
        f"requested_verse: {ref}\n"
        f"asks_for_application: {intent.asks_for_application}\n"
        f"asks_for_context: {intent.asks_for_context}\n"
        f"asks_for_simple_explanation: {intent.asks_for_simple_explanation}\n\n"
        f"Recent conversation context:\n{conversation_context or 'None'}\n\n"
        f"Verse detail:\nreference: {ref}\ntranslation: {detail.get('translation', verse.translation)}\n"
        f"english_meaning: {detail.get('english_meaning', '')}\n"
        f"hindi_meaning: {detail.get('hindi_meaning', '')}\n"
        f"word_meaning: {detail.get('word_meaning', '')}\n"
        f"chapter_context: {chapter_context}\n"
        f"cached_overview_en: {synthesis.get('overview_en', '')}\n"
        f"cached_overview_hi: {synthesis.get('overview_hi', '')}\n"
        f"cached_commentary_consensus_en: {synthesis.get('commentary_consensus_en', '')}\n"
        f"cached_commentary_consensus_hi: {synthesis.get('commentary_consensus_hi', '')}\n"
        f"commentary_samples:\n{commentary_text or 'None'}\n\n"
        f"supporting_verses:\n{support_text or 'None'}\n\n"
        "Instructions:\n"
        "- Open with the heart of this verse in the user's terms; stay on-topic.\n"
        "- Explain why Krishna said this to Arjuna then—not a generic war story.\n"
        "- Synthesize commentary_samples into one coherent thread; resolve tension "
        "between views in one gentle sentence if needed.\n"
        "- If asks_for_application: one short bridge from the battlefield to the "
        "user's scenario—concrete, kind, non-shaming.\n"
        "- If not asking application: actions=[] and reflection='' unless a tiny "
        "prompt truly serves understanding.\n"
        "- Do not lead with a different verse; keep this verse central.\n"
        "- verse_references: requested verse first; add only support verses that "
        "directly illuminate this line.\n"
        "- guidance: main teaching in warm, simple language—use enough sentences that "
        "the reader feels held and clear (often several short paragraphs worth if "
        "needed); never sacrifice empathy for jargon.\n"
        "- meaning: a deeper or summarizing layer—still plain words; can run longer "
        "when it helps.\n"
        f"{deep_verse_stories}"
    )
    guidance_timeout = float(
        getattr(
            settings,
            "OPENAI_GUIDANCE_TIMEOUT_DEEP_SECONDS" if mode == "deep" else "OPENAI_GUIDANCE_TIMEOUT_SIMPLE_SECONDS",
            40 if mode == "deep" else 20,
        ),
    )
    try:
        out_text = _responses_output_text(
            model=settings.OPENAI_MODEL,
            max_output_tokens=max_output_tokens,
            input_messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout_seconds=guidance_timeout,
            json_mode=True,
        )
        payload = _parse_json_payload(out_text)
        guidance = str(payload.get("guidance", "")).strip()
        meaning = str(payload.get("meaning", "")).strip()
        reflection = str(payload.get("reflection", "")).strip()
        actions = _trim_actions(
            payload.get("actions"),
            limit=5 if mode == "deep" else 3,
        )
        refs = payload.get("verse_references", [])
        if not isinstance(refs, list):
            refs = []
        refs = [str(item).strip() for item in refs if str(item).strip()]
        if not refs or refs[0] != ref:
            refs = [ref, *[item for item in refs if item != ref]]
        if not guidance:
            return _build_fallback_verse_explanation(
                message=message,
                verse=verse,
                support_verses=support_verses,
                language=language,
                intent=intent,
            )
        return GuidanceResult(
            guidance=guidance,
            meaning=meaning,
            actions=actions if intent.show_actions else [],
            reflection=reflection if intent.show_reflection else "",
            response_mode="llm",
            intent_type=intent.intent_type,
            show_actions=bool(actions) and intent.show_actions,
            show_reflection=bool(reflection) and intent.show_reflection,
            show_related_verses=intent.show_related_verses and len(refs) > 1,
        )
    except Exception as exc:
        logger.warning("Verse explanation generation failed: %s", exc)
        return _build_fallback_verse_explanation(
            message=message,
            verse=verse,
            support_verses=support_verses,
            language=language,
            intent=intent,
        )


def build_chapter_explanation(
    *,
    message: str,
    chapter_number: int,
    language: str = "en",
) -> GuidanceResult:
    """Explain a chapter directly when the user asks about a chapter."""
    language = _normalize_language(language)
    chapter = get_chapter_detail(chapter_number)
    if chapter is None:
        if language == "hi":
            return GuidanceResult(
                guidance=f"मुझे अध्याय {chapter_number} का विश्वसनीय विवरण नहीं मिला। कृपया अध्याय संख्या जाँचें।",
                meaning="",
                actions=[],
                reflection="",
                response_mode="fallback",
                intent_type="chapter_explanation",
                show_meaning=False,
                show_actions=False,
                show_reflection=False,
                show_related_verses=False,
            )
        return GuidanceResult(
            guidance=f"I could not find a reliable chapter summary for Chapter {chapter_number}. Please check the chapter number.",
            meaning="",
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type="chapter_explanation",
            show_meaning=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    if language == "hi":
        return GuidanceResult(
            guidance=(
                f"अध्याय {chapter_number} ({chapter.get('name', '')}) का मुख्य स्वर "
                f"{chapter.get('summary_hi', '') or chapter.get('meaning_hi', '')}"
            ).strip(),
            meaning="",
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type="chapter_explanation",
            show_meaning=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    if language == "hinglish":
        body = (
            str(chapter.get("summary_en", "") or chapter.get("meaning_en", "")).strip()
        )
        name = str(chapter.get("name", "")).strip()
        return GuidanceResult(
            guidance=(
                f"Chapter {chapter_number} ({name}) ka main focus yeh hai: {body}"
            ).strip(),
            meaning="",
            actions=[],
            reflection="",
            response_mode="fallback",
            intent_type="chapter_explanation",
            show_meaning=False,
            show_actions=False,
            show_reflection=False,
            show_related_verses=False,
        )
    return GuidanceResult(
        guidance=(
            f"Chapter {chapter_number} ({chapter.get('name', '')}) is mainly about "
            f"{chapter.get('summary_en', '') or chapter.get('meaning_en', '')}"
        ).strip(),
        meaning="",
        actions=[],
        reflection="",
        response_mode="fallback",
        intent_type="chapter_explanation",
        show_meaning=False,
        show_actions=False,
        show_reflection=False,
        show_related_verses=False,
    )


def build_guidance(
    message: str,
    verses: list[Verse],
    conversation_messages=None,
    language: str = "en",
    query_interpretation: dict[str, object] | None = None,
    mode: str = "simple",
    max_output_tokens: int = 350,
    intent_analysis: dict[str, object] | None = None,
) -> GuidanceResult:
    """Generate grounded guidance via OpenAI with strict fallback path."""
    language = _normalize_language(language)
    message = normalize_chat_user_message(str(message or "").strip())
    # Truncate oversized inputs before any LLM processing.
    max_chars = getattr(settings, "MAX_ASK_INPUT_CHARS", 2200)
    if len(message) > max_chars:
        message = message[:max_chars]
    intent_analysis = intent_analysis or classify_user_intent(
        message,
        mode=mode,
    ).as_dict()
    intent_type = str(intent_analysis.get("intent_type", "life_guidance"))
    show_actions = bool(intent_analysis.get("show_actions", True))
    show_reflection = bool(intent_analysis.get("show_reflection", True))
    show_related_verses = bool(intent_analysis.get("show_related_verses", True))
    query_interpretation = query_interpretation or interpret_query(message).as_dict()
    emotional_state = str(query_interpretation.get("emotional_state", "")).strip().lower()
    stressed_states = {
        "anxious",
        "fearful",
        "reactive",
        "tender",
        "confused",
        "self-doubting",
        "scattered",
    }
    wants_plain_language = mode != "deep"
    is_stressed = emotional_state in stressed_states
    tone = "plain" if wants_plain_language else "classic"
    if _is_greeting_like(message):
        return _build_compassionate_chat_reply(
            message,
            language=language,
            intent=classify_user_intent(message, mode=mode),
        )
    if _is_short_gratitude_like(message):
        return _build_gratitude_ack_reply(
            language=language,
            intent=classify_user_intent(message, mode=mode),
        )
    if not _llm_generation_enabled():
        return _build_fallback_guidance(
            message,
            verses,
            language=language,
        )

    # Detect specific topic from user message (skip keyword heuristics for pure
    # knowledge questions so we do not force "life coaching" framing).
    message_lower = message.lower()
    detected_topic = "general life guidance"
    topic_advice = ""

    if intent_type == "knowledge_question":
        detected_topic = "Scriptural or conceptual question"
        topic_advice = (
            "Answer what was asked first—directly and faithfully in Bhagavad Gita "
            "terms. Do not invent a personal struggle the user did not describe. "
            "Include verses, Krishna–Arjuna context, and named commentary traditions "
            "only when they sharpen the answer. If the question is factual or "
            "definitional, keep meaning tight; use actions=[] and reflection='' unless "
            "the user clearly wants practical steps or self-inquiry."
        )
    elif any(word in message_lower for word in ["study", "studies", "exam", "school", "college", "learn", "education", "marks", "grades", "homework", "test"]):
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

    if detected_topic in {"ANXIETY AND STRESS", "WAR, DEATH, AND THE IMMORTAL SELF"}:
        is_stressed = True

    if _is_professional_ethics_query(message) and intent_type == "life_guidance":
        detected_topic = "PROFESSIONAL OR LEGAL ETHICS (SPIRITUAL FRAMING)"
        topic_advice = (
            "Speak to truthfulness (satya), courage without cruelty, clarity of motive, "
            "and humility before complexity. Do NOT equate Kurukshetra battlefield roles "
            "with modern bar rules, court procedure, or employer policy. Do NOT give legal "
            "advice; encourage appropriate lawful and professional mentors. Prefer "
            "verses about discernment and integrity over warrior-duty imagery unless the "
            "user clearly uses a spiritual-warrior metaphor."
        )

    verse_optional_mode = len(verses) == 0
    allowed_refs = _verse_reference_set(verses)
    if verse_optional_mode:
        verses_context = (
            "NONE SUPPLIED — retrieval returned no verses, or a relevance review judged "
            "that no specific śloka should be quoted for this question. Answer in the "
            "spirit of the Gita with principles tied to the user's words. Prefer "
            "verse_references=[]. Do not invent chapter.verse numbers in prose."
        )
    else:
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
    actions_instruction = (
        "array of 2-3 concrete actions SPECIFIC to their problem"
        if show_actions
        else "[] unless truly needed for the question"
    )
    reflection_instruction = (
        "one question about THEIR specific situation"
        if show_reflection
        else "'' unless truly needed for the question"
    )
    tone_directive = ""
    if intent_type == "knowledge_question":
        tone_directive = (
            "TONE: A loving parent or creator explaining to a beloved child—patient, "
            "dignifying, never shaming, never performatively formal. No 'Dear seeker'. "
            "Answer the question directly first; expand only where it helps. "
        )
    elif mode != "deep":
        tone_directive = (
            "TONE: A deeply loving parent or creator speaking to a beloved child—"
            "clear, warm, steady, emotionally soft. No 'Dear seeker', no cold sermonizing. "
            "Prefer simple everyday words and short sentences; explain ideas so any "
            "education level can follow—do not shorten arbitrarily if more sentences "
            "would genuinely help understanding. Invite change without shame; "
            "acknowledge the good in the person even when correcting course. "
        )
        if is_stressed:
            tone_directive += (
                "The user sounds strained—go slower, one main idea at a time, "
                "extra reassurance. "
            )
    else:
        tone_directive = (
            "TONE: Compassionate, luminous, serene—Krishna's voice as mentor, not "
            "performative deity. Never claim literal divine identity. Depth does not "
            "mean difficulty: keep language accessible unless the user asks for "
            "technical śāstra detail; then unpack gently. "
        )

    system_prompt = (
        "You are a Bhagavad Gita guidance assistant. Return valid JSON only.\n"
        "AUDIENCE: Seekers of every age and background—plain language first, empathy "
        "alongside doctrine; clarity beats cleverness.\n"
        "Required keys: guidance, meaning, actions, reflection, verse_references.\n"
        "Optional key: related_verse_references — array of chapter.verse strings "
        "(max 4, no duplicates of verse_references). Use it ONLY for extra verses "
        "worth exploring next; omit this key if you prefer the app to choose "
        "related verses automatically; use [] if no extra verses deserve a name.\n"
        + tone_directive
        + "ON-TOPIC: Answer what the user actually asked. No tangents, no filler "
        "stories, no generic duty slogans. If they did not ask for life advice, "
        "do not invent a crisis or prescribe habits.\n"
        "WHEN A VERSE MATTERS: briefly say why Krishna said it to Arjuna in that "
        "moment; weave in how major traditions read it (e.g., Shankara's "
        "non-dual emphasis, Ramanuja's surrender lens, Madhva's distinction of "
        "selves—only as light commentary, not academic name-dropping); then, only "
        "if the user seeks guidance, bridge to their situation without forcing.\n"
        "VERSE RELEVANCE: Prefer verses from the provided context when they fit. "
        "If none fit, you may cite other chapter.verse refs you are confident "
        "about. Omit verse clutter—fewer, sharper verses beat many weak ones. "
        "Do not reflexively pick the same famous verse (e.g. 2.47) when retrieval "
        "offers a different primary verse or when conversation history already used "
        "that line—vary or follow retrieval order.\n"
        "SAFETY: non-medical, non-legal. Latest user message is the primary task; "
        "history is supporting context only.\n"
        "LANGUAGE: If language_code is 'hi', user-facing strings in natural Hindi "
        "(Devanagari). If 'en', English. If 'hinglish', write guidance, meaning, "
        "actions, and reflection in casual Roman Hinglish (Roman Hindi mixed with "
        "everyday English the way urban Indian users type): short sentences, "
        "natural code-switching, warm and clear—NOT formal Devanagari prose. "
        "Quoted verse lines may stay as in context (English translation); "
        "chapter.verse labels stay numeric."
    )
    if _is_professional_ethics_query(message):
        system_prompt += (
            "\nPROFESSIONAL/LEGAL QUESTION: You are not a lawyer. No procedural "
            "legal advice. Do not equate Kurukshetra warrior duty with modern "
            "professional or court obligations. Emphasize satya, integrity, "
            "humility, and seeking appropriate human counsel.\n"
        )
    if verse_optional_mode:
        system_prompt += (
            "\nVERSE-OPTIONAL: No verse bundle is attached. You may set "
            "verse_references to []. If empty, do not write chapter.verse numbers in "
            "prose. Still give substantive, situation-specific guidance rooted in Gita "
            "teaching.\n"
        )

    verse_mode_note = ""
    if verse_optional_mode:
        verse_mode_note = (
            "VERSE CONTEXT: No śloka list is attached (or none passed relevance "
            "review). Prefer verse_references=[]. Do not fabricate verse numbers in "
            "prose unless they appear in verse_references and are genuine.\n\n"
        )
    ethics_preface = ""
    if _is_professional_ethics_query(message):
        ethics_preface = (
            "Note: The user may be describing a legal/professional role. Offer "
            "spiritual-ethical framing only; not legal advice.\n\n"
        )

    shared_context_block = (
        verse_mode_note
        + ethics_preface
        + f"language_code: {language}\n\n"
        f"Structured query interpretation: "
        f"{json.dumps(query_interpretation, ensure_ascii=False)}\n\n"
        f"Intent analysis: {json.dumps(intent_analysis, ensure_ascii=False)}\n\n"
        f"User message:\n{message}\n\n"
        f"Recent conversation context:\n{conversation_context or 'None'}\n\n"
        f"Primary verse candidate by retrieval rank: {primary_reference or 'None'}\n"
        f"Chapter / battlefield context (why Krishna speaks here): "
        f"{primary_chapter_context}\n\n"
        f"Available verse context:\n{verses_context}\n\n"
    )

    deep_append = ""
    if mode == "deep" and intent_type == "knowledge_question":
        deep_append = (
            "\nDEEP MODE (knowledge): Richer scriptural texture—why this teaching landed "
            "on the Kurukshetra moment; how classical commentators differ (still plain "
            "English or natural Hindi/Hinglish). Add 1–2 ILLUSTRATIONS when they clarify: "
            "named episodes from Rāmāyaṇa, Mahābhārata, Purāṇas, or major Upaniṣad/Vedic "
            "dialogue stories where widely received tradition matches the doctrine—"
            "character, dilemma, turning point—not trivia. Optionally a sober, factual "
            "modern parallel ONLY if widely attested and relevant; never invent lore. "
            "Without unsolicited life coaching unless the user asked.\n"
        )
    elif mode == "deep":
        deep_append = (
            "\nDEEP MODE ACTIVE — deeper reflection. Use ample space while keeping "
            "language gentle and understandable.\n"
            "- guidance: emotionally and spiritually layered; speak to the user's "
            "situation with warmth; long-form welcome when it serves clarity.\n"
            "- meaning: why Krishna said this to Arjuna at that Mahābhārata moment, "
            "woven with the user's thread—avoid academic dense blocks; split into plain "
            "readable chunks.\n"
            "- Include 1–3 ILLUSTRATIVE PATHWAYS that mirror their challenge: prefer "
            "named stories from sampradāya lore—Rāmāyaṇa (Rāma, Sītā, Lakṣmaṇa, Bharata, "
            "Hanumat…), Mahābhārata (Vidura, Yudhiṣṭhira, Karṇa, Bhīṣma…), Purāṇas "
            "(Dhruva, Prahlāda…), Bhāgavata līlā, Mahādeva–Pārvatī dialogue, ṛṣis in "
            "Upaniṣads—ONLY when the moral parallel truly fits their question and the "
            "verses cited. Include how the figure faced a similar knot (duty, grief, "
            "fear, rivalry, exile, humility, surrender) and what steadied them. "
            "Optional: one restrained, fact-based modern/public example if genuinely "
            "parallel—no gossip, no unsourced claims.\n"
            "- actions: 3–5 sequenced steps, each with a brief 'why' in simple words.\n"
            "- reflection: 2–4 probing questions tied to their actual words.\n"
            "- name inner states (fear, shame, fatigue) and validate before redirecting.\n"
            "- optional: one breath or ethical micro-practice aligned to the teaching.\n"
            "- Never fabricate scripture; skip names rather than invent episodes.\n"
        )

    if intent_type == "knowledge_question":
        user_prompt = (
            shared_context_block
            + f"QUESTION TYPE: {detected_topic}\n"
            f"Instructions: {topic_advice}\n\n"
            "Requirements:\n"
            "- Answer the user's question first; stay in Bhagavad Gita context.\n"
            "- Do not redirect into unrelated life domains.\n"
            "- guidance: directly responsive in simple, soft language—use as many "
            "clear sentences as needed; in deep mode, add scriptural illustrations "
            "as specified in the DEEP MODE block below when applicable.\n"
            "- meaning: clarify the idea or verse logic in readable terms; avoid "
            "repeating guidance unless helpful.\n"
            f"- actions: {actions_instruction}\n"
            f"- reflection: {reflection_instruction}\n"
            "- verse_references: only verses that truly help; [] if none needed.\n"
            "- related_verse_references: optional; only clearly relevant exploration.\n"
            "- write in language_code.\n"
            + deep_append
        )
    else:
        vague_life_append = ""
        if _is_minimal_context_life_message(message) and not verse_optional_mode:
            vague_life_append = (
                "\nMINIMAL USER DETAIL: The latest message is very short or only a generic "
                "plea. Prefer the FIRST verse in Available verse context as anchor when "
                "listed; do not habitually default to 2.47 if another retrieved verse fits "
                "better. If Recent conversation context already states a situation, "
                "stay with that thread; avoid repeating the same verse-and-paragraph "
                "framing as the last assistant message unless the user truly repeats "
                "the same ask. One warm sentence inviting what hurts most now is "
                "appropriate.\n"
            )
        verse_use_line = (
            "- Verse use: one strong anchor; quote a short line from its translation "
            "in guidance or meaning; say why Krishna pressed this on Arjuna then.\n"
            if not verse_optional_mode
            else (
                "- Verse use: only if a specific śloka truly fits; otherwise set "
                "verse_references to [] and teach from Gita principles without writing "
                "numbered verse addresses in prose.\n"
            )
        )
        user_prompt = (
            shared_context_block
            + vague_life_append
            + f"DETECTED TOPIC: {detected_topic}\n"
            f"TOPIC-SPECIFIC ANGLE: {topic_advice}\n\n"
            "Requirements:\n"
            f"- Center the response on {detected_topic.lower()}; avoid generic "
            f"'do your duty' unless it truly fits their words.\n"
            f"- {topic_advice}\n"
            "- Address the latest message; first sentences should mirror their situation.\n"
            "- Structure (life-guidance): (1) empathic acknowledgment using their words, "
            "(2) what Krishna's teaching offers for this kind of bind, "
            "(3) one or two humble next steps that feel doable.\n"
            "- Disarm resistance: warmth, respect, no moral superiority; speak to "
            "the part of them that already wants peace.\n"
            + verse_use_line
            + "- Bridge to today only where it clarifies—no forced allegory.\n"
            "- guidance: mirror their situation first; then unfold Krishna's reply in "
            "warm, plain language—long enough that diverse readers feel understood "
            "(often several sentences or short paragraphs); never vague virtue-signaling.\n"
            "- meaning: deepen the verse or principle in still-simple words—length "
            "flexible when it helps.\n"
            f"- actions: {actions_instruction}\n"
            f"- reflection: {reflection_instruction}\n"
            "- verse_references: best-fit chapter.verse list (may extend beyond "
            "provided context if clearly more apt); use [] if no verse should be named.\n"
            "- related_verse_references: optional; only verses that deepen exploration.\n"
            "- write in language_code.\n"
            + deep_append
        )

    guidance_timeout = float(
        getattr(
            settings,
            "OPENAI_GUIDANCE_TIMEOUT_DEEP_SECONDS" if mode == "deep" else "OPENAI_GUIDANCE_TIMEOUT_SIMPLE_SECONDS",
            40 if mode == "deep" else 20,
        ),
    )
    try:
        out_text = _responses_output_text(
            model=settings.OPENAI_MODEL,
            max_output_tokens=max_output_tokens,
            input_messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout_seconds=guidance_timeout,
            json_mode=True,
        )
        payload = _parse_json_payload(out_text)

        guidance = str(payload.get("guidance", "")).strip()
        meaning = str(payload.get("meaning", "")).strip()
        reflection = str(payload.get("reflection", "")).strip()
        actions = payload.get("actions", [])
        references = payload.get("verse_references", [])

        actions = _trim_actions(actions, limit=5 if mode == "deep" else 3)

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
            not verse_optional_mode
            and primary_reference
            and primary_reference in allowed_refs
            and not references
        ):
            references = [primary_reference]

        related_verses_refs = _parse_related_verse_references_from_llm(
            payload,
            primary_refs=references,
        )

        reflection_ok = (not show_reflection) or bool(reflection)
        actions_ok = (not show_actions) or (len(actions) >= 2)
        if (
            not guidance
            or not meaning
            or not reflection_ok
            or not actions_ok
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
                verse_optional=verse_optional_mode,
            )
        ):
            return _build_fallback_guidance(
                message,
                verses,
                language=language,
                honor_empty_verse_context=verse_optional_mode,
            )

        guidance = _guidance_with_primary_quote(
            guidance=guidance,
            primary_verse=primary_verse,
            language=language,
            tone=tone,
        )

        return GuidanceResult(
            guidance=guidance,
            meaning=meaning,
            actions=actions if show_actions else [],
            reflection=reflection if show_reflection else "",
            response_mode="llm",
            intent_type=intent_type,
            show_actions=bool(actions) and show_actions,
            show_reflection=bool(reflection) and show_reflection,
            show_related_verses=show_related_verses,
            related_verses_refs=related_verses_refs,
        )
    except Exception as exc:
        logger.warning("Guidance generation failed: %s", exc)
        return _build_fallback_guidance(
            message,
            verses,
            language=language,
            honor_empty_verse_context=verse_optional_mode,
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
    verses = [v for v in _get_all_verses_cached() if v.chapter == chapter_number]
    verses.sort(key=lambda v: v.verse)
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
    verse_obj = next(
        (v for v in _get_all_verses_cached() if v.chapter == chapter and v.verse == verse),
        None,
    )
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
        client = _openai_client()
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
    if _llm_generation_enabled():
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
            out_text = _responses_output_text(
                model=settings.OPENAI_MODEL,
                input_messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=True,
            )
            payload = _validate_verse_synthesis_payload(
                _parse_json_payload(out_text),
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
