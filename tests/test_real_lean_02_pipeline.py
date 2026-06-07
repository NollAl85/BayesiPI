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


def test_mathlib_sampler_uses_proof_assignment_not_type_ascription(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "Topology"
    source_dir.mkdir(parents=True)
    (source_dir / "TypeAscription.lean").write_text(
        """theorem original_type_ascription :
    (Set.univ (α := Nat)).Nonempty := by
  have h0 : (0 : Nat) ∈ Set.univ := by trivial
  have h1 : (Set.univ (α := Nat)).Nonempty := ⟨0, h0⟩
  have h2 : (Set.univ (α := Nat)).Nonempty := h1
  have h3 : (Set.univ (α := Nat)).Nonempty := h2
  have h4 : (Set.univ (α := Nat)).Nonempty := h3
  have h5 : (Set.univ (α := Nat)).Nonempty := h4
  have h6 : (Set.univ (α := Nat)).Nonempty := h5
  exact h6
""",
        encoding="utf-8",
    )

    problems, _solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("Topology",),
    )

    full_source = problems[0].full_lean_source or ""
    assert "(α := Nat)" in full_source
    assert "(α := {{proof}}" not in full_source
    assert "Nonempty := {{proof}}" in full_source


def test_mathlib_sampler_does_not_bundle_neighboring_term_proofs(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "Order"
    source_dir.mkdir(parents=True)
    (source_dir / "Neighbors.lean").write_text(
        """theorem term_proof_neighbor (x : Nat) : x = x := rfl

lemma original_by_neighbor′ (x : Nat) : x = x := by
  have h1 : x = x := rfl
  have h2 : x = x := h1
  have h3 : x = x := h2
  have h4 : x = x := h3
  have h5 : x = x := h4
  have h6 : x = x := h5
  have h7 : x = x := h6
  exact h7
""",
        encoding="utf-8",
    )

    problems, _solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("Order",),
    )

    public_blob = json.dumps(model_to_jsonable(problems[0]), sort_keys=True)
    assert "term_proof_neighbor" in public_blob
    assert "original_by_neighbor" not in public_blob
    assert "real02_target_001′" not in public_blob
    assert "real02_target_001" in public_blob


def test_mathlib_sampler_skips_command_modifier_context(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "RingTheory"
    source_dir.mkdir(parents=True)
    (source_dir / "Modifier.lean").write_text(
        """variable {R : Type*}
variable (R) in
lemma modifier_sensitive_original : True := by
  have h1 : True := trivial
  have h2 : True := h1
  have h3 : True := h2
  have h4 : True := h3
  have h5 : True := h4
  have h6 : True := h5
  have h7 : True := h6
  exact h7

lemma safe_original_name (x y z : Nat) : x + y + z = x + (y + z) := by
  have h1 : x + y + z = x + (y + z) := by omega
  have h2 : x + y + z = x + (y + z) := h1
  have h3 : x + y + z = x + (y + z) := h2
  have h4 : x + y + z = x + (y + z) := h3
  have h5 : x + y + z = x + (y + z) := h4
  have h6 : x + y + z = x + (y + z) := h5
  have h7 : x + y + z = x + (y + z) := h6
  exact h7
""",
        encoding="utf-8",
    )

    problems, _solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("RingTheory",),
    )

    public_blob = json.dumps(model_to_jsonable(problems[0]), sort_keys=True)
    assert "modifier_sensitive_original" in public_blob
    assert "variable (R) in" in public_blob
    assert "safe_original_name" not in public_blob
    assert "real02_target_001" in public_blob


def test_mathlib_sampler_uses_prefix_imports_not_import_mathlib(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "Topology"
    source_dir.mkdir(parents=True)
    (source_dir / "Prefix.lean").write_text(
        """import Mathlib.Data.Nat.Basic

namespace Prefix

def helper (x : Nat) : Nat := x

lemma original_prefix_isolated (x : Nat) : helper x = x := by
  have h1 : helper x = x := rfl
  have h2 : helper x = x := h1
  have h3 : helper x = x := h2
  have h4 : helper x = x := h3
  have h5 : helper x = x := h4
  have h6 : helper x = x := h5
  have h7 : helper x = x := h6
  have h8 : helper x = x := h7
  exact h8

end Prefix
""",
        encoding="utf-8",
    )

    problems, _solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("Topology",),
    )

    full_source = problems[0].full_lean_source or ""
    assert "import Mathlib.Data.Nat.Basic" in full_source
    assert "import Mathlib\n" not in full_source
    assert "def helper" in full_source
    assert "theorem real02_target_001" in full_source
    assert "original_prefix_isolated" not in json.dumps(model_to_jsonable(problems[0]), sort_keys=True)


def test_mathlib_sampler_preserves_local_notation_context(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "FieldTheory"
    source_dir.mkdir(parents=True)
    (source_dir / "Notation.lean").write_text(
        """local notation "FooNat" => Nat

lemma original_notation_context (x : FooNat) : x = x := by
  have h1 : x = x := rfl
  have h2 : x = x := h1
  have h3 : x = x := h2
  have h4 : x = x := h3
  have h5 : x = x := h4
  have h6 : x = x := h5
  have h7 : x = x := h6
  exact h7
""",
        encoding="utf-8",
    )

    problems, _solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("FieldTheory",),
    )

    full_source = problems[0].full_lean_source or ""
    assert 'local notation "FooNat" => Nat' in full_source
    assert "FooNat" in problems[0].statement
    assert "original_notation_context" not in json.dumps(model_to_jsonable(problems[0]), sort_keys=True)


def test_mathlib_sampler_preserves_ordered_scoped_notation_context(tmp_path: Path) -> None:
    mathlib_dir = tmp_path / "Mathlib"
    source_dir = mathlib_dir / "RingTheory"
    source_dir.mkdir(parents=True)
    (source_dir / "ScopedNotation.lean").write_text(
        """namespace ScopedNotation
variable {p : Nat}
local notation "FooP" => p
noncomputable section

lemma original_scoped_notation_context : FooP = p := by
  have h1 : FooP = p := rfl
  have h2 : FooP = p := h1
  have h3 : FooP = p := h2
  have h4 : FooP = p := h3
  have h5 : FooP = p := h4
  have h6 : FooP = p := h5
  have h7 : FooP = p := h6
  exact h7
end
end ScopedNotation
""",
        encoding="utf-8",
    )

    problems, _solutions = sample_from_local_mathlib_with_solutions(
        mathlib_root=tmp_path,
        limit=1,
        project_root=tmp_path,
        module_prefixes=("RingTheory",),
    )

    full_source = problems[0].full_lean_source or ""
    assert full_source.index("namespace ScopedNotation") < full_source.index("variable {p : Nat}")
    assert full_source.index("variable {p : Nat}") < full_source.index('local notation "FooP" => p')
    assert full_source.index('local notation "FooP" => p') < full_source.index("noncomputable section")
    assert full_source.index("noncomputable section") < full_source.index("theorem real02_target_001")
    assert full_source.splitlines()[-2:] == ["end", "end ScopedNotation"]
    assert "original_scoped_notation_context" not in json.dumps(
        model_to_jsonable(problems[0]), sort_keys=True
    )


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
    uniform_easy = _problem("real_lean_02_003")
    _write_jsonl(candidates, [model_to_jsonable(hard), model_to_jsonable(easy), model_to_jsonable(uniform_easy)])
    _write_jsonl(
        solutions,
        [
            model_to_jsonable(_solution("real_lean_02_001")),
            model_to_jsonable(_solution("real_lean_02_002")),
            model_to_jsonable(_solution("real_lean_02_003")),
        ],
    )
    _write_summary(
        direct_summary,
        [
            {"problem_id": "real_lean_02_001", "condition": "direct", "solved": "False", "rounds": "3"},
            {"problem_id": "real_lean_02_002", "condition": "direct", "solved": "True", "rounds": "1"},
            {"problem_id": "real_lean_02_003", "condition": "direct", "solved": "False", "rounds": "3"},
        ],
    )
    _write_summary(
        uniform_summary,
        [
            {"problem_id": "real_lean_02_001", "condition": "uniform", "solved": "False", "rounds": "2"},
            {"problem_id": "real_lean_02_002", "condition": "uniform", "solved": "True", "rounds": "1"},
            {"problem_id": "real_lean_02_003", "condition": "uniform", "solved": "True", "rounds": "1"},
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
    reasons = {row["problem_id"]: row["selection_reject_reason"] for row in rejected}
    assert reasons["real_lean_02_002"] == "direct_full_solved"
    assert reasons["real_lean_02_003"] == "uniform_constrained_one_round_solved"
    assert [row["problem_id"] for row in uniform_failed] == ["real_lean_02_001"]


def _problem(problem_id: str) -> Problem:
    suffix = problem_id.rsplit("_", 1)[-1]
    theorem_name = f"real02_target_{suffix}"
    statement = (
        f"theorem {theorem_name} (xs ys zs : List Nat) : "
        "(xs ++ ys).map Nat.succ ++ zs.map Nat.succ = "
        "xs.map Nat.succ ++ ys.map Nat.succ ++ zs.map Nat.succ := {{proof}}"
    )
    return Problem(
        problem_id=problem_id,
        source="real_lean_02_mathlib",
        theorem_name=theorem_name,
        statement=statement,
        task_type="file_with_hole",
        full_lean_source=f"import Mathlib\n\n{statement}\n",
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
  have h8 : x = x := h7
  have h9 : x = x := h8
  exact h9"""
    return ReferenceSolution(
        problem_id=problem_id,
        reference_proof=proof,
        metadata={
            "original_theorem_name": f"private_name_{problem_id}",
            "source_module": "Mathlib/LinearAlgebra/Fake",
            "validation_attempted": True,
            "candidate_validated": True,
            "original_theorem_available": False,
            "proof_trivially_available": False,
            "reference_compiles": True,
            "reference_check_seconds": 1.0,
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
