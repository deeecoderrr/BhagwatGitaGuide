"""Path to the normalized ITR JSON Schema (exchange / validation with external tools)."""
from __future__ import annotations

import pathlib

_SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "schemas" / "normalized_itr.json"


def normalized_itr_schema_path() -> pathlib.Path:
    return _SCHEMA
