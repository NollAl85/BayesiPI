from __future__ import annotations

import json
import sys

from harness.agents import AgentCall, CodexSubagentBackend


def test_codex_subagent_backend_runs_cli_and_writes_artifacts(tmp_path, monkeypatch) -> None:
    fake_cli = _write_fake_codex_cli(tmp_path)
    monkeypatch.setenv("CODEX_SUBAGENT_COMMAND", f"{sys.executable} {fake_cli}")
    monkeypatch.setenv("CODEX_SUBAGENT_REASONING_EFFORT", "low")
    monkeypatch.setenv("CODEX_SUBAGENT_MODEL", "fake-model")

    artifact_dir = tmp_path / "artifacts"
    backend = CodexSubagentBackend(artifact_dir, max_parallel=2, timeout_seconds=5)
    response = backend.complete(
        "direct",
        "Base direct prompt",
        {"problem": {"problem_id": "codex_problem"}},
    )

    payload = json.loads(response)
    assert payload["candidate_lean_code"] == "by\n  trivial"
    assert backend.backend_name == "codex_subagents"

    prompt_path = artifact_dir / "0001_direct_codex_problem_prompt.md"
    response_path = artifact_dir / "0001_direct_codex_problem_response.json"
    argv_path = artifact_dir / "0001_direct_codex_problem_response.argv.json"
    workspace_path = artifact_dir / "0001_direct_codex_problem_workspace"
    assert prompt_path.exists()
    assert response_path.exists()
    assert workspace_path.is_dir()
    assert "Required Response JSON Schema" in prompt_path.read_text(encoding="utf-8")

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv[-1] == "-"
    assert argv[argv.index("--cd") + 1] == str(workspace_path)
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[argv.index("--model") + 1] == "fake-model"
    assert argv[argv.index("-c") + 1] == 'model_reasoning_effort="low"'


def test_codex_subagent_backend_batches_workers(tmp_path, monkeypatch) -> None:
    fake_cli = _write_fake_codex_cli(tmp_path)
    monkeypatch.setenv("CODEX_SUBAGENT_COMMAND", f"{sys.executable} {fake_cli}")
    monkeypatch.delenv("CODEX_SUBAGENT_EXTRA_ARGS", raising=False)
    monkeypatch.delenv("CODEX_SUBAGENT_MODEL", raising=False)
    monkeypatch.delenv("CODEX_SUBAGENT_REASONING_EFFORT", raising=False)

    artifact_dir = tmp_path / "artifacts"
    backend = CodexSubagentBackend(artifact_dir, max_parallel=2, timeout_seconds=5)
    responses = backend.complete_many(
        [
            AgentCall(
                role="worker",
                prompt="Worker prompt A",
                context={
                    "problem": {"problem_id": "batch_problem"},
                    "approach": {"approach_id": "cases"},
                },
            ),
            AgentCall(
                role="worker",
                prompt="Worker prompt B",
                context={
                    "problem": {"problem_id": "batch_problem"},
                    "approach": {"approach_id": "simp"},
                },
            ),
        ]
    )

    assert len(responses) == 2
    assert all(json.loads(response)["progress_claim"] == "technical_progress" for response in responses)
    assert (artifact_dir / "0001_worker_batch_problem_cases_response.json").exists()
    assert (artifact_dir / "0002_worker_batch_problem_simp_response.json").exists()


def _write_fake_codex_cli(tmp_path):
    script_path = tmp_path / "fake_codex_cli.py"
    script_path.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path

args = sys.argv[1:]
if not args or args[0] != "exec":
    raise SystemExit(2)

schema_path = Path(args[args.index("--output-schema") + 1])
output_path = Path(args[args.index("--output-last-message") + 1])
_ = sys.stdin.read()
schema = json.loads(schema_path.read_text(encoding="utf-8"))
properties = schema.get("properties", {})

if "progress_claim" in properties:
    payload = {
        "candidate_lean_code": "by\\n  trivial",
        "progress_claim": "technical_progress",
        "stuck_reason": None,
        "useful_artifacts": ["fake worker response"],
        "report_text": "Fake worker completed.",
    }
elif "reasoning_summary" in properties:
    payload = {
        "candidate_lean_code": "by\\n  trivial",
        "reasoning_summary": "Fake direct response.",
    }
else:
    payload = {
        "updated_beliefs": [],
        "killed_approaches": [],
        "new_approaches": [],
        "assignments": [],
        "summary": "Fake PI response.",
    }

output_path.write_text(json.dumps(payload), encoding="utf-8")
output_path.with_suffix(".argv.json").write_text(json.dumps(args), encoding="utf-8")
print("fake codex complete")
""".lstrip(),
        encoding="utf-8",
    )
    return script_path
