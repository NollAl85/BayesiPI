from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from benchmark.benchmark import load_jsonl, load_solutions_jsonl
from harness.lean_runner import LeanRunner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark_jsonl", type=Path)
    parser.add_argument("--solutions", type=Path, required=True)
    parser.add_argument("--lean-timeout-seconds", type=int, default=10)
    args = parser.parse_args()

    problems = load_jsonl(args.benchmark_jsonl)
    solutions = load_solutions_jsonl(args.solutions)
    runner = LeanRunner(["lean"], timeout_seconds=args.lean_timeout_seconds)

    failures: list[str] = []
    for problem in problems:
        solution = solutions.get(problem.problem_id)
        if solution is None:
            failures.append(f"{problem.problem_id}: missing reference proof")
            print(f"FAIL {problem.problem_id}: missing reference proof")
            continue
        result = runner.check(problem, solution.reference_proof)
        if result.success:
            print(f"PASS {problem.problem_id}")
        else:
            failures.append(f"{problem.problem_id}: {result.error_summary}")
            print(f"FAIL {problem.problem_id}: {result.error_summary}")

    extra_solutions = sorted(set(solutions) - {problem.problem_id for problem in problems})
    for problem_id in extra_solutions:
        failures.append(f"{problem_id}: solution has no public problem")
        print(f"FAIL {problem_id}: solution has no public problem")

    print(f"checked={len(problems)} failed={len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

