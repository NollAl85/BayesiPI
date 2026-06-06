from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Condition(str, Enum):
    direct = "direct"
    uniform = "uniform"
    pi = "pi"


class ProgressType(str, Enum):
    proof_found = "proof_found"
    structural_progress = "structural_progress"
    directional_evidence = "directional_evidence"
    technical_progress = "technical_progress"
    no_progress = "no_progress"
    evidence_against = "evidence_against"


class Problem(BaseModel):
    problem_id: str
    source: str
    theorem_name: str | None = None
    imports: list[str] = Field(default_factory=list)
    statement: str
    hidden_reference_proof: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        """Return problem fields that may be shown to agents."""
        return {
            "problem_id": self.problem_id,
            "source": self.source,
            "theorem_name": self.theorem_name,
            "imports": self.imports,
            "statement": self.statement,
            "metadata": self.metadata,
        }


class Approach(BaseModel):
    approach_id: str
    description: str


class LeanResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    error_summary: str = ""
    remaining_goals: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    lean_file: str | None = None


class AgentAttempt(BaseModel):
    agent_type: str
    candidate_lean_code: str
    reasoning_summary: str = ""
    approach_id: str | None = None
    prompt: str = ""
    response: str = ""
    estimated_tokens: int = 0
    lean_result: LeanResult | None = None


class WorkerReport(BaseModel):
    approach_id: str
    approach_description: str
    proof_found: bool = False
    lean_success: bool = False
    candidate_lean_code: str = ""
    useful_artifacts: list[str] = Field(default_factory=list)
    remaining_goals: list[str] = Field(default_factory=list)
    stuck_reason: str | None = None
    progress_claim: ProgressType = ProgressType.no_progress
    report_text: str = ""
    prompt: str = ""
    response: str = ""
    estimated_tokens: int = 0
    lean_result: LeanResult | None = None


class PIBelief(BaseModel):
    approach_id: str
    belief_score: float = Field(ge=0.0, le=1.0)
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)


class PIAssignment(BaseModel):
    approach_id: str
    worker_id: str
    effort_budget: int = Field(ge=0)
    rationale: str = ""


class PIUpdate(BaseModel):
    updated_beliefs: list[PIBelief] = Field(default_factory=list)
    killed_approaches: list[str] = Field(default_factory=list)
    new_approaches: list[Approach] = Field(default_factory=list)
    assignments: list[PIAssignment] = Field(default_factory=list)
    summary: str = ""
    prompt: str = ""
    response: str = ""
    estimated_tokens: int = 0


class ExperimentConfig(BaseModel):
    run_id_prefix: str = "run"
    lean_command: list[str] = Field(default_factory=lambda: ["lean"])
    max_rounds: int = Field(default=3, ge=1)
    workers_per_round: int = Field(default=3, ge=1)
    max_llm_calls: int = Field(default=30, ge=1)
    max_lean_calls: int = Field(default=30, ge=1)
    max_wall_seconds: int = Field(default=120, ge=1)
    lean_timeout_seconds: int = Field(default=10, ge=1)
    max_estimated_tokens: int | None = Field(default=None, ge=1)
    conditions: list[Condition] = Field(
        default_factory=lambda: [Condition.direct, Condition.uniform, Condition.pi]
    )
    approaches: list[Approach] = Field(default_factory=list)


class BudgetSnapshot(BaseModel):
    rounds: int = 0
    llm_calls: int = 0
    lean_calls: int = 0
    estimated_tokens: int = 0
    elapsed_seconds: float = 0.0


class ConditionResult(BaseModel):
    run_id: str
    problem_id: str
    condition: Condition
    solved: bool
    wall_time: float
    lean_calls: int
    llm_calls: int
    estimated_tokens: int
    rounds: int
    notes: str = ""
    proof: str | None = None


def model_to_jsonable(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")

