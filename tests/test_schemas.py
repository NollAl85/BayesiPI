from __future__ import annotations

from harness.schemas import Problem


def test_public_payload_excludes_hidden_reference_proof() -> None:
    problem = Problem(
        problem_id="p",
        source="test",
        statement="example : True",
        hidden_reference_proof="by trivial",
    )

    payload = problem.public_payload()

    assert "hidden_reference_proof" not in payload
    assert payload["statement"] == "example : True"


def test_public_payload_real_task_leakage_contract() -> None:
    problem = Problem(
        problem_id="real_contract",
        source="test",
        theorem_name="public_or_anonymized_name",
        statement="example : True",
        full_lean_source="example : True := {{proof}}",
        project_root="/tmp/project",
        module_path="OriginalModule.lean",
        expected_theorem_name="public_or_anonymized_name",
        hidden_reference_proof="by\n  trivial",
        metadata={"public": "ok"},
    )

    payload = problem.public_payload()

    assert "hidden_reference_proof" not in payload
    assert payload["full_lean_source"] == "example : True := {{proof}}"
    assert payload["project_root"] == "/tmp/project"
    assert payload["module_path"] == "OriginalModule.lean"
    assert payload["expected_theorem_name"] == "public_or_anonymized_name"
    assert payload["metadata"] == {"public": "ok"}
    # Current contract: public_payload exposes theorem_name,
    # expected_theorem_name, metadata, full_lean_source, and module_path.
    # Benchmark-specific cleaners must anonymize or remove those fields before
    # prompts if they would reveal original theorem names or source modules.
