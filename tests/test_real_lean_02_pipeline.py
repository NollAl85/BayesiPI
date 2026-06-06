from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from benchmark.mathlib_adapter import sample_from_local_mathlib_with_solutions
from harness.schemas import Problem, ReferenceSolution, model_to_jsonable


def test_mathlib_sampler_anonymizes_public_payload(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "LinearAlgebra"
    source_dir.mkdir(parents=True)
    (source_dir / "Hard.lean").write_text(
        """namespace LinearAlgebra
open scoped BigOperators
variable {R M : Type*}

theorem original_route_name (x : Nat) : x = x := by
  have h1 : x = x := rfl
  have h2 : x = x := h1
  have h3 : x = x := h2
  have h4 : x = x := h3
  have h5 : x = x := h4
  have h6 : x = x := h5
  have h7 : x = x := h6
  have h8 : x = x := h7
  exact h8
end LinearAlgebra
""",
        encoding="utf-8",
    )

    problems, solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("LinearAlgebra",),
    )

    assert len(problems) == 1
    assert len(solutions) == 1
    public_blob = json.dumps(model_to_jsonable(problems[0]), sort_keys=True)
    assert problems[0].theorem_name == "real02_target_001"
    assert problems[0].expected_theorem_name == "real02_target_001"
    assert problems[0].module_path is None
    assert "original_route_name" not in public_blob
    assert "Mathlib/LinearAlgebra/Hard" not in public_blob
    assert solutions[0].metadata["original_theorem_name"] == "original_route_name"
    assert solutions[0].metadata["source_module"] == "Mathlib/LinearAlgebra/Hard"


def test_real_lean_02_selector_rejects_easy_candidates(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    solutions = tmp_path / "solutions.jsonl"
    direct_summary = tmp_path / "direct.csv"
    uniform_summary = tmp_path / "uniform.csv"
    out_problems = tmp_path / "selected.jsonl"
    out_solutions = tmp_path / "selected_solutions.jsonl"
    out_rejected = tmp_path / "rejected.jsonl"
    out_direct_failed = tmp_path / "direct_failed.jsonl"
    out_uniform_failed = tmp_path / "uniform_failed.jsonl"

    hard = _problem("real_lean_02_001")
    easy = _problem("real_lean_02_002")
    _write_jsonl(candidates, [model_to_jsonable(hard), model_to_jsonable(easy)])
    _write_jsonl(
        solutions,
        [
            model_to_jsonable(_solution("real_lean_02_001")),
            model_to_jsonable(_solution("real_lean_02_002")),
        ],
    )
    _write_summary(
        direct_summary,
        [
            {"problem_id": "real_lean_02_001", "condition": "direct", "solved": "False", "rounds": "3"},
            {"problem_id": "real_lean_02_002", "condition": "direct", "solved": "True", "rounds": "1"},
        ],
    )
    _write_summary(
        uniform_summary,
        [
            {"problem_id": "real_lean_02_001", "condition": "uniform", "solved": "False", "rounds": "2"},
            {"problem_id": "real_lean_02_002", "condition": "uniform", "solved": "True", "rounds": "1"},
        ],
    )

    completed = subprocess.run(
        [
            "python3",
            "scripts/select_real_lean_02.py",
            "--candidates",
            str(candidates),
            "--solutions",
            str(solutions),
            "--direct-full-summary",
            str(direct_summary),
            "--uniform-constrained-summary",
            str(uniform_summary),
            "--out-problems",
            str(out_problems),
            "--out-solutions",
            str(out_solutions),
            "--out-rejected",
            str(out_rejected),
            "--out-direct-full-failed",
            str(out_direct_failed),
            "--out-uniform-constrained-failed",
            str(out_uniform_failed),
            "--target-size",
            "1",
            "--min-survivors",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "selected=1" in completed.stdout
    selected = [json.loads(line) for line in out_problems.read_text(encoding="utf-8").splitlines()]
    rejected = [json.loads(line) for line in out_rejected.read_text(encoding="utf-8").splitlines()]
    uniform_failed = [json.loads(line) for line in out_uniform_failed.read_text(encoding="utf-8").splitlines()]
    assert [row["problem_id"] for row in selected] == ["real_lean_02_001"]
    assert rejected[0]["selection_reject_reason"] == "direct_full_solved"
    assert [row["problem_id"] for row in uniform_failed] == ["real_lean_02_001"]


def _problem(problem_id: str) -> Problem:
    suffix = problem_id.rsplit("_", 1)[-1]
    theorem_name = f"real02_target_{suffix}"
    return Problem(
        problem_id=problem_id,
        source="real_lean_02_mathlib",
        theorem_name=theorem_name,
        statement=f"theorem {theorem_name} (x : Nat) : x = x := {{{{proof}}}}",
        task_type="file_with_hole",
        full_lean_source=f"import Mathlib\n\ntheorem {theorem_name} (x : Nat) : x = x := {{{{proof}}}}\n",
        expected_theorem_name=theorem_name,
        metadata={"anonymized": True},
    )


def _solution(problem_id: str) -> ReferenceSolution:
    proof = """by
  have h1 : x = x := rfl
  have h2 : x = x := h1
  have h3 : x = x := h2
  have h4 : x = x := h3
  have h5 : x = x := h4
  have h6 : x = x := h5
  have h7 : x = x := h6
  exact h7"""
    return ReferenceSolution(
        problem_id=problem_id,
        reference_proof=proof,
        metadata={
            "original_theorem_name": f"private_name_{problem_id}",
            "source_module": "Mathlib/LinearAlgebra/Fake",
        },
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_summary(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "run_id",
        "problem_id",
        "condition",
        "solved",
        "wall_time",
        "lean_calls",
        "llm_calls",
        "estimated_tokens",
        "rounds",
        "notes",
        "proof",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = {
                "run_id": "test",
                "wall_time": "1.0",
                "lean_calls": "1",
                "llm_calls": "1",
                "estimated_tokens": "1",
                "notes": "",
                "proof": "",
            }
            payload.update(row)
            writer.writerow(payload)
