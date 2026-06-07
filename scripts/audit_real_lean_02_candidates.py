from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from benchmark.benchmark import load_jsonl, load_solutions_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit real_lean_02 candidates for theorem leakage.")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "candidates" / "real_lean_02_candidates.jsonl",
    )
    parser.add_argument(
        "--solutions",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "solutions" / "real_lean_02_solutions.jsonl",
    )
    parser.add_argument("--direct-one-shot-summary", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "logs" / "real_lean_02_leak_audit.csv")
    args = parser.parse_args()

    candidates = load_jsonl(args.candidates)
    solutions = load_solutions_jsonl(args.solutions) if args.solutions.exists() else {}
    direct_one_shot = _read_direct_one_shot(args.direct_one_shot_summary) if args.direct_one_shot_summary else {}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "problem_id",
            "source",
            "original_theorem_name_private",
            "public_theorem_name",
            "imports_mathlib",
            "original_theorem_available",
            "reference_compiles",
            "direct_one_shot_solved",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for problem in candidates:
            solution = solutions.get(problem.problem_id)
            metadata = solution.metadata if solution else {}
            writer.writerow(
                {
                    "problem_id": problem.problem_id,
                    "source": problem.source,
                    "original_theorem_name_private": metadata.get("original_theorem_name", ""),
                    "public_theorem_name": problem.theorem_name or "",
                    "imports_mathlib": _imports_mathlib(problem),
                    "original_theorem_available": metadata.get("original_theorem_available", ""),
                    "reference_compiles": metadata.get("reference_compiles", ""),
                    "direct_one_shot_solved": direct_one_shot.get(problem.problem_id, ""),
                }
            )
    print(f"out={args.out}")


def _imports_mathlib(problem) -> bool:
    source = "\n".join(problem.imports or [])
    if problem.full_lean_source:
        source += "\n" + problem.full_lean_source
    return any(line.strip() == "import Mathlib" for line in source.splitlines())


def _read_direct_one_shot(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("condition") == "direct":
                rows[row["problem_id"]] = row.get("solved", "")
    return rows


if __name__ == "__main__":
    main()
