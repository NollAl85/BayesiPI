from __future__ import annotations

import shutil

import pytest

from harness.lean_runner import LeanRunner, render_lean_source
from harness.schemas import Problem


pytestmark = pytest.mark.skipif(shutil.which("lean") is None, reason="Lean is not installed")


def test_lean_runner_accepts_valid_proof() -> None:
    problem = Problem(
        problem_id="lean_valid",
        source="test",
        statement="example (p : Prop) (hp : p) : p",
    )
    result = LeanRunner(["lean"], timeout_seconds=10).check(problem, "by\n  exact hp")

    assert result.success
    assert result.error_summary == ""


def test_lean_runner_rejects_sorry() -> None:
    problem = Problem(
        problem_id="lean_sorry",
        source="test",
        statement="example : True",
    )
    result = LeanRunner(["lean"], timeout_seconds=10).check(problem, "by\n  sorry")

    assert not result.success
    assert "sorry" in result.error_summary


def test_render_lean_source_uses_imports() -> None:
    problem = Problem(
        problem_id="render",
        source="test",
        imports=["Init"],
        statement="example : True",
    )

    rendered = render_lean_source(problem, "by\n  trivial")

    assert rendered.startswith("import Init")
    assert "example : True := by" in rendered

