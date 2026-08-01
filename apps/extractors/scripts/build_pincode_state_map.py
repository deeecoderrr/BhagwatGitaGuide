#!/usr/bin/env python3
"""Build pincode → ITR StateCode JSON from India Post CSV (bharatpin dataset)."""
from __future__ import annotations

import csv
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.extractors.india_state_codes import state_code_from_postal_name  # noqa: E402

DEFAULT_CSV_URL = (
    "https://raw.githubusercontent.com/jeet308/bharatpin/main/src/bharatpin/data/pincodes.csv"
)
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "pincode_state_map.json"


def _load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build_mapping(rows: list[dict[str, str]]) -> tuple[dict[str, str], list[str]]:
    votes: dict[str, Counter[str]] = {}
    skipped: list[str] = []

    for row in rows:
        pin = (row.get("pincode") or "").strip()
        if len(pin) != 6 or not pin.isdigit():
            continue
        state_name = (row.get("state") or "").strip()
        code = state_code_from_postal_name(state_name)
        if not code:
            skipped.append(state_name)
            continue
        votes.setdefault(pin, Counter())[code] += 1

    mapping: dict[str, str] = {}
    for pin, counter in votes.items():
        mapping[pin] = counter.most_common(1)[0][0]
    return mapping, sorted(set(skipped))


def main() -> int:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if csv_path is None:
        tmp = Path("/tmp/bharatpin_pincodes.csv")
        print(f"Downloading {DEFAULT_CSV_URL} …")
        urllib.request.urlretrieve(DEFAULT_CSV_URL, tmp)
        csv_path = tmp

    rows = _load_csv_rows(csv_path)
    mapping, unknown_states = build_mapping(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": "bharatpin pincodes.csv (India Post 2026)",
        "pincode_count": len(mapping),
        "pincode_to_state_code": mapping,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(mapping)} pincodes → {OUT_PATH}")
    if unknown_states:
        print("Unknown postal state names (not mapped):", ", ".join(unknown_states))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
