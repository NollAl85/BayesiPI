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
from harness.schemas import Problem, ReferenceSolution, model_to_jsonable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--solutions", type=Path, required=True)
    parser.add_argument("--direct-summary", type=Path, default=None)
    parser.add_argument("--uniform-summary", type=Path, default=None)
    parser.add_argument("--out-problems", type=Path, required=True)
    parser.add_argument("--out-solutions", type=Path, required=True)
    parser.add_argument("--out-rejected", type=Path, default=None)
    parser.add_argument("--out-rejected-solutions", type=Path, default=None)
    parser.add_argument("--target-size", type=int, default=20)
    args = parser.parse_args()

    candidates = load_jsonl(args.candidates)
    solutions = load_solutions_jsonl(args.solutions)
    direct = _read_summary(args.direct_summary)
    uniform = _read_summary(args.uniform_summary)

    scored = [
        (_score_candidate(problem, direct.get(problem.problem_id), uniform.get(problem.problem_id)), problem)
        for problem in candidates
        if problem.problem_id in solutions
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [problem for _, problem in scored[: args.target_size]]
    rejected = [problem for _, problem in scored[args.target_size:]]

    _write_problems(args.out_problems, selected)
    _write_solutions(args.out_solutions, [solutions[problem.problem_id] for problem in selected])
    if args.out_rejected:
        _write_problems(args.out_rejected, rejected)
    if args.out_rejected_solutions:
        _write_solutions(args.out_rejected_solutions, [solutions[problem.problem_id] for problem in rejected])

    print(f"selected={len(selected)} rejected={len(rejected)}")
    print(f"out_problems={args.out_problems}")
    print(f"out_solutions={args.out_solutions}")


def _score_candidate(
    problem: Problem,
    direct_row: dict[str, str] | None,
    uniform_row: dict[str, str] | None,
) -> tuple[int, str]:
    direct_solved = _solved(direct_row)
    uniform_solved = _solved(uniform_row)
    direct_rounds = _int_field(direct_row, "rounds", default=1 if direct_row else 0)
    uniform_llm = _int_field(uniform_row, "llm_calls", default=0)
    score = 0
    if direct_row is None:
        score += 2
    elif not direct_solved:
        score += 12
    elif direct_rounds > 1:
        score += 6
    else:
        score += 1
    if uniform_row is None:
        score += 2
    elif not uniform_solved:
        score += 8
    elif uniform_llm > 2:
        score += 3
    else:
        score += 1
    # Stable tie-breaker keeps the selection reproducible without exposing route metadata.
    return (score, problem.problem_id)


def _read_summary(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["problem_id"]: row for row in csv.DictReader(handle)}


def _solved(row: dict[str, str] | None) -> bool:
    return bool(row) and row.get("solved", "").lower() == "true"


def _int_field(row: dict[str, str] | None, field: str, default: int) -> int:
    if not row or not row.get(field):
        return default
    return int(float(row[field]))


def _write_problems(path: Path, problems: list[Problem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for problem in problems:
            handle.write(json.dumps(model_to_jsonable(problem), sort_keys=True) + "\n")


def _write_solutions(path: Path, solutions: list[ReferenceSolution]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for solution in solutions:
            handle.write(json.dumps(model_to_jsonable(solution), sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
