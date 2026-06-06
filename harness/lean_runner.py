from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
import re

from harness.schemas import LeanResult, Problem


class LeanRunner:
    def __init__(self, command: list[str] | None = None, timeout_seconds: int = 10):
        self.command = command or ["lean"]
        self.timeout_seconds = timeout_seconds

    def check(self, problem: Problem, candidate_lean_code: str) -> LeanResult:
        lean_source = render_lean_source(problem, candidate_lean_code)
        temp_dir = tempfile.mkdtemp(prefix="lean_pi_")
        lean_path = Path(temp_dir) / f"{problem.problem_id}.lean"
        lean_path.write_text(lean_source, encoding="utf-8")
        start = time.monotonic()
        try:
            completed = subprocess.run(
                [*self.command, str(lean_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            elapsed = time.monotonic() - start
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            accepted = completed.returncode == 0 and not _uses_sorry(lean_source, stdout, stderr)
            return LeanResult(
                success=accepted,
                stdout=stdout,
                stderr=stderr,
                elapsed_seconds=elapsed,
                error_summary=summarize_lean_errors(stdout, stderr, lean_source),
                remaining_goals=extract_remaining_goals(stdout, stderr),
                command=[*self.command, str(lean_path)],
                lean_file=str(lean_path),
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - start
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            timeout_message = f"Lean timed out after {self.timeout_seconds} seconds."
            return LeanResult(
                success=False,
                stdout=stdout,
                stderr=f"{stderr}\n{timeout_message}".strip(),
                elapsed_seconds=elapsed,
                error_summary=timeout_message,
                remaining_goals=extract_remaining_goals(stdout, stderr),
                command=[*self.command, str(lean_path)],
                lean_file=str(lean_path),
            )


def render_lean_source(problem: Problem, candidate_lean_code: str) -> str:
    imports = "\n".join(f"import {name}" for name in problem.imports)
    body = candidate_lean_code.strip()
    if _looks_like_complete_lean_file(body):
        rendered = body
    else:
        rendered = f"{problem.statement.strip()} := {body}"
    if imports:
        return f"{imports}\n\n{rendered}\n"
    return f"{rendered}\n"


def summarize_lean_errors(stdout: str, stderr: str, lean_source: str = "", max_lines: int = 20) -> str:
    if _uses_sorry(lean_source, stdout, stderr):
        return "Proof contains or relies on sorry; treating as failure."
    combined = [
        line.rstrip()
        for line in f"{stdout}\n{stderr}".splitlines()
        if not _is_environment_warning(line)
    ]
    interesting = [
        line
        for line in combined
        if "error:" in line
        or "warning:" in line
        or "unsolved goals" in line
        or "unknown" in line.lower()
        or "failed" in line.lower()
    ]
    if not interesting:
        interesting = [line for line in combined if line.strip()]
    return "\n".join(interesting[-max_lines:])


def extract_remaining_goals(stdout: str, stderr: str, max_lines: int = 40) -> list[str]:
    lines = f"{stdout}\n{stderr}".splitlines()
    goals: list[str] = []
    capture = False
    for line in lines:
        if "unsolved goals" in line:
            capture = True
            goals.append(line.strip())
            continue
        if capture:
            if line.startswith("error:") and goals:
                break
            if line.strip():
                goals.append(line.rstrip())
            elif goals:
                break
        if len(goals) >= max_lines:
            break
    return goals


def _looks_like_complete_lean_file(value: str) -> bool:
    prefixes = ("import ", "example ", "theorem ", "lemma ", "def ")
    return value.startswith(prefixes) or "\nexample " in value or "\ntheorem " in value


def _uses_sorry(lean_source: str, stdout: str, stderr: str) -> bool:
    output = f"{stdout}\n{stderr}"
    source_has_sorry = re.search(r"(?<![A-Za-z0-9_])sorry(?![A-Za-z0-9_])", lean_source) is not None
    return source_has_sorry or "declaration uses 'sorry'" in output


def _is_environment_warning(line: str) -> bool:
    return "failed to query latest release" in line and "using existing version" in line


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
