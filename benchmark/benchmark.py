from __future__ import annotations

import json
from pathlib import Path

from harness.schemas import Problem, model_to_jsonable


def load_jsonl(path: Path | str) -> list[Problem]:
    problems: list[Problem] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                problems.append(Problem.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid problem JSONL at line {line_number}: {exc}") from exc
    return problems


def write_jsonl(path: Path | str, problems: list[Problem]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for problem in problems:
            handle.write(json.dumps(model_to_jsonable(problem), sort_keys=True) + "\n")

