#!/usr/bin/env python3
"""Print concise summary from retrieval benchmark JSON response."""

from __future__ import annotations

import json
import sys


def _refs(trace: dict, top: int = 3) -> list[str]:
    scores = trace.get("retrieval_scores", [])
    refs = [
        item.get("reference", "")
        for item in scores
        if isinstance(item, dict) and item.get("reference")
    ]
    return refs[:top]


def _mode(trace: dict) -> str:
    return str(trace.get("retrieval_mode", "unknown"))


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("No input JSON received on stdin.")
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON input: {exc}")
        return 1

    if payload.get("mode") != "benchmark":
        print("Not a benchmark payload. Raw mode:", payload.get("mode"))
        return 1

    semantic = payload.get("semantic", {})
    hybrid = payload.get("hybrid", {})
    semantic_refs = _refs(semantic)
    hybrid_refs = _refs(hybrid)
    overlap = sorted(set(semantic_refs) & set(hybrid_refs))

    print("Retrieval Benchmark Summary")
    print("---------------------------")
    print(f"semantic mode : {_mode(semantic)}")
    print(f"hybrid mode   : {_mode(hybrid)}")
    print(f"semantic top  : {', '.join(semantic_refs) or 'none'}")
    print(f"hybrid top    : {', '.join(hybrid_refs) or 'none'}")
    print(f"overlap refs  : {', '.join(overlap) or 'none'}")

    semantic_themes = semantic.get("query_themes", [])
    hybrid_themes = hybrid.get("query_themes", [])
    themes = semantic_themes or hybrid_themes
    if themes:
        print(f"query themes  : {', '.join(themes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
