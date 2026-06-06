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

