from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

from harness.schemas import Problem, ReferenceSolution, model_to_jsonable
from scripts import select_real_lean_01


def test_real_task_selector_rejects_easy_and_revealing_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    solutions_path = tmp_path / "solutions.jsonl"
    direct_summary_path = tmp_path / "direct_summary.csv"
    selected_path = tmp_path / "selected.jsonl"
    rejected_path = tmp_path / "rejected.jsonl"
    _write_jsonl(
        candidates_path,
        [
            model_to_jsonable(_problem("easy_one_call")),
            model_to_jsonable(_problem("easy_one_round")),
            model_to_jsonable(_problem("hard_unsolved")),
            model_to_jsonable(_problem("revealing_name", theorem_name="foo_mem_append")),
            model_to_jsonable(_problem("short_reference")),
        ],
    )
    _write_jsonl(
        solutions_path,
        [
            model_to_jsonable(_solution("short_reference", "by\n  exact trivial")),
        ],
    )
    _write_summary(
        direct_summary_path,
        [
            {"problem_id": "easy_one_call", "solved": "True", "lean_calls": "1", "rounds": "1"},
            {"problem_id": "easy_one_round", "solved": "True", "lean_calls": "2", "rounds": "1"},
            {"problem_id": "hard_unsolved", "solved": "False", "lean_calls": "3", "rounds": "3"},
            {"problem_id": "revealing_name", "solved": "False", "lean_calls": "3", "rounds": "3"},
            {"problem_id": "short_reference", "solved": "False", "lean_calls": "3", "rounds": "3"},
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_real_lean_01.py",
            "--candidates",
            str(candidates_path),
            "--direct-summary",
            str(direct_summary_path),
            "--solutions",
            str(solutions_path),
            "--out-problems",
            str(selected_path),
            "--out-rejected",
            str(rejected_path),
            "--target-size",
            "1",
            "--min-survivors",
            "1",
            "--min-reference-proof-lines",
            "5",
        ],
    )

    select_real_lean_01.main()

    selected = _read_jsonl(selected_path)
    rejected = _read_jsonl(rejected_path)
    reasons = {row["problem_id"]: row["selection_reject_reason"] for row in rejected}
    assert [row["problem_id"] for row in selected] == ["hard_unsolved"]
    assert reasons["easy_one_call"] == "direct_low_one_call"
    assert reasons["easy_one_round"] == "direct_low_one_round"
    assert reasons["revealing_name"] == "theorem_name_too_revealing"
    assert reasons["short_reference"] == "short_reference_proof"


def test_real_task_selector_fails_loudly_when_pool_is_too_easy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    direct_summary_path = tmp_path / "direct_summary.csv"
    selected_path = tmp_path / "selected.jsonl"
    _write_jsonl(candidates_path, [model_to_jsonable(_problem("easy_a")), model_to_jsonable(_problem("easy_b"))])
    _write_summary(
        direct_summary_path,
        [
            {"problem_id": "easy_a", "solved": "True", "lean_calls": "1", "rounds": "1"},
            {"problem_id": "easy_b", "solved": "True", "lean_calls": "1", "rounds": "1"},
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_real_lean_01.py",
            "--candidates",
            str(candidates_path),
            "--direct-summary",
            str(direct_summary_path),
            "--out-problems",
            str(selected_path),
            "--min-survivors",
            "1",
        ],
    )

    with pytest.raises(SystemExit, match="Candidate pool too easy"):
        select_real_lean_01.main()


def test_real_task_selector_fails_when_direct_summary_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    direct_summary_path = tmp_path / "direct_summary.csv"
    selected_path = tmp_path / "selected.jsonl"
    _write_jsonl(candidates_path, [model_to_jsonable(_problem("has_row")), model_to_jsonable(_problem("missing_row"))])
    _write_summary(direct_summary_path, [{"problem_id": "has_row", "solved": "False", "lean_calls": "3", "rounds": "3"}])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_real_lean_01.py",
            "--candidates",
            str(candidates_path),
            "--direct-summary",
            str(direct_summary_path),
            "--out-problems",
            str(selected_path),
        ],
    )

    with pytest.raises(SystemExit, match="Direct probe summary is incomplete"):
        select_real_lean_01.main()


def _problem(problem_id: str, theorem_name: str | None = None) -> Problem:
    return Problem(
        problem_id=problem_id,
        source="unit_test",
        theorem_name=theorem_name or f"target_{problem_id}",
        statement="example : True := {{proof}}",
        task_type="file_with_hole",
        full_lean_source="example : True := {{proof}}",
        proof_placeholder="{{proof}}",
    )


def _solution(problem_id: str, proof: str) -> ReferenceSolution:
    return ReferenceSolution(problem_id=problem_id, reference_proof=proof)


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
                "run_id": "selector_test",
                "condition": "direct",
                "wall_time": "1.0",
                "llm_calls": "1",
                "estimated_tokens": "1",
                "notes": "",
                "proof": "",
            }
            payload.update(row)
            writer.writerow(payload)
