from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from harness.schemas import (
    AgentAttempt,
    Approach,
    BudgetSnapshot,
    PIAssignment,
    PIBelief,
    PIUpdate,
    Problem,
    ProgressType,
    WorkerReport,
)


TOY_PROOF_ATTEMPTS = {
    "toy_nat_add_zero": "by\n  simpa",
    "toy_nat_add_comm": "by\n  exact Nat.add_comm a b",
    "toy_and_intro": "by\n  exact And.intro hp hq",
}


class AgentBackend(Protocol):
    def complete(self, role: str, prompt: str, context: dict[str, Any]) -> str:
        """Return a structured response as text."""


class DeterministicToyBackend:
    """Local backend for smoke tests.

    It uses problem IDs rather than hidden reference proofs, so the harness can
    test the full Lean/logging/budget path without leaking benchmark answers.
    """

    def complete(self, role: str, prompt: str, context: dict[str, Any]) -> str:
        problem_id = context.get("problem", {}).get("problem_id", "")
        proof = TOY_PROOF_ATTEMPTS.get(problem_id, "by\n  first | rfl | simp")
        if role == "direct":
            return json.dumps(
                {
                    "candidate_lean_code": proof,
                    "reasoning_summary": "Tried a compact direct proof for the toy theorem.",
                }
            )
        if role == "worker":
            approach = context.get("approach", {})
            return json.dumps(
                {
                    "candidate_lean_code": proof,
                    "progress_claim": "technical_progress",
                    "stuck_reason": None,
                    "useful_artifacts": [f"Attempted {approach.get('approach_id', 'unknown')} route."],
                    "report_text": "Produced a candidate proof for Lean verification.",
                }
            )
        if role == "pi_initial":
            approaches = [Approach.model_validate(item) for item in context.get("approaches", [])]
            workers_per_round = int(context.get("workers_per_round", 1))
            selected = approaches[:workers_per_round]
            return _pi_response(selected, "Initial PI plan assigns workers across distinct approaches.")
        if role == "pi_update":
            reports = context.get("worker_reports", [])
            successes = [report for report in reports if report.get("lean_success")]
            approaches = [Approach.model_validate(item) for item in context.get("approaches", [])]
            if successes:
                winning = successes[0]["approach_id"]
                beliefs = [
                    PIBelief(
                        approach_id=winning,
                        belief_score=1.0,
                        uncertainty_score=0.0,
                        rationale="Lean accepted this worker's proof.",
                        evidence_for=["Lean success"],
                    )
                ]
                return PIUpdate(
                    updated_beliefs=beliefs,
                    summary=f"Proof found by {winning}; stop allocating effort.",
                ).model_dump_json()
            selected = approaches[: int(context.get("workers_per_round", 1))]
            return _pi_response(selected, "No proof found; continue with the best remaining approaches.")
        raise ValueError(f"Unknown role: {role}")


class FileExchangeBackend:
    """Manual backend for Codex/subagent file exchange.

    Each call writes a prompt under logs/<run_id>/pending and waits for a JSON
    response file with the matching call ID. This keeps orchestration local
    while allowing Codex subagents, other sessions, or a human operator to fill
    agent outputs.
    """

    def __init__(
        self,
        pending_dir: Path | str,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float | None = None,
    ):
        self.pending_dir = Path(pending_dir)
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self._call_index = 0

    def complete(self, role: str, prompt: str, context: dict[str, Any]) -> str:
        self._call_index += 1
        call_id = self._call_id(role, context)
        prompt_path = self.pending_dir / f"{call_id}_prompt.md"
        response_path = self.pending_dir / f"{call_id}_response.json"
        error_path = self.pending_dir / f"{call_id}_error.txt"
        prompt_path.write_text(
            self._manual_prompt(role, prompt, response_path),
            encoding="utf-8",
        )
        print(f"Waiting for manual Codex response: {response_path}", flush=True)

        started_at = time.monotonic()
        last_error = ""
        while True:
            if response_path.exists():
                response = response_path.read_text(encoding="utf-8")
                try:
                    payload = _parse_json_response(response)
                    _validate_manual_response(role, payload, context)
                    if error_path.exists():
                        error_path.unlink()
                    return response
                except Exception as exc:  # noqa: BLE001
                    message = f"{type(exc).__name__}: {exc}"
                    if message != last_error:
                        error_path.write_text(message, encoding="utf-8")
                        print(f"Invalid manual response for {call_id}: {message}", flush=True)
                        last_error = message
            if self.timeout_seconds is not None and time.monotonic() - started_at > self.timeout_seconds:
                raise TimeoutError(f"Timed out waiting for {response_path}")
            time.sleep(self.poll_interval_seconds)

    def _call_id(self, role: str, context: dict[str, Any]) -> str:
        problem_id = context.get("problem", {}).get("problem_id", "unknown_problem")
        approach_id = context.get("approach", {}).get("approach_id")
        parts = [f"{self._call_index:04d}", role, str(problem_id)]
        if approach_id:
            parts.append(str(approach_id))
        return "_".join(_safe_token(part) for part in parts)

    def _manual_prompt(self, role: str, prompt: str, response_path: Path) -> str:
        schema = _required_response_schema(role)
        return (
            f"{prompt.rstrip()}\n\n"
            "## Manual Codex File Exchange\n\n"
            f"Write the response JSON to `{response_path.name}` in this same pending directory.\n"
            "Return only valid JSON. Do not wrap it in Markdown. Do not use web search or external retrieval.\n"
            "Use only the public problem context in this prompt. Hidden reference proofs are not available.\n\n"
            "## Required Response JSON Schema\n\n"
            "```json\n"
            f"{json.dumps(schema, indent=2, sort_keys=True)}\n"
            "```\n"
        )


class PromptLibrary:
    def __init__(self, prompt_dir: Path | str):
        self.prompt_dir = Path(prompt_dir)

    def load(self, name: str) -> str:
        return (self.prompt_dir / name).read_text(encoding="utf-8")


class DirectAgent:
    def __init__(self, backend: AgentBackend, prompts: PromptLibrary):
        self.backend = backend
        self.prompts = prompts

    def propose(self, problem: Problem, previous_errors: list[str]) -> AgentAttempt:
        context = {
            "problem": problem.public_payload(),
            "previous_errors": previous_errors,
        }
        prompt = _render_prompt(self.prompts.load("direct_agent.md"), context)
        response = self.backend.complete("direct", prompt, context)
        payload = _parse_json_response(response)
        attempt = AgentAttempt(
            agent_type="direct",
            candidate_lean_code=str(payload.get("candidate_lean_code", "")).strip(),
            reasoning_summary=str(payload.get("reasoning_summary", "")).strip(),
            prompt=prompt,
            response=response,
            estimated_tokens=estimate_tokens(prompt, response),
        )
        return attempt


class WorkerAgent:
    def __init__(self, backend: AgentBackend, prompts: PromptLibrary):
        self.backend = backend
        self.prompts = prompts

    def attempt(
        self,
        problem: Problem,
        approach: Approach,
        prior_reports: list[WorkerReport],
        lean_feedback: list[str],
    ) -> WorkerReport:
        context = {
            "problem": problem.public_payload(),
            "approach": approach.model_dump(mode="json"),
            "prior_reports": [report.model_dump(mode="json") for report in prior_reports],
            "lean_feedback": lean_feedback,
        }
        prompt = _render_prompt(self.prompts.load("worker_agent.md"), context)
        response = self.backend.complete("worker", prompt, context)
        payload = _parse_json_response(response)
        progress = _coerce_progress_type(payload.get("progress_claim"))
        return WorkerReport(
            approach_id=approach.approach_id,
            approach_description=approach.description,
            candidate_lean_code=str(payload.get("candidate_lean_code", "")).strip(),
            useful_artifacts=list(payload.get("useful_artifacts") or []),
            stuck_reason=payload.get("stuck_reason"),
            progress_claim=progress,
            report_text=str(payload.get("report_text", "")).strip(),
            prompt=prompt,
            response=response,
            estimated_tokens=estimate_tokens(prompt, response),
        )


class PIAgent:
    def __init__(self, backend: AgentBackend, prompts: PromptLibrary):
        self.backend = backend
        self.prompts = prompts

    def initial_plan(
        self,
        problem: Problem,
        approaches: list[Approach],
        workers_per_round: int,
        budget: BudgetSnapshot,
    ) -> PIUpdate:
        context = {
            "problem": problem.public_payload(),
            "approaches": [approach.model_dump(mode="json") for approach in approaches],
            "workers_per_round": workers_per_round,
            "budget": budget.model_dump(mode="json"),
        }
        prompt = _render_prompt(self.prompts.load("pi_initial.md"), context)
        response = self.backend.complete("pi_initial", prompt, context)
        return _parse_pi_update(prompt, response)

    def update(
        self,
        problem: Problem,
        approaches: list[Approach],
        worker_reports: list[WorkerReport],
        workers_per_round: int,
        budget: BudgetSnapshot,
    ) -> PIUpdate:
        context = {
            "problem": problem.public_payload(),
            "approaches": [approach.model_dump(mode="json") for approach in approaches],
            "worker_reports": [report.model_dump(mode="json") for report in worker_reports],
            "workers_per_round": workers_per_round,
            "budget": budget.model_dump(mode="json"),
        }
        prompt = _render_prompt(self.prompts.load("pi_update.md"), context)
        response = self.backend.complete("pi_update", prompt, context)
        return _parse_pi_update(prompt, response)


def estimate_tokens(*texts: str) -> int:
    total_chars = sum(len(text or "") for text in texts)
    return max(1, (total_chars + 3) // 4)


def _render_prompt(template: str, context: dict[str, Any]) -> str:
    public_context = json.dumps(context, indent=2, sort_keys=True)
    return f"{template.rstrip()}\n\n## Context\n\n```json\n{public_context}\n```\n"


def _parse_json_response(response: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end < start:
            return {}
        parsed = json.loads(response[start : end + 1])
    if isinstance(parsed, dict):
        return parsed
    return {}


def _parse_pi_update(prompt: str, response: str) -> PIUpdate:
    payload = _parse_json_response(response)
    try:
        update = PIUpdate.model_validate(payload)
    except ValidationError:
        update = PIUpdate(summary="Could not parse PI response.")
    update.prompt = prompt
    update.response = response
    update.estimated_tokens = estimate_tokens(prompt, response)
    return update


def _coerce_progress_type(value: Any) -> ProgressType:
    try:
        return ProgressType(value)
    except ValueError:
        return ProgressType.no_progress


def _validate_manual_response(role: str, payload: dict[str, Any], context: dict[str, Any]) -> None:
    if role == "direct":
        candidate = str(payload.get("candidate_lean_code", "")).strip()
        if not candidate:
            raise ValueError("direct response must include non-empty candidate_lean_code")
        AgentAttempt(
            agent_type="direct",
            candidate_lean_code=candidate,
            reasoning_summary=str(payload.get("reasoning_summary", "")).strip(),
        )
        return
    if role == "worker":
        candidate = str(payload.get("candidate_lean_code", "")).strip()
        if not candidate:
            raise ValueError("worker response must include non-empty candidate_lean_code")
        approach = context.get("approach", {})
        WorkerReport(
            approach_id=str(approach.get("approach_id", "")),
            approach_description=str(approach.get("description", "")),
            candidate_lean_code=candidate,
            useful_artifacts=list(payload.get("useful_artifacts") or []),
            stuck_reason=payload.get("stuck_reason"),
            progress_claim=_coerce_progress_type(payload.get("progress_claim")),
            report_text=str(payload.get("report_text", "")).strip(),
        )
        return
    if role in {"pi_initial", "pi_update"}:
        PIUpdate.model_validate(payload)
        return
    raise ValueError(f"Unknown role: {role}")


def _required_response_schema(role: str) -> dict[str, Any]:
    progress_values = [value.value for value in ProgressType]
    if role == "direct":
        return {
            "type": "object",
            "required": ["candidate_lean_code", "reasoning_summary"],
            "properties": {
                "candidate_lean_code": {"type": "string", "description": "Lean proof body, usually beginning with `by`."},
                "reasoning_summary": {"type": "string"},
            },
            "additionalProperties": False,
        }
    if role == "worker":
        return {
            "type": "object",
            "required": [
                "candidate_lean_code",
                "progress_claim",
                "stuck_reason",
                "useful_artifacts",
                "report_text",
            ],
            "properties": {
                "candidate_lean_code": {"type": "string", "description": "Lean proof body, usually beginning with `by`."},
                "progress_claim": {"type": "string", "enum": progress_values},
                "stuck_reason": {"type": ["string", "null"]},
                "useful_artifacts": {"type": "array", "items": {"type": "string"}},
                "report_text": {"type": "string"},
            },
            "additionalProperties": False,
        }
    if role in {"pi_initial", "pi_update"}:
        return {
            "type": "object",
            "required": [
                "updated_beliefs",
                "killed_approaches",
                "new_approaches",
                "assignments",
                "summary",
            ],
            "properties": {
                "updated_beliefs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["approach_id", "belief_score", "uncertainty_score", "rationale"],
                        "properties": {
                            "approach_id": {"type": "string"},
                            "belief_score": {"type": "number", "minimum": 0, "maximum": 1},
                            "uncertainty_score": {"type": "number", "minimum": 0, "maximum": 1},
                            "rationale": {"type": "string"},
                            "evidence_for": {"type": "array", "items": {"type": "string"}},
                            "evidence_against": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "killed_approaches": {"type": "array", "items": {"type": "string"}},
                "new_approaches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["approach_id", "description"],
                        "properties": {
                            "approach_id": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
                "assignments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["approach_id", "worker_id", "effort_budget", "rationale"],
                        "properties": {
                            "approach_id": {"type": "string"},
                            "worker_id": {"type": "string"},
                            "effort_budget": {"type": "integer", "minimum": 0},
                            "rationale": {"type": "string"},
                        },
                    },
                },
                "summary": {"type": "string"},
            },
            "additionalProperties": False,
        }
    return {"type": "object"}


def _safe_token(value: str) -> str:
    cleaned = [char if char.isalnum() or char in ("-", "_") else "_" for char in value]
    return "".join(cleaned).strip("_")[:80] or "unknown"


def _pi_response(approaches: list[Approach], summary: str) -> str:
    beliefs = [
        PIBelief(
            approach_id=approach.approach_id,
            belief_score=0.5,
            uncertainty_score=0.5,
            rationale="Initial toy prior.",
        )
        for approach in approaches
    ]
    assignments = [
        PIAssignment(
            approach_id=approach.approach_id,
            worker_id=f"worker_{index + 1}",
            effort_budget=1,
            rationale="Diversify across available approaches.",
        )
        for index, approach in enumerate(approaches)
    ]
    return PIUpdate(
        updated_beliefs=beliefs,
        assignments=assignments,
        summary=summary,
    ).model_dump_json()
