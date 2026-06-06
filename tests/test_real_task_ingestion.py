from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import ingest_real_lean_tasks


def test_ingestion_separates_public_problem_from_private_solution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_path = tmp_path / "input.jsonl"
    problems_path = tmp_path / "problems.jsonl"
    solutions_path = tmp_path / "solutions.jsonl"
    row = {
        "problem_id": "real_test_001",
        "source": "unit_test",
        "statement": "⊢ True",
        "full_lean_source": "example : True := {{proof}}",
        "proof_placeholder": "{{proof}}",
        "project_root": "/tmp/fake_project",
        "module_path": "Fake.lean",
        "theorem_name": "secret_original_name",
        "expected_theorem_name": "secret_expected_name",
        "reference_proof": "by\n  trivial",
        "metadata": {"public": "ok"},
        "solution_metadata": {"private": "ok"},
    }
    _write_jsonl(input_path, [row])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_real_lean_tasks.py",
            str(input_path),
            "--out-problems",
            str(problems_path),
            "--out-solutions",
            str(solutions_path),
        ],
    )

    ingest_real_lean_tasks.main()

    problems = _read_jsonl(problems_path)
    solutions = _read_jsonl(solutions_path)
    assert len(problems) == 1
    assert len(solutions) == 1
    public = problems[0]
    private = solutions[0]
    assert "reference_proof" not in public
    assert private["reference_proof"] == "by\n  trivial"
    assert public["task_type"] == "file_with_hole"
    assert public["full_lean_source"] == "example : True := {{proof}}"
    assert public["proof_placeholder"] == "{{proof}}"
    assert public["project_root"] == "/tmp/fake_project"
    assert public["module_path"] == "Fake.lean"
    assert public["metadata"] == {"public": "ok"}
    assert private["metadata"] == {"private": "ok"}


def test_ingestion_rejects_duplicate_problem_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_path = tmp_path / "input.jsonl"
    problems_path = tmp_path / "problems.jsonl"
    _write_jsonl(
        input_path,
        [
            {"problem_id": "dup", "source": "unit_test", "statement": "example : True"},
            {"problem_id": "dup", "source": "unit_test", "statement": "example : True"},
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ingest_real_lean_tasks.py", str(input_path), "--out-problems", str(problems_path)],
    )

    with pytest.raises(ValueError, match="Duplicate problem_id"):
        ingest_real_lean_tasks.main()


def test_ingestion_resolves_full_lean_source_path_relative_to_input(tmp_path: Path) -> None:
    source_path = tmp_path / "source.lean"
    source_path.write_text("example : True := {{proof}}\n", encoding="utf-8")
    row = {
        "problem_id": "path_source",
        "source": "unit_test",
        "full_lean_source_path": "source.lean",
        "proof_placeholder": "{{proof}}",
    }

    problem, solution = ingest_real_lean_tasks._convert_row(row, tmp_path)

    assert solution is None
    assert problem.full_lean_source == "example : True := {{proof}}\n"
    assert problem.statement == "example : True := {{proof}}"


def test_ingestion_summarizes_statement_from_full_source_when_missing(tmp_path: Path) -> None:
    row = {
        "problem_id": "summarized",
        "source": "unit_test",
        "full_lean_source": "\n\nexample : True := {{proof}}\n\n",
    }

    problem, _ = ingest_real_lean_tasks._convert_row(row, tmp_path)

    assert problem.statement == "example : True := {{proof}}"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
