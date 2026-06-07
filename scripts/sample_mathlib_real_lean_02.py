from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from benchmark.mathlib_adapter import (
    DEFAULT_REAL02_PREFIXES,
    sample_from_local_mathlib_with_solutions,
)
from harness.schemas import model_to_jsonable


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample anonymized real_lean_02 theorem reconstruction candidates from a local Mathlib checkout."
    )
    parser.add_argument("mathlib_root", type=Path, help="Local Mathlib directory or Lake project root containing Mathlib.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--project-root", type=Path, default=None, help="Lake project root used for local Lean checking.")
    parser.add_argument("--validate-candidates", action="store_true", help="Run reference and anti-leak Lean checks.")
    parser.add_argument("--lean-timeout-seconds", type=int, default=90)
    parser.add_argument(
        "--module-prefix",
        action="append",
        default=None,
        help="Mathlib module prefix to sample. Repeat to override the default real_lean_02 prefix set.",
    )
    parser.add_argument(
        "--out-candidates",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "candidates" / "real_lean_02_candidates.jsonl",
    )
    parser.add_argument(
        "--out-solutions",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "solutions" / "real_lean_02_solutions.jsonl",
    )
    args = parser.parse_args()

    prefixes = tuple(args.module_prefix or DEFAULT_REAL02_PREFIXES)
    problems, solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=args.mathlib_root,
        limit=args.limit,
        seed=args.seed,
        module_prefixes=prefixes,
        project_root=args.project_root,
        validate_candidates=args.validate_candidates,
        lean_timeout_seconds=args.lean_timeout_seconds,
    )
    _write_jsonl(args.out_candidates, [model_to_jsonable(problem) for problem in problems])
    _write_jsonl(args.out_solutions, [model_to_jsonable(solution) for solution in solutions])
    print(f"candidates={len(problems)}")
    print(f"solutions={len(solutions)}")
    print(f"out_candidates={args.out_candidates}")
    print(f"out_solutions={args.out_solutions}")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
