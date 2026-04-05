"""Evaluate retrieval quality against a labeled prompt dataset."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from guide_api.services import (
    detect_themes,
    retrieve_hybrid_verses_with_trace,
    retrieve_semantic_verses_with_trace,
    retrieve_verses_with_trace,
)


class Command(BaseCommand):
    """Management command for retrieval hit-rate measurement."""

    help = "Evaluate retrieval quality from prompts and expected references."

    def add_arguments(self, parser):
        """Define dataset path, retrieval mode, and scoring options."""
        parser.add_argument(
            "--file",
            default="data/retrieval_eval_cases.json",
            help="Path to eval JSON file.",
        )
        parser.add_argument(
            "--mode",
            default="pipeline",
            choices=["pipeline", "semantic", "hybrid"],
            help="Retrieval mode to evaluate.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=3,
            help="Top-k retrieval limit used during evaluation.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail command if any case misses expected references.",
        )
        parser.add_argument(
            "--report-misses",
            action="store_true",
            help="Print miss clusters by inferred theme and references.",
        )

    def handle(self, *args, **options):
        """Load cases, execute retrieval, and print summary metrics."""
        file_path = Path(options["file"])
        mode = options["mode"]
        limit = options["limit"]
        strict = options["strict"]
        report_misses = options["report_misses"]

        if not file_path.exists():
            raise CommandError(f"Eval file not found: {file_path}")

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid eval JSON: {exc}") from exc

        if not isinstance(payload, list):
            raise CommandError("Eval JSON must be a list of case objects.")
        if not payload:
            raise CommandError("Eval dataset is empty.")

        misses = 0
        case_results = []

        for idx, case in enumerate(payload, start=1):
            prompt, expected_refs = self._validate_case(case, idx)
            retrieval = self._run_retrieval(
                mode=mode,
                prompt=prompt,
                limit=limit,
            )
            actual_refs = [
                row.get("reference", "")
                for row in retrieval.retrieval_scores
            ]
            actual_refs = [ref for ref in actual_refs if ref]
            expected_set = set(expected_refs)
            actual_set = set(actual_refs)
            matched = sorted(expected_set & actual_set)
            is_hit = bool(matched)
            if not is_hit:
                misses += 1

            case_results.append(
                {
                    "index": idx,
                    "prompt": prompt,
                    "expected": expected_refs,
                    "actual_topk": actual_refs,
                    "matched": matched,
                    "hit": is_hit,
                    "retrieval_mode": retrieval.retrieval_mode,
                }
            )

        total = len(case_results)
        hits = total - misses
        hit_rate = round(hits / total, 4)
        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Retrieval eval complete. mode={mode} cases={total} "
                    f"hits={hits} misses={misses} hit_rate={hit_rate}"
                )
            )
        )

        for result in case_results:
            marker = "HIT" if result["hit"] else "MISS"
            self.stdout.write(
                (
                    f"[{marker}] case={result['index']} "
                    f"retrieval_mode={result['retrieval_mode']} "
                    f"expected={result['expected']} "
                    f"actual_topk={result['actual_topk']} "
                    f"matched={result['matched']}"
                )
            )

        if report_misses:
            self._print_miss_report(case_results)

        if strict and misses > 0:
            raise CommandError(
                (
                    "Retrieval evaluation failed in strict mode. "
                    f"misses={misses} out of {total}."
                )
            )

    @staticmethod
    def _validate_case(case: object, index: int) -> tuple[str, list[str]]:
        """Return validated prompt and expected references for one case."""
        if not isinstance(case, dict):
            raise CommandError(f"Case {index} is not an object.")
        prompt = str(case.get("prompt", "")).strip()
        expected_refs = case.get("expected_references", [])
        if not prompt:
            raise CommandError(f"Case {index} is missing non-empty prompt.")
        if not isinstance(expected_refs, list) or not expected_refs:
            raise CommandError(
                f"Case {index} must include expected_references list.",
            )
        cleaned = [
            str(ref).strip()
            for ref in expected_refs
            if str(ref).strip()
        ]
        if not cleaned:
            raise CommandError(
                f"Case {index} expected_references has no valid entries.",
            )
        return prompt, cleaned

    @staticmethod
    def _run_retrieval(*, mode: str, prompt: str, limit: int):
        """Dispatch retrieval mode runner and return trace object."""
        if mode == "semantic":
            return retrieve_semantic_verses_with_trace(
                message=prompt,
                limit=limit,
            )
        if mode == "hybrid":
            return retrieve_hybrid_verses_with_trace(
                message=prompt,
                limit=limit,
            )
        return retrieve_verses_with_trace(message=prompt, limit=limit)

    def _print_miss_report(self, case_results: list[dict]) -> None:
        """Print clustered miss diagnostics to guide scoring iteration."""
        misses = [item for item in case_results if not item["hit"]]
        if not misses:
            self.stdout.write("Miss report: no misses.")
            return

        theme_counter: Counter[str] = Counter()
        reference_counter: Counter[str] = Counter()

        for miss in misses:
            prompt = miss["prompt"]
            themes = sorted(detect_themes(prompt))
            if themes:
                theme_counter.update(themes)
            else:
                theme_counter.update(["unclassified"])

            expected = miss.get("expected", [])
            matched = set(miss.get("matched", []))
            missed_refs = [ref for ref in expected if ref not in matched]
            reference_counter.update(missed_refs)

        self.stdout.write("Miss report:")
        theme_line = ", ".join(
            f"{theme}={count}"
            for theme, count in theme_counter.most_common(8)
        )
        self.stdout.write(f"  themes: {theme_line}")
        refs_line = ", ".join(
            f"{ref}={count}"
            for ref, count in reference_counter.most_common(12)
        )
        self.stdout.write(f"  top_missing_refs: {refs_line}")
