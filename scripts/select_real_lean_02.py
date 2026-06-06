from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from benchmark.benchmark import load_jsonl, load_solutions_jsonl
from benchmark.mathlib_adapter import meaningful_proof_lines
from harness.schemas import Problem, ReferenceSolution, model_to_jsonable


TRIVIAL_PROOF_RE = re.compile(r"^\s*by\s+(?:exact|simpa|simp|rfl|omega)\b|^\s*(?:exact|simpa|simp|rfl|omega)\b")
PUBLIC_NAME_RE = re.compile(r"^real02_target_\d{3,}$")
PRIVATE_METADATA_KEYS = {"original_theorem_name", "source_module", "source_path"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Select difficult real_lean_02 benchmark tasks from probe results.")
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
    parser.add_argument("--direct-full-summary", type=Path, required=True)
    parser.add_argument("--uniform-constrained-summary", type=Path, required=True)
    parser.add_argument(
        "--out-problems",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "problems" / "real_lean_02.jsonl",
    )
    parser.add_argument(
        "--out-solutions",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "solutions" / "real_lean_02_selected_solutions.jsonl",
    )
    parser.add_argument(
        "--out-rejected",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "candidates" / "real_lean_02_rejected.jsonl",
    )
    parser.add_argument(
        "--out-direct-full-failed",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "problems" / "real_lean_02_direct_full_failed.jsonl",
    )
    parser.add_argument(
        "--out-uniform-constrained-failed",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "problems" / "real_lean_02_uniform_constrained_failed.jsonl",
    )
    parser.add_argument("--target-size", type=int, default=20)
    parser.add_argument("--min-survivors", type=int, default=20)
    parser.add_argument("--min-reference-proof-lines", type=int, default=8)
    parser.add_argument("--max-reference-check-seconds", type=float, default=90.0)
    args = parser.parse_args()

    candidates = load_jsonl(args.candidates)
    solutions = load_solutions_jsonl(args.solutions)
    direct_full = _read_summary(args.direct_full_summary, "direct")
    uniform = _read_summary(args.uniform_constrained_summary, "uniform")
    _require_complete(candidates, direct_full, "direct_full")
    _require_complete(candidates, uniform, "uniform_constrained")

    survivors: list[tuple[tuple[int, str], Problem]] = []
    rejected: list[tuple[Problem, str]] = []
    for problem in candidates:
        solution = solutions.get(problem.problem_id)
        reason = _hard_reject_reason(
            problem=problem,
            solution=solution,
            direct_full=direct_full[problem.problem_id],
            uniform=uniform[problem.problem_id],
            min_reference_proof_lines=args.min_reference_proof_lines,
            max_reference_check_seconds=args.max_reference_check_seconds,
        )
        if reason:
            rejected.append((problem, reason))
            continue
        survivors.append((_score(problem, solution, uniform[problem.problem_id]), problem))

    if len(survivors) < args.min_survivors:
        _write_rejected(args.out_rejected, rejected)
        raise SystemExit(f"Candidate pool too easy: only {len(survivors)} survived. Sample harder modules.")

    survivors.sort(key=lambda item: item[0], reverse=True)
    selected = [problem for _, problem in survivors[: args.target_size]]
    selected_solutions = [solutions[problem.problem_id] for problem in selected if problem.problem_id in solutions]
    direct_failed = [problem for problem in selected if not _solved(direct_full[problem.problem_id])]
    uniform_failed = [problem for problem in selected if not _solved(uniform[problem.problem_id])]

    _write_problems(args.out_problems, selected)
    _write_solutions(args.out_solutions, selected_solutions)
    _write_problems(args.out_direct_full_failed, direct_failed)
    _write_problems(args.out_uniform_constrained_failed, uniform_failed)
    _write_rejected(args.out_rejected, rejected)
    print(f"survivors={len(survivors)}")
    print(f"selected={len(selected)}")
    print(f"direct_full_failed_selected={len(direct_failed)}")
    print(f"uniform_constrained_failed_selected={len(uniform_failed)}")
    print(f"out_problems={args.out_problems}")


def _hard_reject_reason(
    *,
    problem: Problem,
    solution: ReferenceSolution | None,
    direct_full: dict[str, str],
    uniform: dict[str, str],
    min_reference_proof_lines: int,
    max_reference_check_seconds: float,
) -> str | None:
    if _solved(direct_full):
        return "direct_full_solved"
    if _solved(uniform) and _int_field(uniform, "rounds", 0) <= 1:
        return "uniform_constrained_one_round_solved"
    if solution is None:
        return "missing_reference_solution"
    proof = solution.reference_proof
    if meaningful_proof_lines(proof) < min_reference_proof_lines:
        return "short_reference_proof"
    if TRIVIAL_PROOF_RE.search(proof.strip()):
        return "trivial_reference_proof"
    if _public_payload_leaks_private_source(problem):
        return "public_payload_leaks_private_source"
    if _statement_obviously_names_theorem(problem, solution):
        return "statement_identifies_theorem"
    check_seconds = float(solution.metadata.get("reference_check_seconds") or 0.0)
    if check_seconds > max_reference_check_seconds:
        return "slow_reference_check"
    return None


def _public_payload_leaks_private_source(problem: Problem) -> bool:
    if not problem.theorem_name or not PUBLIC_NAME_RE.match(problem.theorem_name):
        return True
    if problem.expected_theorem_name and problem.expected_theorem_name != problem.theorem_name:
        return True
    if problem.module_path:
        return True
    if problem.imports and problem.imports != ["Mathlib"]:
        return True
    lowered = json.dumps(problem.metadata, sort_keys=True).lower()
    return any(key in lowered for key in PRIVATE_METADATA_KEYS)


def _statement_obviously_names_theorem(problem: Problem, solution: ReferenceSolution) -> bool:
    original_name = str(solution.metadata.get("original_theorem_name") or "").lower()
    if not original_name:
        return False
    public_text = f"{problem.statement}\n{problem.full_lean_source or ''}".lower()
    return original_name in public_text


def _score(problem: Problem, solution: ReferenceSolution | None, uniform: dict[str, str]) -> tuple[int, str]:
    score = 0
    if not _solved(uniform):
        score += 50
    else:
        score += min(_int_field(uniform, "lean_calls", 1), 8)
        score += min(_int_field(uniform, "rounds", 1), 4)
    if solution:
        proof_lines = meaningful_proof_lines(solution.reference_proof)
        if 8 <= proof_lines <= 40:
            score += 20
        else:
            score += max(0, 20 - abs(proof_lines - 24))
        score += min(_distinct_tactic_count(solution.reference_proof), 10)
    return (score, problem.problem_id)


def _distinct_tactic_count(proof: str) -> int:
    tactic_words = set()
    for line in proof.splitlines():
        stripped = line.strip(" ·{}()")
        if not stripped:
            continue
        tactic_words.add(stripped.split()[0])
    return len(tactic_words)


def _read_summary(path: Path, condition: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("condition") == condition:
                rows[row["problem_id"]] = row
    return rows


def _require_complete(problems: list[Problem], rows: dict[str, dict[str, str]], label: str) -> None:
    missing = [problem.problem_id for problem in problems if problem.problem_id not in rows]
    if missing:
        raise SystemExit(f"{label} probe summary is incomplete: missing {len(missing)} rows; first={missing[:5]}")


def _solved(row: dict[str, str]) -> bool:
    return row.get("solved", "").lower() == "true"


def _int_field(row: dict[str, str], field: str, default: int) -> int:
    if row.get(field) in (None, ""):
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


def _write_rejected(path: Path, rejected: list[tuple[Problem, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for problem, reason in rejected:
            row = model_to_jsonable(problem)
            row["selection_reject_reason"] = reason
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
