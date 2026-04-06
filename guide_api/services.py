from __future__ import annotations

"""Domain services for safety checks, retrieval, and guidance generation."""

from dataclasses import dataclass
import csv
import json
import logging
import math
import re
from pathlib import Path

from django.conf import settings
from django.db import connection
from openai import OpenAI

from guide_api.data.default_verses import DEFAULT_VERSES
from guide_api.models import Verse

logger = logging.getLogger(__name__)
_seed_synced = False
SUPPORTED_LANGUAGE_CODES = {"en", "hi"}
_verse_quote_cache: dict[str, dict[str, str]] | None = None
_verse_additional_angle_cache: dict[str, list[dict[str, str]]] | None = None
_merged_verse_context_cache: dict[str, dict[str, object]] | None = None
_chapter_summary_cache: dict[int, dict[str, object]] | None = None
_vedic_slok_cache: dict[str, dict[str, object]] | None = None

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
}

THEME_CHAPTER_PRIORS = {
    "anxiety": {2, 6, 18},
    "anger": {2, 3, 16},
    "career": {2, 3, 18},
    "discipline": {3, 6, 18},
    "purpose": {2, 3, 18},
    "comparison": {2, 12, 16},
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

UNIVERSAL_CURATED_REFERENCES = [
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
}

THEME_LABELS_HI = {
    "anxiety": "चिंता और स्थिरता",
    "career": "काम और कर्तव्य",
    "relationships": "रिश्ते और करुणा",
    "anger": "क्रोध और आत्म-संयम",
    "discipline": "अनुशासन और एकाग्रता",
    "purpose": "उद्देश्य और दिशा",
    "comparison": "तुलना और आत्म-मूल्य",
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


def is_risky_prompt(message: str) -> bool:
    """Block crisis/medical/legal style prompts with keyword checks."""
    lowered = message.lower()
    return any(keyword in lowered for keyword in RISK_KEYWORDS)


def ensure_seed_verses() -> None:
    """Ensure default verse seed data exists for local/dev environments."""
    global _seed_synced
    if _seed_synced and Verse.objects.exists():
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


def _verse_reference(verse: Verse) -> str:
    """Format verse primary key as chapter.verse string."""
    return f"{verse.chapter}.{verse.verse}"


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
        return retrieval

    fallback_verses = _curated_fallback_verses(message=message, limit=limit)
    if not fallback_verses:
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


def _load_vedic_slok_cache() -> dict[str, dict[str, object]]:
    """Load multi-author sloka commentary copied from the Vedic repo."""
    global _vedic_slok_cache
    if _vedic_slok_cache is not None:
        return _vedic_slok_cache

    _vedic_slok_cache = {}
    slok_dir = Path(__file__).resolve().parents[1] / "data" / "slok"
    if not slok_dir.exists():
        return _vedic_slok_cache

    commentary_fields = ("et", "ec", "ht", "hc", "sc")
    try:
        for path in sorted(slok_dir.glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            chapter = row.get("chapter")
            verse = row.get("verse")
            if not chapter or not verse:
                continue
            reference = f"{int(chapter)}.{int(verse)}"
            commentaries: list[dict[str, str]] = []
            for key, value in row.items():
                if not isinstance(value, dict):
                    continue
                author = str(value.get("author", "")).strip()
                parts = [
                    str(value.get(field, "")).strip()
                    for field in commentary_fields
                ]
                parts = [part for part in parts if part]
                if not author or not parts:
                    continue
                commentaries.append(
                    {
                        "author": author,
                        "text": " ".join(parts),
                    }
                )
            _vedic_slok_cache[reference] = {
                "speaker": str(row.get("speaker", "")).strip(),
                "slok": str(row.get("slok", "")).strip(),
                "transliteration": str(row.get("transliteration", "")).strip(),
                "commentaries": commentaries,
            }
    except Exception as exc:
        logger.warning("Vedic slok cache load failed: %s", exc)
    return _vedic_slok_cache


def _load_merged_verse_context_cache() -> dict[str, dict[str, object]]:
    """Merge canonical verse context and additional angles by reference."""
    global _merged_verse_context_cache
    if _merged_verse_context_cache is not None:
        return _merged_verse_context_cache

    quote_cache = _load_verse_quote_cache()
    additional_cache = _load_additional_angle_cache()
    vedic_slok_cache = _load_vedic_slok_cache()
    merged: dict[str, dict[str, object]] = {}

    references = (
        set(quote_cache.keys())
        | set(additional_cache.keys())
        | set(vedic_slok_cache.keys())
    )
    for reference in references:
        quote_row = quote_cache.get(reference, {})
        angle_rows = additional_cache.get(reference, [])
        vedic_row = vedic_slok_cache.get(reference, {})

        merged[reference] = {
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
            if not merged[reference]["sanskrit"]:
                merged[reference]["sanskrit"] = str(
                    angle.get("sanskrit", "")
                ).strip()
            if not merged[reference]["transliteration"]:
                merged[reference]["transliteration"] = str(
                    angle.get("transliteration", "")
                ).strip()
            if not merged[reference]["hindi"]:
                merged[reference]["hindi"] = str(
                    angle.get("hindi", "")
                ).strip()
            if not merged[reference]["english"]:
                merged[reference]["english"] = str(
                    angle.get("english", "")
                ).strip()
            if not merged[reference]["word_meaning"]:
                merged[reference]["word_meaning"] = str(
                    angle.get("word_meaning", "")
                ).strip()

    _merged_verse_context_cache = merged
    return _merged_verse_context_cache


def _merged_verse_context(reference: str) -> dict[str, object]:
    """Return one merged context payload for a verse reference."""
    return _load_merged_verse_context_cache().get(reference, {})


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
    rows = _author_commentary_entries(reference)
    if message:
        rows = sorted(
            rows,
            key=lambda entry: (
                -_author_commentary_match_score(
                    message=message,
                    entry=entry,
                ),
                str(entry.get("author", "")).lower(),
            ),
        )
    rows = rows[:limit]
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


def _build_fallback_guidance(
    message: str,
    verses: list[Verse],
    *,
    language: str = "en",
) -> GuidanceResult:
    """Create deterministic, safe guidance when LLM is unavailable."""
    language = _normalize_language(language)
    refs = ", ".join(f"{verse.chapter}.{verse.verse}" for verse in verses)
    primary_verse = verses[0] if verses else None
    primary_ref = _verse_reference(primary_verse) if primary_verse else "2.47"
    chapter_context = _chapter_perspective(
        chapter=primary_verse.chapter if primary_verse else 2,
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
    """Serialize retrieved verses into compact prompt context text."""
    lines = []
    for verse in verses:
        ref = _verse_reference(verse)
        row = _merged_verse_context(ref)
        angle = _additional_angle_text(ref)
        commentary = _author_commentary_text(ref, limit=2, message=message)
        lines.append(
            (
                f"{verse.chapter}.{verse.verse}: {verse.translation} "
                f"(themes: {', '.join(verse.themes)}) "
                f"(hindi_meaning: {row.get('hindi', '')[:120]}) "
                f"(word_meaning: {row.get('word_meaning', '')[:120]}) "
                f"(additional_angles: {angle[:220]}) "
                f"(author_commentary: {commentary[:260]})"
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


def build_guidance(
    message: str,
    verses: list[Verse],
    conversation_messages=None,
    language: str = "en",
) -> GuidanceResult:
    """Generate grounded guidance via OpenAI with strict fallback path."""
    language = _normalize_language(language)
    if not settings.OPENAI_API_KEY:
        return _build_fallback_guidance(
            message,
            verses,
            language=language,
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
        "Use only the provided verses and keep advice safe and "
        "non-medical/non-legal. Always answer the user's latest message "
        "as the primary task. Use conversation history only as supporting "
        "context for continuity, not as the main question to answer. "
        "If language_code is 'hi', write all user-facing text in natural "
        "Hindi (Devanagari). If language_code is 'en', write in English."
    )
    user_prompt = (
        f"language_code: {language}\n\n"
        f"User problem:\n{message}\n\n"
        f"Recent conversation context:\n{conversation_context or 'None'}\n\n"
        f"Primary verse candidate by retrieval rank: "
        f"{primary_reference or 'None'}\n"
        f"Context for why Krishna said this to Arjuna: "
        f"{primary_chapter_context}\n\n"
        f"Available verse context:\n{verses_context}\n\n"
        "Requirements:\n"
        "- answer the latest user problem above, not the older history\n"
        "- first line must directly address the user's latest specific problem\n"
        "- use a soothing, reassuring, devotional-guru tone that increases "
        "the seeker's calmness and curiosity for the next step\n"
        "- structure the answer logic in this order: "
        "1) what Krishna was addressing in Arjuna, "
        "2) the timeless principle of that teaching, "
        "3) how that same principle applies to the user's present situation\n"
        "- explicitly explain why Krishna said the primary teaching to Arjuna "
        "in that battlefield context, then validate how the same principle "
        "applies to the user's current problem\n"
        "- choose one most relevant verse as the primary anchor (prefer the "
        "first retrieved verse unless another is clearly more relevant)\n"
        "- include one short direct quote from the chosen primary verse "
        "translation in guidance or meaning\n"
        "- do not merely summarize the verse; interpret Krishna's intention "
        "for Arjuna and then bridge it to the user's dilemma\n"
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
        "- guidance: 2-4 sentences\n"
        "- meaning: 1-2 sentences\n"
        "- actions: array of 2-3 concrete actions\n"
        "- reflection: one question\n"
        "- verse_references: array using chapter.verse from context only\n"
        "- write guidance/meaning/actions/reflection in the specified "
        "language_code\n"
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
