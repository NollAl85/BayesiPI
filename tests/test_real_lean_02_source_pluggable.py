from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest

from benchmark.sorry_project_adapter import sample_from_sorry_project
from harness.schemas import Problem, model_to_jsonable
from scripts.discover_real_lean_sources import discover_sources


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_source_discovery_detects_fake_lake_project_and_sorry_count(tmp_path: Path) -> None:
    project = _fake_sorry_project(tmp_path / "lean_project")

    sources = discover_sources([tmp_path, tmp_path / "missing"], check_lake=False)

    project_record = next(row for row in sources if row["project_root"] == str(project))
    assert project_record["kind"] == "sorry_project"
    assert project_record["sorry_count"] == 1
    assert project_record["lean_toolchain"] == "leanprover/lean4:v4.12.0"
    assert project_record["can_run_lake_env_lean"] is False
    assert project_record["local_sorry_tasks_available"] is True
    assert project_record["mathlib_prefix_reconstruction_possible"] is False
    assert any(path.endswith("Hard.lean") for path in project_record["lean_files"])


def test_source_discovery_detects_fake_mathlib_directory(tmp_path: Path) -> None:
    mathlib = tmp_path / "mathlib_checkout" / "Mathlib"
    (mathlib / "Data").mkdir(parents=True)
    (mathlib / "Data" / "Hard.lean").write_text("theorem mathlib_like : True := by trivial\n", encoding="utf-8")

    sources = discover_sources([tmp_path], check_lake=False)

    mathlib_records = [row for row in sources if row["kind"] == "mathlib"]
    assert len(mathlib_records) == 1
    assert mathlib_records[0]["mathlib_root"] == str(mathlib)
    assert mathlib_records[0]["theorem_lemma_count"] == 1
    assert mathlib_records[0]["mathlib_prefix_reconstruction_possible"] is False
    assert mathlib_records[0]["local_sorry_tasks_available"] is False


def test_source_discovery_handles_missing_roots_gracefully(tmp_path: Path) -> None:
    assert discover_sources([tmp_path / "does_not_exist"], check_lake=False) == []


def test_sorry_project_extraction_public_safe_file_with_hole(tmp_path: Path) -> None:
    project = _fake_sorry_project(tmp_path / "lean_project")

    problems = sample_from_sorry_project(project_root=project, limit=1, validate_candidates=False)

    assert len(problems) == 1
    problem = problems[0]
    public_blob = json.dumps(problem.public_payload(), sort_keys=True)
    assert problem.problem_id == "real_lean_02_001"
    assert problem.theorem_name == "real02_target_001"
    assert problem.expected_theorem_name == "real02_target_001"
    assert problem.task_type == "file_with_hole"
    assert problem.project_root == str(project)
    assert problem.module_path is None
    assert problem.full_lean_source is not None
    assert "{{proof}}" in problem.full_lean_source
    assert "original_hard_route" not in public_blob
    assert str(project / "Hard.lean") not in public_blob
    assert "reference_proof" not in public_blob
    assert "hidden_reference_proof" not in public_blob


def test_candidate_generation_fails_clearly_without_sources(tmp_path: Path) -> None:
    discovery = tmp_path / "empty.json"
    discovery.write_text("[]\n", encoding="utf-8")

    completed = subprocess.run(
        [
            "python3",
            "scripts/generate_real_lean_02_candidates.py",
            "--source-discovery",
            str(discovery),
            "--out-candidates",
            str(tmp_path / "candidates.jsonl"),
            "--out-solutions",
            str(tmp_path / "solutions.jsonl"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "No usable local real Lean sources found" in completed.stderr


def test_candidate_generation_uses_fake_sorry_project_without_mathlib(tmp_path: Path) -> None:
    project = _fake_sorry_project(tmp_path / "lean_project")
    discovery = tmp_path / "sources.json"
    discovery.write_text(
        json.dumps(
            [
                {
                    "source_id": "fake_sorry",
                    "kind": "sorry_project",
                    "project_root": str(project),
                    "mathlib_root": None,
                    "lean_files": [str(project / "Hard.lean")],
                    "sorry_count": 1,
                    "lean_toolchain": "leanprover/lean4:v4.12.0",
                    "can_run_lake_env_lean": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.jsonl"
    solutions = tmp_path / "solutions.jsonl"

    completed = subprocess.run(
        [
            "python3",
            "scripts/generate_real_lean_02_candidates.py",
            "--source-discovery",
            str(discovery),
            "--limit",
            "1",
            "--out-candidates",
            str(candidates),
            "--out-solutions",
            str(solutions),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    rows = _read_jsonl(candidates)
    assert "source_kind=sorry_project" in completed.stdout
    assert len(rows) == 1
    assert rows[0]["problem_id"] == "real_lean_02_001"
    assert rows[0]["expected_theorem_name"] == "real02_target_001"
    assert "original_hard_route" not in json.dumps(rows[0], sort_keys=True)
    assert solutions.read_text(encoding="utf-8") == ""


def test_selector_rejects_direct_one_shot_and_fails_loudly(tmp_path: Path) -> None:
    candidate = _selector_problem("real_lean_02_001")
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(candidates, [model_to_jsonable(candidate)])
    direct_full = tmp_path / "direct_full.csv"
    uniform = tmp_path / "uniform.csv"
    direct_one_shot = tmp_path / "direct_one_shot.csv"
    _write_summary(direct_full, [{"problem_id": candidate.problem_id, "condition": "direct", "solved": "False"}])
    _write_summary(uniform, [{"problem_id": candidate.problem_id, "condition": "uniform", "solved": "False"}])
    _write_summary(
        direct_one_shot,
        [
            {
                "problem_id": candidate.problem_id,
                "condition": "direct",
                "solved": "True",
                "lean_calls": "1",
            }
        ],
    )

    completed = subprocess.run(
        [
            "python3",
            "scripts/select_real_lean_02.py",
            "--candidates",
            str(candidates),
            "--solutions",
            str(tmp_path / "missing_solutions.jsonl"),
            "--direct-full-summary",
            str(direct_full),
            "--uniform-constrained-summary",
            str(uniform),
            "--direct-one-shot-summary",
            str(direct_one_shot),
            "--out-rejected",
            str(tmp_path / "rejected.jsonl"),
            "--min-survivors",
            "1",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Candidate pool too easy or too small: only 0 survived." in completed.stderr
    rejected = _read_jsonl(tmp_path / "rejected.jsonl")
    assert rejected[0]["selection_reject_reason"] == "direct_one_shot_solved"


def test_selector_keeps_uniform_unsolved_candidate_without_reference_solution(tmp_path: Path) -> None:
    candidate = _selector_problem("real_lean_02_001")
    candidates = tmp_path / "candidates.jsonl"
    selected = tmp_path / "selected.jsonl"
    selected_solutions = tmp_path / "selected_solutions.jsonl"
    _write_jsonl(candidates, [model_to_jsonable(candidate)])
    direct_full = tmp_path / "direct_full.csv"
    uniform = tmp_path / "uniform.csv"
    _write_summary(direct_full, [{"problem_id": candidate.problem_id, "condition": "direct", "solved": "False"}])
    _write_summary(uniform, [{"problem_id": candidate.problem_id, "condition": "uniform", "solved": "False"}])

    completed = subprocess.run(
        [
            "python3",
            "scripts/select_real_lean_02.py",
            "--candidates",
            str(candidates),
            "--solutions",
            str(tmp_path / "missing_solutions.jsonl"),
            "--direct-full-summary",
            str(direct_full),
            "--uniform-constrained-summary",
            str(uniform),
            "--out-problems",
            str(selected),
            "--out-solutions",
            str(selected_solutions),
            "--min-survivors",
            "1",
            "--target-size",
            "1",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "selected=1" in completed.stdout
    assert _read_jsonl(selected)[0]["problem_id"] == candidate.problem_id
    assert selected_solutions.read_text(encoding="utf-8") == ""


def _fake_sorry_project(project: Path) -> Path:
    project.mkdir(parents=True)
    (project / "lakefile.lean").write_text("import Lake\nopen Lake DSL\npackage fake\n", encoding="utf-8")
    (project / "lean-toolchain").write_text("leanprover/lean4:v4.12.0\n", encoding="utf-8")
    (project / "Hard.lean").write_text(
        """namespace Fake
open Nat

variable (xs ys zs : List Nat)

theorem original_hard_route :
    (xs ++ ys).map Nat.succ ++ zs.map Nat.succ =
      xs.map Nat.succ ++ ys.map Nat.succ ++ zs.map Nat.succ := by
  sorry

end Fake
""",
        encoding="utf-8",
    )
    return project


def _selector_problem(problem_id: str) -> Problem:
    suffix = problem_id.rsplit("_", 1)[-1]
    theorem_name = f"real02_target_{suffix}"
    statement = (
        f"theorem {theorem_name} (xs ys zs : List Nat) : "
        "(xs ++ ys).map Nat.succ ++ zs.map Nat.succ = "
        "xs.map Nat.succ ++ ys.map Nat.succ ++ zs.map Nat.succ := {{proof}}"
    )
    return Problem(
        problem_id=problem_id,
        source="real_lean_02_sorry_project",
        theorem_name=theorem_name,
        statement=statement,
        task_type="file_with_hole",
        full_lean_source=statement + "\n",
        expected_theorem_name=theorem_name,
        metadata={"anonymized": True, "validation_attempted": False},
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
                "condition": "direct",
                "solved": "False",
                "wall_time": "1.0",
                "lean_calls": "3",
                "llm_calls": "3",
                "estimated_tokens": "1",
                "rounds": "3",
                "notes": "",
                "proof": "",
            }
            payload.update(row)
            writer.writerow(payload)
