from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from harness.schemas import ConditionResult, ExperimentConfig, Problem, model_to_jsonable


def make_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}"


class RunLogger:
    def __init__(self, root: Path | str, run_id: str):
        self.root = Path(root)
        self.run_id = run_id
        self.run_dir = self.root / run_id
        self.prompts_dir = self.run_dir / "prompts"
        self.responses_dir = self.run_dir / "responses"
        self.lean_dir = self.run_dir / "lean"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(exist_ok=True)
        self.responses_dir.mkdir(exist_ok=True)
        self.lean_dir.mkdir(exist_ok=True)
        self._event_index = 0
        self._artifact_index = 0

    def save_config(self, config: ExperimentConfig) -> None:
        with (self.run_dir / "config.yaml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump(model_to_jsonable(config), handle, sort_keys=False)

    def save_problems(self, problems: list[Problem]) -> None:
        with (self.run_dir / "problems.jsonl").open("w", encoding="utf-8") as handle:
            for problem in problems:
                handle.write(json.dumps(model_to_jsonable(problem), sort_keys=True) + "\n")

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_index += 1
        record = {
            "index": self._event_index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def save_prompt_response(
        self,
        label: str,
        prompt: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._artifact_index += 1
        safe_label = _safe_name(label)
        base = f"{self._artifact_index:04d}_{safe_label}"
        (self.prompts_dir / f"{base}.md").write_text(prompt, encoding="utf-8")
        (self.responses_dir / f"{base}.txt").write_text(response, encoding="utf-8")
        self.log_event(
            "agent_call",
            {
                "label": label,
                "prompt_file": f"prompts/{base}.md",
                "response_file": f"responses/{base}.txt",
                "metadata": metadata or {},
            },
        )

    def save_lean_artifact(self, label: str, lean_file: str | None, stdout: str, stderr: str) -> None:
        self._artifact_index += 1
        safe_label = _safe_name(label)
        base = f"{self._artifact_index:04d}_{safe_label}"
        if lean_file:
            destination = self.lean_dir / f"{base}.lean"
            shutil.copyfile(lean_file, destination)
        (self.lean_dir / f"{base}.stdout.txt").write_text(stdout, encoding="utf-8")
        (self.lean_dir / f"{base}.stderr.txt").write_text(stderr, encoding="utf-8")

    def write_summary(self, rows: list[ConditionResult]) -> Path:
        path = self.run_dir / "summary.csv"
        fieldnames = [
            "run_id",
            "problem_id",
            "condition",
            "solved",
            "wall_time",
            "lean_calls",
            "llm_calls",
            "estimated_tokens",
            "rounds",
            "notes",
            "proof",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                data = model_to_jsonable(row)
                data["condition"] = row.condition.value
                writer.writerow(data)
        return path


def _safe_name(value: str) -> str:
    cleaned = [char if char.isalnum() or char in ("-", "_") else "_" for char in value]
    return "".join(cleaned).strip("_")[:80] or "artifact"

