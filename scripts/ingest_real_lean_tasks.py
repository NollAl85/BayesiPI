from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from harness.schemas import Problem, ReferenceSolution, model_to_jsonable


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert generic local real-Lean task JSONL into benchmark problem/solution JSONL."
    )
    parser.add_argument("inputs", type=Path, nargs="+", help="Input JSONL files in the generic real-task format.")
    parser.add_argument("--out-problems", type=Path, required=True)
    parser.add_argument("--out-solutions", type=Path, default=None)
    args = parser.parse_args()

    problems: list[Problem] = []
    solutions: list[ReferenceSolution] = []
    seen: set[str] = set()
    for input_path in args.inputs:
        for row in _read_jsonl(input_path):
            problem, solution = _convert_row(row, input_path.parent)
            if problem.problem_id in seen:
                raise ValueError(f"Duplicate problem_id={problem.problem_id!r}")
            seen.add(problem.problem_id)
            problems.append(problem)
            if solution is not None:
                solutions.append(solution)

    _write_jsonl(args.out_problems, [model_to_jsonable(problem) for problem in problems])
    if args.out_solutions:
        _write_jsonl(args.out_solutions, [model_to_jsonable(solution) for solution in solutions])
    print(f"problems={len(problems)}")
    print(f"solutions={len(solutions)}")
    print(f"out_problems={args.out_problems}")
    if args.out_solutions:
        print(f"out_solutions={args.out_solutions}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
    return rows


def _convert_row(row: dict[str, Any], base_dir: Path) -> tuple[Problem, ReferenceSolution | None]:
    full_lean_source = row.get("full_lean_source")
    source_path = row.get("full_lean_source_path")
    if source_path:
        full_lean_source = _read_source_path(base_dir, str(source_path))
    statement = str(row.get("statement") or "").strip()
    if not statement and full_lean_source:
        statement = _summarize_source(full_lean_source)
    problem = Problem(
        problem_id=str(row["problem_id"]),
        source=str(row.get("source") or "real_lean"),
        theorem_name=row.get("theorem_name"),
        imports=_string_list(row.get("imports")),
        statement=statement,
        task_type=str(row.get("task_type") or ("file_with_hole" if full_lean_source else "statement")),
        preamble=str(row.get("context") or row.get("preamble") or ""),
        full_lean_source=full_lean_source,
        proof_placeholder=str(row.get("proof_placeholder") or "{{proof}}"),
        project_root=row.get("project_root"),
        module_path=row.get("module_path"),
        expected_theorem_name=row.get("expected_theorem_name") or row.get("theorem_name"),
        metadata=dict(row.get("metadata") or {}),
    )
    reference_proof = row.get("reference_proof")
    if reference_proof is None:
        return problem, None
    solution = ReferenceSolution(
        problem_id=problem.problem_id,
        reference_proof=str(reference_proof).strip(),
        metadata=dict(row.get("solution_metadata") or {}),
    )
    return problem, solution


def _read_source_path(base_dir: Path, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.read_text(encoding="utf-8")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _summarize_source(source: str) -> str:
    lines = [line.rstrip() for line in source.splitlines() if line.strip()]
    return "\n".join(lines[:20])


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
