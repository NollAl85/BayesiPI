from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import yaml

from harness.agents import DeterministicToyBackend, DirectAgent, PIAgent, PromptLibrary, WorkerAgent
from harness.lean_runner import LeanRunner
from harness.logging import RunLogger, make_run_id
from harness.schemas import (
    AgentAttempt,
    Approach,
    BudgetSnapshot,
    Condition,
    ConditionResult,
    ExperimentConfig,
    LeanResult,
    PIUpdate,
    Problem,
    WorkerReport,
    model_to_jsonable,
)


DEFAULT_APPROACHES = [
    Approach(
        approach_id="simplification",
        description="Try simplification, rewriting, and canonical simp lemmas.",
    ),
    Approach(
        approach_id="library_search",
        description="Try direct existing theorems, constructors, or exact proof terms.",
    ),
    Approach(
        approach_id="case_analysis",
        description="Try constructors, destructuring hypotheses, or direct cases.",
    ),
]


class BudgetTracker:
    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.started_at = time.monotonic()
        self.rounds = 0
        self.llm_calls = 0
        self.lean_calls = 0
        self.estimated_tokens = 0

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            rounds=self.rounds,
            llm_calls=self.llm_calls,
            lean_calls=self.lean_calls,
            estimated_tokens=self.estimated_tokens,
            elapsed_seconds=self.elapsed_seconds,
        )

    def can_start_round(self) -> bool:
        return self.rounds < self.config.max_rounds and self._time_available()

    def start_round(self) -> None:
        self.rounds += 1

    def can_call_agent(self) -> bool:
        if self.llm_calls >= self.config.max_llm_calls:
            return False
        if not self._time_available():
            return False
        if self.config.max_estimated_tokens is None:
            return True
        return self.estimated_tokens < self.config.max_estimated_tokens

    def record_agent_call(self, estimated_tokens: int) -> None:
        self.llm_calls += 1
        self.estimated_tokens += estimated_tokens

    def can_call_lean(self) -> bool:
        return self.lean_calls < self.config.max_lean_calls and self._time_available()

    def record_lean_call(self) -> None:
        self.lean_calls += 1

    def exhausted_reason(self) -> str:
        if self.rounds >= self.config.max_rounds:
            return "round budget exhausted"
        if self.llm_calls >= self.config.max_llm_calls:
            return "agent-call budget exhausted"
        if self.lean_calls >= self.config.max_lean_calls:
            return "Lean-call budget exhausted"
        if self.config.max_estimated_tokens is not None and self.estimated_tokens >= self.config.max_estimated_tokens:
            return "estimated-token budget exhausted"
        if not self._time_available():
            return "wall-clock budget exhausted"
        return "no proof found"

    def _time_available(self) -> bool:
        return self.elapsed_seconds < self.config.max_wall_seconds


class ExperimentRunner:
    def __init__(
        self,
        config: ExperimentConfig,
        project_root: Path | str | None = None,
        run_id: str | None = None,
    ):
        self.config = config
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
        self.run_id = run_id or make_run_id(config.run_id_prefix)
        self.logger = RunLogger(self.project_root / "logs", self.run_id)
        self.lean_runner = LeanRunner(config.lean_command, config.lean_timeout_seconds)
        prompt_library = PromptLibrary(self.project_root / "prompts")
        backend = DeterministicToyBackend()
        self.direct_agent = DirectAgent(backend, prompt_library)
        self.worker_agent = WorkerAgent(backend, prompt_library)
        self.pi_agent = PIAgent(backend, prompt_library)

    def run_all(self, problems: list[Problem], conditions: Iterable[Condition] | None = None) -> list[ConditionResult]:
        selected_conditions = list(conditions or self.config.conditions)
        self.logger.save_config(self.config)
        self.logger.save_problems(problems)
        rows: list[ConditionResult] = []
        for problem in problems:
            for condition in selected_conditions:
                if condition == Condition.direct:
                    rows.append(self.run_direct(problem))
                elif condition == Condition.uniform:
                    rows.append(self.run_uniform(problem))
                elif condition == Condition.pi:
                    rows.append(self.run_pi(problem))
                else:
                    raise ValueError(f"Unsupported condition: {condition}")
        self.logger.write_summary(rows)
        return rows

    def run_direct(self, problem: Problem) -> ConditionResult:
        tracker = BudgetTracker(self.config)
        previous_errors: list[str] = []
        proof: str | None = None
        self.logger.log_event("condition_start", {"condition": "direct", "problem_id": problem.problem_id})
        while tracker.can_start_round():
            tracker.start_round()
            if not tracker.can_call_agent():
                break
            attempt = self.direct_agent.propose(problem, previous_errors)
            tracker.record_agent_call(attempt.estimated_tokens)
            self._log_agent_attempt("direct", problem, attempt)
            if not tracker.can_call_lean():
                break
            result = self.lean_runner.check(problem, attempt.candidate_lean_code)
            tracker.record_lean_call()
            attempt.lean_result = result
            self._log_lean_result("direct", problem, result)
            self.logger.log_event("direct_attempt", model_to_jsonable(attempt))
            if result.success:
                proof = attempt.candidate_lean_code
                break
            previous_errors.append(result.error_summary)
        return self._condition_result(problem, Condition.direct, tracker, proof)

    def run_uniform(self, problem: Problem) -> ConditionResult:
        tracker = BudgetTracker(self.config)
        proof: str | None = None
        reports: list[WorkerReport] = []
        lean_feedback: list[str] = []
        approaches = self._approaches()[: self.config.workers_per_round]
        self.logger.log_event("condition_start", {"condition": "uniform", "problem_id": problem.problem_id})
        while tracker.can_start_round() and proof is None:
            tracker.start_round()
            for approach in approaches:
                if not tracker.can_call_agent() or not tracker.can_call_lean():
                    break
                report = self.worker_agent.attempt(problem, approach, reports, lean_feedback)
                tracker.record_agent_call(report.estimated_tokens)
                self._log_worker_report("uniform", problem, report)
                result = self.lean_runner.check(problem, report.candidate_lean_code)
                tracker.record_lean_call()
                report.lean_result = result
                report.lean_success = result.success
                report.proof_found = result.success
                report.remaining_goals = result.remaining_goals
                self._log_lean_result("uniform", problem, result)
                self.logger.log_event("uniform_worker_report", model_to_jsonable(report))
                reports.append(report)
                if result.success:
                    proof = report.candidate_lean_code
                    break
                lean_feedback.append(result.error_summary)
        return self._condition_result(problem, Condition.uniform, tracker, proof)

    def run_pi(self, problem: Problem) -> ConditionResult:
        tracker = BudgetTracker(self.config)
        proof: str | None = None
        approaches = self._approaches()
        reports: list[WorkerReport] = []
        lean_feedback: list[str] = []
        assignments = []
        self.logger.log_event("condition_start", {"condition": "pi", "problem_id": problem.problem_id})
        if tracker.can_call_agent():
            initial = self.pi_agent.initial_plan(
                problem,
                approaches,
                self.config.workers_per_round,
                tracker.snapshot(),
            )
            tracker.record_agent_call(initial.estimated_tokens)
            assignments = initial.assignments
            self._log_pi_update("pi_initial", problem, initial)
        while tracker.can_start_round() and proof is None:
            tracker.start_round()
            if not assignments:
                assignments = self._fallback_assignments(approaches)
            round_reports: list[WorkerReport] = []
            for assignment in assignments[: self.config.workers_per_round]:
                if not tracker.can_call_agent() or not tracker.can_call_lean():
                    break
                approach = self._find_approach(approaches, assignment.approach_id)
                report = self.worker_agent.attempt(problem, approach, reports, lean_feedback)
                tracker.record_agent_call(report.estimated_tokens)
                self._log_worker_report("pi_worker", problem, report)
                result = self.lean_runner.check(problem, report.candidate_lean_code)
                tracker.record_lean_call()
                report.lean_result = result
                report.lean_success = result.success
                report.proof_found = result.success
                report.remaining_goals = result.remaining_goals
                self._log_lean_result("pi_worker", problem, result)
                self.logger.log_event("pi_worker_report", model_to_jsonable(report))
                reports.append(report)
                round_reports.append(report)
                if result.success:
                    proof = report.candidate_lean_code
                    break
                lean_feedback.append(result.error_summary)
            if proof is not None:
                break
            if tracker.can_call_agent():
                update = self.pi_agent.update(
                    problem,
                    approaches,
                    round_reports,
                    self.config.workers_per_round,
                    tracker.snapshot(),
                )
                tracker.record_agent_call(update.estimated_tokens)
                assignments = update.assignments
                approaches.extend(update.new_approaches)
                self._log_pi_update("pi_update", problem, update)
        return self._condition_result(problem, Condition.pi, tracker, proof)

    def _condition_result(
        self,
        problem: Problem,
        condition: Condition,
        tracker: BudgetTracker,
        proof: str | None,
    ) -> ConditionResult:
        solved = proof is not None
        result = ConditionResult(
            run_id=self.run_id,
            problem_id=problem.problem_id,
            condition=condition,
            solved=solved,
            wall_time=tracker.elapsed_seconds,
            lean_calls=tracker.lean_calls,
            llm_calls=tracker.llm_calls,
            estimated_tokens=tracker.estimated_tokens,
            rounds=tracker.rounds,
            notes="solved" if solved else tracker.exhausted_reason(),
            proof=proof,
        )
        self.logger.log_event("condition_end", model_to_jsonable(result))
        return result

    def _approaches(self) -> list[Approach]:
        return self.config.approaches or DEFAULT_APPROACHES

    def _fallback_assignments(self, approaches: list[Approach]):
        from harness.schemas import PIAssignment

        return [
            PIAssignment(
                approach_id=approach.approach_id,
                worker_id=f"fallback_worker_{index + 1}",
                effort_budget=1,
                rationale="Fallback assignment when PI returned no workers.",
            )
            for index, approach in enumerate(approaches[: self.config.workers_per_round])
        ]

    def _find_approach(self, approaches: list[Approach], approach_id: str) -> Approach:
        for approach in approaches:
            if approach.approach_id == approach_id:
                return approach
        return Approach(approach_id=approach_id, description="Approach supplied by PI.")

    def _log_agent_attempt(self, label: str, problem: Problem, attempt: AgentAttempt) -> None:
        self.logger.save_prompt_response(
            f"{label}_{problem.problem_id}",
            attempt.prompt,
            attempt.response,
            {"estimated_tokens": attempt.estimated_tokens},
        )

    def _log_worker_report(self, label: str, problem: Problem, report: WorkerReport) -> None:
        self.logger.save_prompt_response(
            f"{label}_{problem.problem_id}_{report.approach_id}",
            report.prompt,
            report.response,
            {"estimated_tokens": report.estimated_tokens},
        )

    def _log_pi_update(self, label: str, problem: Problem, update: PIUpdate) -> None:
        self.logger.save_prompt_response(
            f"{label}_{problem.problem_id}",
            update.prompt,
            update.response,
            {"estimated_tokens": update.estimated_tokens},
        )
        self.logger.log_event(label, model_to_jsonable(update))

    def _log_lean_result(self, label: str, problem: Problem, result: LeanResult) -> None:
        self.logger.save_lean_artifact(
            f"{label}_{problem.problem_id}",
            result.lean_file,
            result.stdout,
            result.stderr,
        )


def load_config(path: Path | str) -> ExperimentConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return ExperimentConfig.model_validate(payload)

