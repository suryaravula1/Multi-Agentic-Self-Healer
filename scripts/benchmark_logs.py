#!/usr/bin/env python3
"""Benchmark parse + diagnose pipeline against local log fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from self_healer.heuristics import diagnose_heuristic, parse_logs_heuristic
from self_healer.models.schemas import HealRequest
from self_healer.orchestrator import HealingPipeline

FIXTURE_DIRS = [
    ROOT / "fixtures" / "sample_logs",
    ROOT / "fixtures" / "loghub",
]


def iter_log_files() -> list[Path]:
    files: list[Path] = []
    for directory in FIXTURE_DIRS:
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.log")))
    return files


def benchmark_file(path: Path, use_llm: bool) -> dict:
    logs = path.read_text(errors="replace")
    if len(logs) > 50_000:
        logs = logs[:50_000]

    if use_llm:
        result = HealingPipeline().run(HealRequest(logs=logs, auto_execute=False))
        return {
            "file": path.name,
            "source": result.parse.source.value if result.parse else None,
            "signatures": len(result.parse.error_signatures) if result.parse else 0,
            "category": result.diagnosis.failure_category if result.diagnosis else None,
            "confidence": result.diagnosis.confidence if result.diagnosis else None,
            "steps": len(result.plan.steps) if result.plan else 0,
            "stage": result.stage_reached.value,
        }

    parsed = parse_logs_heuristic(logs)
    diagnosis = diagnose_heuristic(parsed)
    return {
        "file": path.name,
        "source": parsed.source.value,
        "signatures": len(parsed.error_signatures),
        "category": diagnosis.failure_category,
        "confidence": diagnosis.confidence,
        "events": len(parsed.events),
    }


def main() -> None:
    use_llm = "--llm" in sys.argv
    files = iter_log_files()

    if not files:
        print("No .log files found. Run: bash scripts/fetch_loghub_sample.sh")
        sys.exit(1)

    print(f"Mode: {'LLM' if use_llm else 'heuristic'}")
    print(f"Files: {len(files)}\n")

    results = [benchmark_file(path, use_llm) for path in files]
    print(json.dumps(results, indent=2))

    categories = {r["category"] for r in results if r.get("category")}
    print(f"\nCategories detected: {', '.join(sorted(categories)) or 'none'}")


if __name__ == "__main__":
    main()
