from __future__ import annotations

from harness.agents import FileExchangeBackend


def test_file_exchange_backend_writes_prompt_and_reads_response(tmp_path) -> None:
    response_path = tmp_path / "0001_direct_manual_problem_response.json"
    response_path.write_text(
        '{"candidate_lean_code":"by\\n  trivial","reasoning_summary":"Direct constructor proof."}',
        encoding="utf-8",
    )
    backend = FileExchangeBackend(tmp_path, poll_interval_seconds=0.01, timeout_seconds=1)

    response = backend.complete(
        "direct",
        "Base prompt",
        {"problem": {"problem_id": "manual_problem"}},
    )

    prompt_path = tmp_path / "0001_direct_manual_problem_prompt.md"
    assert prompt_path.exists()
    assert "Required Response JSON Schema" in prompt_path.read_text(encoding="utf-8")
    assert "candidate_lean_code" in response

