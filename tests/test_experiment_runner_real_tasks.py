from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from harness.experiment_runner import ExperimentRunner
from harness.lean_runner import LeanRunner
from harness.schemas import Approach, Condition, ExperimentConfig, LeanResult, Problem


def test_experiment_runner_supports_pi_initial_only_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _project_root_with_prompts(tmp_path)
    monkeypatch.setattr(LeanRunner, "check", _fake_successful_check)
    config = ExperimentConfig(
        run_id_prefix="pytest_real",
        conditions=[Condition.pi_initial_only],
        max_rounds=1,
        workers_per_round=1,
        max_llm_calls=3,
        max_lean_calls=2,
        approaches=[Approach(approach_id="a", description="first approach")],
    )
    runner = ExperimentRunner(config, project_root, run_id="pi_initial_only_trace", backend_name="deterministic")

    rows = runner.run_all([_toy_problem()])

    assert len(rows) == 1
    assert rows[0].condition == Condition.pi_initial_only
    assert (runner.logger.run_dir / "summary.csv").exists()
    trace_path = runner.logger.run_dir / "approach_trace.csv"
    assert trace_path.exists()
    trace_rows = _read_csv(trace_path)
    assert any(row["agent_role"] == "pi_initial" for row in trace_rows)
    assert not any(row["agent_role"] == "pi_update" for row in trace_rows)


def test_uniform_round_robin_allocates_only_round_budget(tmp_path: Path) -> None:
    project_root = _project_root_with_prompts(tmp_path)
    config = ExperimentConfig(
        run_id_prefix="pytest_uniform",
        conditions=[Condition.uniform],
        workers_per_round=2,
        uniform_policy="round_robin",
        uniform_seed=3,
        approaches=[
            Approach(approach_id="a", description="approach a"),
            Approach(approach_id="b", description="approach b"),
            Approach(approach_id="c", description="approach c"),
            Approach(approach_id="d", description="approach d"),
        ],
    )
    runner = ExperimentRunner(config, project_root, run_id="uniform_round_robin", backend_name="deterministic")
    approaches = runner._uniform_approaches(Problem(problem_id="rr_problem", source="test", statement="example : True"))

    round_1 = runner._uniform_round_approaches(approaches, 1)
    round_2 = runner._uniform_round_approaches(approaches, 2)

    assert len(round_1) == 2
    assert len(round_2) == 2
    assert {approach.approach_id for approach in round_1}.isdisjoint(
        {approach.approach_id for approach in round_2}
    )
    assert {approach.approach_id for approach in round_1 + round_2} == {"a", "b", "c", "d"}


def test_pi_does_not_update_after_final_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root_with_prompts(tmp_path)
    monkeypatch.setattr(LeanRunner, "check", _fake_unsuccessful_check)
    config = ExperimentConfig(
        run_id_prefix="pytest_pi",
        conditions=[Condition.pi],
        max_rounds=1,
        workers_per_round=1,
        max_llm_calls=3,
        max_lean_calls=1,
        approaches=[Approach(approach_id="a", description="first approach")],
    )
    runner = ExperimentRunner(config, project_root, run_id="pi_no_final_update", backend_name="deterministic")

    rows = runner.run_all([_toy_problem()])

    assert len(rows) == 1
    assert not rows[0].solved
    trace_rows = _read_csv(runner.logger.run_dir / "approach_trace.csv")
    assert any(row["agent_role"] == "pi_initial" for row in trace_rows)
    assert not any(row["agent_role"] == "pi_update" for row in trace_rows)


def _fake_successful_check(self: LeanRunner, problem: Problem, candidate_lean_code: str) -> LeanResult:
    return LeanResult(success=True, elapsed_seconds=0.01, command=self.command)


def _fake_unsuccessful_check(self: LeanRunner, problem: Problem, candidate_lean_code: str) -> LeanResult:
    return LeanResult(
        success=False,
        elapsed_seconds=0.01,
        command=self.command,
        error_summary="synthetic failure",
    )


def _toy_problem() -> Problem:
    return Problem(
        problem_id="toy_nat_add_zero",
        source="toy",
        statement="example (n : Nat) : n + 0 = n",
    )


def _project_root_with_prompts(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "project"
    shutil.copytree(repo_root / "prompts", project_root / "prompts")
    return project_root


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
