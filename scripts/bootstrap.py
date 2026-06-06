from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def ensure_project_dependencies() -> None:
    missing = _missing_modules()
    if not missing:
        return

    replacement = _find_python_with_dependencies()
    if replacement is not None:
        os.execv(replacement, [replacement, *sys.argv])

    modules = ", ".join(missing)
    raise SystemExit(
        f"Missing Python modules: {modules}. Use a Python environment with project dependencies installed."
    )


def _missing_modules() -> list[str]:
    missing: list[str] = []
    for module_name in ("pydantic", "yaml"):
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            missing.append(module_name)
    return missing


def _find_python_with_dependencies() -> str | None:
    candidates = [
        shutil.which("python"),
        "/Users/alex/miniconda3/bin/python",
    ]
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            continue
        if candidate_path.resolve() == current:
            continue
        completed = subprocess.run(
            [str(candidate_path), "-c", "import pydantic, yaml"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return str(candidate_path)
    return None

