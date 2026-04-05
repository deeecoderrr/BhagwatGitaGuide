#!/usr/bin/env python3
"""Extract auth token from JSON payload read on stdin."""

from __future__ import annotations

import json
import sys


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("")
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("")
        return 0

    token = payload.get("token", "") if isinstance(payload, dict) else ""
    print(token if isinstance(token, str) else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
