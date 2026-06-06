from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from harness.lean_runner import LeanRunner, render_lean_source
from harness.schemas import Problem


@pytest.mark.skipif(shutil.which("lean") is None, reason="Lean is not installed")
def test_lean_runner_accepts_valid_proof() -> None:
    problem = Problem(
        problem_id="lean_valid",
        source="test",
        statement="example (p : Prop) (hp : p) : p",
    )
    result = LeanRunner(["lean"], timeout_seconds=10).check(problem, "by\n  exact hp")

    assert result.success
    assert result.error_summary == ""


@pytest.mark.skipif(shutil.which("lean") is None, reason="Lean is not installed")
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


def test_render_lean_source_fills_full_source_placeholder_exactly() -> None:
    problem = Problem(
        problem_id="render_full_source_placeholder",
        source="test",
        statement="unused",
        full_lean_source="example : True := {{proof}}",
        proof_placeholder="{{proof}}",
    )

    rendered = render_lean_source(problem, "by\n  trivial")

    assert rendered == "example : True := by\n  trivial\n"


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


def test_render_lean_source_replaces_indented_by_sorry() -> None:
    problem = Problem(
        problem_id="render_indented_sorry",
        source="test",
        statement="unused",
        full_lean_source="example : True := by\n    sorry\n",
    )

    rendered = render_lean_source(problem, "trivial")

    assert "sorry" not in rendered
    assert rendered == "example : True := by\n    trivial\n"


def test_render_lean_source_replaces_first_bare_sorry() -> None:
    problem = Problem(
        problem_id="render_bare_sorry",
        source="test",
        statement="unused",
        full_lean_source="example : True := sorry",
    )

    rendered = render_lean_source(problem, "by\n  trivial")

    assert "sorry" not in rendered
    assert "by\n  trivial" in rendered
    assert "{{proof}}" not in rendered


def test_lean_runner_uses_project_root_as_subprocess_cwd(tmp_path: Path) -> None:
    project_root = tmp_path / "fake_project"
    project_root.mkdir()
    fake_command = tmp_path / "record_cwd.py"
    fake_command.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).with_suffix('.cwd').write_text(os.getcwd())\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    problem = Problem(
        problem_id="project_root_cwd",
        source="test",
        statement="unused",
        full_lean_source="example : True := {{proof}}",
        proof_placeholder="{{proof}}",
        project_root=str(project_root),
    )

    result = LeanRunner([sys.executable, str(fake_command)], timeout_seconds=10).check(problem, "by\n  trivial")

    assert result.success
    assert Path(result.lean_file or "").with_suffix(".cwd").read_text(encoding="utf-8") == str(project_root)
