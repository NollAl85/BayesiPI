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


def test_render_lean_source_fills_placeholder() -> None:
    problem = Problem(
        problem_id="render_placeholder",
        source="test",
        statement="example : True := {{proof}}",
        proof_placeholder="{{proof}}",
    )

    rendered = render_lean_source(problem, "by\n  trivial")

    assert "{{proof}}" not in rendered
    assert "example : True := by" in rendered


def test_render_lean_source_replaces_by_sorry_with_proof_body() -> None:
    problem = Problem(
        problem_id="render_sorry",
        source="test",
        statement="unused",
        full_lean_source="example : True := by\n  sorry\n",
    )

    rendered = render_lean_source(problem, "by\n  trivial")

    assert "sorry" not in rendered
    assert rendered == "example : True := by\n  trivial\n"
