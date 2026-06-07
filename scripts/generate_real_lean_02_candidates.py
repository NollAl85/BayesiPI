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

from benchmark.mathlib_adapter import sample_from_local_mathlib_with_solutions
from benchmark.sorry_project_adapter import sample_from_sorry_project
from harness.schemas import Problem, ReferenceSolution, model_to_jsonable


NO_SOURCES_MESSAGE = (
    "No local real Lean sources found. Provide MATHLIB_ROOT, HTPI_ROOT, "
    "or a local Lake project containing Lean files with sorry."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate real_lean_02 candidates from local real Lean sources.")
    parser.add_argument("--source-discovery", type=Path, required=True)
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2)
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

    sources = _load_discovery(args.source_discovery)
    selected = _select_source(sources, args.source_id)
    if selected is None:
        raise SystemExit(NO_SOURCES_MESSAGE)

    problems, solutions = _generate_from_source(selected, limit=args.limit, seed=args.seed)
    if not problems:
        raise SystemExit(NO_SOURCES_MESSAGE)
    _write_jsonl(args.out_candidates, [model_to_jsonable(problem) for problem in problems])
    _write_jsonl(args.out_solutions, [model_to_jsonable(solution) for solution in solutions])
    print(f"source_id={selected['source_id']}")
    print(f"source_kind={selected['kind']}")
    print(f"candidates={len(problems)}")
    print(f"solutions={len(solutions)}")
    print(f"out_candidates={args.out_candidates}")
    print(f"out_solutions={args.out_solutions}")


def _load_discovery(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Source discovery file not found: {path}") from exc
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
        return [row for row in payload["sources"] if isinstance(row, dict)]
    raise SystemExit(f"Invalid source discovery JSON: expected a list or an object with a sources list: {path}")


def _select_source(sources: list[dict[str, Any]], source_id: str | None) -> dict[str, Any] | None:
    candidates = [_normalize_source(row) for row in sources]
    if source_id:
        for row in candidates:
            if row.get("source_id") == source_id:
                return row if _usable_source(row) else None
        return None
    for row in candidates:
        if row.get("kind") == "mathlib" and row.get("mathlib_root") and _path_exists(row["mathlib_root"]):
            return row
    for row in candidates:
        if row.get("kind") in {"sorry_project", "lake_project"} and int(row.get("sorry_count") or 0) > 0:
            if row.get("project_root") and _path_exists(row["project_root"]):
                return row
    return None


def _generate_from_source(
    source: dict[str, Any], *, limit: int, seed: int
) -> tuple[list[Problem], list[ReferenceSolution]]:
    kind = source["kind"]
    if kind == "mathlib" and source.get("mathlib_root"):
        return sample_from_local_mathlib_with_solutions(
            mathlib_root=Path(source["mathlib_root"]),
            project_root=Path(source["project_root"]) if source.get("project_root") else None,
            limit=limit,
            seed=seed,
            source="real_lean_02_mathlib",
        )
    project_root = Path(source["project_root"])
    problems = sample_from_sorry_project(
        project_root=project_root,
        limit=limit,
        seed=seed,
        source="real_lean_02_sorry_project",
        validate_candidates=bool(source.get("can_run_lake_env_lean")),
    )
    return problems, []


def _usable_source(row: dict[str, Any]) -> bool:
    if row.get("kind") == "mathlib":
        return bool(row.get("mathlib_root")) and _path_exists(row["mathlib_root"])
    return bool(row.get("project_root")) and _path_exists(row["project_root"]) and int(row.get("sorry_count") or 0) > 0


def _normalize_source(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if not normalized.get("kind"):
        normalized["kind"] = "unknown"
    if not normalized.get("source_id"):
        normalized["source_id"] = str(normalized.get("project_root") or normalized.get("mathlib_root") or "unknown")
    return normalized


def _path_exists(value: str) -> bool:
    return Path(value).expanduser().exists()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
