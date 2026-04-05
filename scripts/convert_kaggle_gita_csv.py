#!/usr/bin/env python3
"""
Convert Kaggle Bhagavad Gita CSV into importer JSON schema.

Expected CSV columns from dataset:
- Chapter
- Verse
- EngMeaning
- (optional) WordMeaning, Transliteration, Shloka, HinMeaning

Output JSON schema (compatible with manage.py import_gita):
[
  {
    "chapter": 1,
    "verse": 1,
    "translation": "...",
    "commentary": "...",
    "themes": []
  }
]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _clean(text: str) -> str:
    """Normalize whitespace and safely handle missing values."""
    return " ".join((text or "").strip().split())


def parse_args() -> argparse.Namespace:
    """Parse CLI options for source CSV and output JSON file."""
    parser = argparse.ArgumentParser(
        description="Convert Kaggle Bhagavad Gita CSV to importable JSON.",
    )
    parser.add_argument(
        "--input",
        required=False,
        default="data/Bhagwad_Gita.csv",
        help="Path to Kaggle CSV file.",
    )
    parser.add_argument(
        "--output",
        required=False,
        default="data/gita_700.json",
        help="Path for converted JSON output.",
    )
    return parser.parse_args()


def main() -> int:
    """Convert CSV rows into importer schema and write JSON output."""
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Input CSV not found: {input_path}")
        print("Tip: put Kaggle file at data/Bhagwad_Gita.csv")
        return 1

    rows = []
    skipped = 0
    seen = set()

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            try:
                chapter = int(_clean(raw.get("Chapter", "")))
                verse = int(_clean(raw.get("Verse", "")))
            except ValueError:
                skipped += 1
                continue

            translation = _clean(raw.get("EngMeaning", ""))
            if not translation:
                skipped += 1
                continue

            # Prefer word meaning as short commentary.
            # Fallback to transliteration.
            commentary = _clean(raw.get("WordMeaning", "")) or _clean(
                raw.get("Transliteration", ""),
            )

            key = (chapter, verse)
            if key in seen:
                # Keep first occurrence and skip duplicates.
                skipped += 1
                continue
            seen.add(key)

            rows.append(
                {
                    "chapter": chapter,
                    "verse": verse,
                    "translation": translation,
                    "commentary": commentary,
                    "themes": [],
                }
            )

    rows.sort(key=lambda item: (item["chapter"], item["verse"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Converted rows: {len(rows)}")
    print(f"Skipped rows: {skipped}")
    print(f"Output file: {output_path}")
    print(
        "Next step: python manage.py import_gita --file "
        f"{output_path} --dry-run",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
