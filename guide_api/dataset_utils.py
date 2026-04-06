"""Utilities for normalizing external Bhagavad Gita dataset files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re


CANONICAL_CSV_HEADERS = [
    "ID",
    "Chapter",
    "Verse",
    "Shloka",
    "Transliteration",
    "HinMeaning",
    "EngMeaning",
    "WordMeaning",
]

COLUMN_ALIASES = {
    "chapter": "chapter",
    "chapter_no": "chapter",
    "chapter_number": "chapter",
    "verse": "verse",
    "verse_no": "verse",
    "verse_number": "verse",
    "shloka": "shloka",
    "sloka": "shloka",
    "sanskrit": "shloka",
    "sanskritanuvad": "shloka",
    "text": "shloka",
    "transliteration": "transliteration",
    "hinmeaning": "hindi_meaning",
    "hindimeaning": "hindi_meaning",
    "hindi": "hindi_meaning",
    "hindi_meaning": "hindi_meaning",
    "hindianuvad": "hindi_meaning",
    "engmeaning": "english_meaning",
    "enlgishtranslation": "english_meaning",
    "englishtranslation": "english_meaning",
    "english": "english_meaning",
    "englishmeaning": "english_meaning",
    "english_meaning": "english_meaning",
    "wordmeaning": "word_meaning",
    "word_meaning": "word_meaning",
    "word-to-word": "word_meaning",
    "title": "title",
    "id": "id",
}


@dataclass(frozen=True)
class MultiScriptVerse:
    """Canonical in-memory representation for one verse row."""

    chapter: int
    verse: int
    shloka: str
    transliteration: str
    hindi_meaning: str
    english_meaning: str
    word_meaning: str
    title: str = ""
    row_id: int = 0

    @property
    def reference(self) -> str:
        """Return chapter.verse string used by retrieval and docs."""
        return f"{self.chapter}.{self.verse}"


def _clean(value: object) -> str:
    """Normalize whitespace and convert missing values to empty string."""
    return " ".join(str(value or "").strip().split())


def _normalized_key(name: str) -> str:
    """Map source column names to canonical field keys."""
    key = "".join(char for char in str(name).lower() if char.isalnum() or char == "_")
    return COLUMN_ALIASES.get(key, key)


def _parse_int(value: object) -> int | None:
    """Parse numeric-ish spreadsheet values into integer safely."""
    cleaned = _clean(value)
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _extract_numbers(value: object) -> list[int]:
    """Extract integer groups from mixed labels like 'Verse 2.47'."""
    return [int(item) for item in re.findall(r"\d+", _clean(value))]


def _parse_chapter(value: object) -> int | None:
    """Parse chapter from raw field such as 'Chapter 3' or '3'."""
    parsed = _parse_int(value)
    if parsed is not None:
        return parsed
    numbers = _extract_numbers(value)
    if numbers:
        return numbers[0]
    return None


def _parse_verse(value: object) -> int | None:
    """Parse verse from raw field such as 'Verse 2.47' or '47'."""
    cleaned = _clean(value)
    dotted_match = re.search(r"(\d+)\.(\d+)", cleaned)
    if dotted_match:
        return int(dotted_match.group(2))

    parsed = _parse_int(cleaned)
    if parsed is not None:
        return parsed

    numbers = _extract_numbers(cleaned)
    if numbers:
        return numbers[-1]
    return None


def normalize_multiscript_rows(rows: list[dict[str, object]]) -> list[MultiScriptVerse]:
    """Convert raw row dicts into deduplicated canonical verse rows."""
    normalized: dict[tuple[int, int], MultiScriptVerse] = {}

    for raw in rows:
        mapped = {}
        for key, value in raw.items():
            mapped[_normalized_key(key)] = value

        chapter = _parse_chapter(mapped.get("chapter"))
        verse = _parse_verse(mapped.get("verse"))
        if chapter is None or verse is None:
            continue

        english_meaning = _clean(mapped.get("english_meaning"))
        if not english_meaning:
            # English meaning is required because it powers core translation
            # text in Verse.translation and embedding context.
            continue

        key = (chapter, verse)
        if key in normalized:
            # Keep the first seen row per verse for deterministic imports.
            continue

        row_id = _parse_int(mapped.get("id")) or 0
        normalized[key] = MultiScriptVerse(
            chapter=chapter,
            verse=verse,
            shloka=_clean(mapped.get("shloka")),
            transliteration=_clean(mapped.get("transliteration")),
            hindi_meaning=_clean(mapped.get("hindi_meaning")),
            english_meaning=english_meaning,
            word_meaning=_clean(mapped.get("word_meaning")),
            title=_clean(mapped.get("title")),
            row_id=row_id,
        )

    return [
        normalized[key]
        for key in sorted(normalized.keys())
    ]


def load_multiscript_rows(path: Path, sheet: str | None = None) -> list[dict[str, object]]:
    """Load row dictionaries from a CSV or XLSX dataset file."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except Exception as exc:
            raise RuntimeError(
                "XLSX support requires openpyxl. Install dependencies and retry.",
            ) from exc

        workbook = load_workbook(path, data_only=True, read_only=True)
        worksheet = workbook[sheet] if sheet else workbook.active
        values = worksheet.values
        headers = next(values, None)
        if not headers:
            return []
        rows = []
        for row in values:
            rows.append(
                {
                    str(header or ""): value
                    for header, value in zip(headers, row)
                }
            )
        return rows

    raise ValueError(f"Unsupported file extension: {path.suffix}")


def to_canonical_csv_rows(verses: list[MultiScriptVerse]) -> list[dict[str, object]]:
    """Convert canonical verse rows into canonical CSV output schema."""
    rows = []
    for index, verse in enumerate(verses, start=1):
        rows.append(
            {
                "ID": verse.row_id or index,
                "Chapter": verse.chapter,
                "Verse": verse.verse,
                "Shloka": verse.shloka,
                "Transliteration": verse.transliteration,
                "HinMeaning": verse.hindi_meaning,
                "EngMeaning": verse.english_meaning,
                "WordMeaning": verse.word_meaning,
            }
        )
    return rows


def write_canonical_csv(path: Path, verses: list[MultiScriptVerse]) -> None:
    """Persist normalized multi-script rows in canonical CSV shape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_CSV_HEADERS)
        writer.writeheader()
        writer.writerows(to_canonical_csv_rows(verses))
