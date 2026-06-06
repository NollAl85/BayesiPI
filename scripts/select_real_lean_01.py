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
    parser.add_argument("--direct-summary", type=Path, required=True)
    parser.add_argument("--uniform-summary", type=Path, default=None)
    parser.add_argument("--solutions", type=Path, default=None)
    parser.add_argument("--out-problems", type=Path, required=True)
    parser.add_argument("--out-solutions", type=Path, default=None)
    parser.add_argument("--out-rejected", type=Path, default=None)
    parser.add_argument("--target-size", type=int, default=20)
    parser.add_argument("--min-survivors", type=int, default=20)
    parser.add_argument("--min-reference-proof-lines", type=int, default=5)
    args = parser.parse_args()

    candidates = load_jsonl(args.candidates)
    direct_rows = _read_summary(args.direct_summary, required_condition="direct")
    uniform_rows = _read_summary(args.uniform_summary, required_condition="uniform") if args.uniform_summary else {}
    solutions = load_solutions_jsonl(args.solutions) if args.solutions else {}

    missing = [problem.problem_id for problem in candidates if problem.problem_id not in direct_rows]
    if missing:
        raise SystemExit(
            "Direct probe summary is incomplete: "
            f"{len(missing)} candidates have no direct row. First missing: {missing[:5]}"
        )

    survivors: list[tuple[tuple[int, str], Problem]] = []
    rejected: list[Problem] = []
    reject_reasons: dict[str, str] = {}
    for problem in candidates:
        reason = _hard_reject_reason(
            problem,
            direct_rows[problem.problem_id],
            solutions.get(problem.problem_id),
            args.min_reference_proof_lines,
        )
        if reason:
            rejected.append(problem)
            reject_reasons[problem.problem_id] = reason
            continue
        survivors.append((_score(problem, direct_rows[problem.problem_id], uniform_rows.get(problem.problem_id)), problem))

    if len(survivors) < args.min_survivors:
        raise SystemExit(
            f"Candidate pool too easy: only {len(survivors)} tasks survived. "
            "Import harder real tasks."
        )

    survivors.sort(key=lambda item: item[0], reverse=True)
    selected = [problem for _, problem in survivors[: args.target_size]]
    remaining = [problem for _, problem in survivors[args.target_size:]]
    rejected.extend(remaining)
    _write_problems(args.out_problems, selected)
    if args.out_solutions:
        selected_solutions = [solutions[problem.problem_id] for problem in selected if problem.problem_id in solutions]
        _write_solutions(args.out_solutions, selected_solutions)
    if args.out_rejected:
        _write_rejected(args.out_rejected, rejected, reject_reasons)

    print(f"survivors={len(survivors)} selected={len(selected)} rejected={len(rejected)}")
    print(f"out_problems={args.out_problems}")


def _read_summary(path: Path | None, required_condition: str) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("condition") != required_condition:
                continue
            rows[row["problem_id"]] = row
    return rows


def _hard_reject_reason(
    problem: Problem,
    direct_row: dict[str, str],
    solution: ReferenceSolution | None,
    min_reference_proof_lines: int,
) -> str | None:
    if _solved(direct_row) and _int_field(direct_row, "lean_calls", 0) <= 1:
        return "direct_low_one_call"
    if _solved(direct_row) and _int_field(direct_row, "rounds", 0) <= 1:
        return "direct_low_one_round"
    proof = direct_row.get("proof") or (solution.reference_proof if solution else "")
    if solution and _proof_lines(solution.reference_proof) < min_reference_proof_lines:
        return "short_reference_proof"
    if _is_trivial_proof(proof):
        return "trivial_proof_shape"
    if _looks_like_exact_theorem_name(problem):
        return "theorem_name_too_revealing"
    return None


def _score(problem: Problem, direct_row: dict[str, str], uniform_row: dict[str, str] | None) -> tuple[int, str]:
    score = 0
    if not _solved(direct_row):
        score += 20
    else:
        score += 8
        score += min(_int_field(direct_row, "rounds", 1), 5)
        score += min(_int_field(direct_row, "lean_calls", 1), 5)
    if uniform_row:
        if not _solved(uniform_row):
            score += 8
        elif _int_field(uniform_row, "lean_calls", 0) > 2:
            score += 3
    return (score, problem.problem_id)


def _solved(row: dict[str, str] | None) -> bool:
    return bool(row) and row.get("solved", "").lower() == "true"


def _int_field(row: dict[str, str] | None, field: str, default: int) -> int:
    if not row or not row.get(field):
        return default
    return int(float(row[field]))


def _proof_lines(proof: str) -> int:
    return sum(1 for line in proof.splitlines() if line.strip())


def _is_trivial_proof(proof: str) -> bool:
    lines = [line.strip() for line in proof.splitlines() if line.strip() and not line.strip().startswith("--")]
    if len(lines) > 2:
        return False
    joined = " ".join(lines)
    trivial_prefixes = ("by rfl", "by simpa", "by omega", "by exact", "rfl", "simpa", "omega", "exact ")
    return any(joined.startswith(prefix) for prefix in trivial_prefixes)


def _looks_like_exact_theorem_name(problem: Problem) -> bool:
    name = (problem.theorem_name or problem.expected_theorem_name or "").lower()
    if not name:
        return False
    revealing_words = ("mem_append", "map_append", "append_assoc", "add_comm", "mul_comm", "rev_append")
    return any(word in name for word in revealing_words)


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


def _write_rejected(path: Path, problems: list[Problem], reject_reasons: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for problem in problems:
            row = model_to_jsonable(problem)
            row["selection_reject_reason"] = reject_reasons.get(problem.problem_id, "not_selected")
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
