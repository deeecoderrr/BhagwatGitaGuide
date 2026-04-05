from __future__ import annotations

"""Domain services for safety checks, retrieval, and guidance generation."""

from dataclasses import dataclass
import json
import logging
import math
import re

from django.conf import settings
from openai import OpenAI

from guide_api.data.default_verses import DEFAULT_VERSES
from guide_api.models import Verse

logger = logging.getLogger(__name__)
_seed_synced = False

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
    },
    "anger": {"anger", "angry", "frustrated", "rage", "irritated"},
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
    "anger": {"2.62", "2.63", "3.37", "16.21"},
    "career": {"2.47", "3.19", "3.30", "18.58"},
    "relationships": {"12.13", "12.15", "16.21"},
    "discipline": {"6.12", "6.26", "6.35", "3.19", "3.8", "2.48"},
    "purpose": {"3.35", "18.47", "18.66", "6.5", "2.50", "2.31"},
    "comparison": {"2.62", "2.63", "2.71", "12.13", "12.15", "16.21"},
}

THEME_CHAPTER_PRIORS = {
    "anxiety": {2, 6, 18},
    "anger": {2, 3, 16},
    "career": {2, 3, 18},
    "discipline": {3, 6, 18},
    "purpose": {2, 3, 18},
    "comparison": {2, 12, 16},
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


def retrieve_verses_with_trace(message: str, limit: int = 3) -> RetrievalResult:
    """Preferred retrieval strategy: semantic first, hybrid fallback."""
    semantic = retrieve_semantic_verses_with_trace(
        message=message,
        limit=limit,
    )
    if semantic.retrieval_mode == "semantic":
        return semantic
    return retrieve_hybrid_verses_with_trace(message=message, limit=limit)


def retrieve_verses(message: str, limit: int = 3) -> list[Verse]:
    """Compatibility helper returning verse list without trace fields."""
    return retrieve_verses_with_trace(message=message, limit=limit).verses


def _build_fallback_guidance(verses: list[Verse]) -> GuidanceResult:
    """Create deterministic, safe guidance when LLM is unavailable."""
    refs = ", ".join(f"{verse.chapter}.{verse.verse}" for verse in verses)
    guidance = (
        "Your concern is valid. The Gita encourages steady action "
        "without fear of "
        f"outcomes. Let these teachings guide your next step: {refs}."
    )
    meaning = (
        "Focus on what you can control today: your effort, your attitude, "
        "and your "
        "speech. Let outcomes unfold with patience."
    )
    actions = [
        "Write one concrete action you can complete in the next 30 minutes.",
        "Take three deep breaths before reacting to stressful thoughts.",
        "End the day by noting one action done with sincerity.",
    ]
    reflection = "What am I trying to control that is not truly in my hands?"
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


def _serialize_verses_for_prompt(verses: list[Verse]) -> str:
    """Serialize retrieved verses into compact prompt context text."""
    lines = []
    for verse in verses:
        lines.append(
            (
                f"{verse.chapter}.{verse.verse}: {verse.translation} "
                f"(themes: {', '.join(verse.themes)})"
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
) -> GuidanceResult:
    """Generate grounded guidance via OpenAI with strict fallback path."""
    if not settings.OPENAI_API_KEY:
        return _build_fallback_guidance(verses)

    allowed_refs = _verse_reference_set(verses)
    verses_context = _serialize_verses_for_prompt(verses)
    conversation_context = _serialize_conversation_context(
        conversation_messages,
    )
    system_prompt = (
        "You are a Bhagavad Gita guidance assistant. Return valid JSON only "
        "with keys: "
        "guidance, meaning, actions, reflection, verse_references. "
        "Do not claim to be Krishna. Be calm and practical. "
        "Use only the provided verses and keep advice safe and "
        "non-medical/non-legal. Always answer the user's latest message "
        "as the primary task. Use conversation history only as supporting "
        "context for continuity, not as the main question to answer."
    )
    user_prompt = (
        f"User problem:\n{message}\n\n"
        f"Recent conversation context:\n{conversation_context or 'None'}\n\n"
        f"Available verse context:\n{verses_context}\n\n"
        "Requirements:\n"
        "- answer the latest user problem above, not the older history\n"
        "- first line must directly address the user's latest specific problem\n"
        "- when recent conversation context exists, use it only to better "
        "understand the latest problem and maintain continuity\n"
        "- do not drift back to older unresolved topics unless the latest "
        "message clearly asks to revisit them\n"
        "- guidance: 2-4 sentences\n"
        "- meaning: 1-2 sentences\n"
        "- actions: array of 2-3 concrete actions\n"
        "- reflection: one question\n"
        "- verse_references: array using chapter.verse from context only\n"
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
            or not _is_grounded_response(
                guidance,
                meaning,
                references,
                allowed_refs,
            )
        ):
            return _build_fallback_guidance(verses)

        return GuidanceResult(
            guidance=guidance,
            meaning=meaning,
            actions=actions,
            reflection=reflection,
            response_mode="llm",
        )
    except Exception as exc:
        logger.warning("OpenAI guidance generation failed: %s", exc)
        return _build_fallback_guidance(verses)
