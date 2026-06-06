from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from analysis.summarize_results import write_aggregate_csv
from benchmark.benchmark import load_jsonl
from harness.experiment_runner import ExperimentRunner, load_config
from harness.schemas import Condition


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark_jsonl", type=Path)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "default.yaml")
    parser.add_argument("--run-id", default="direct_probe")
    args = parser.parse_args()

    config = load_config(args.config)
    config.conditions = [Condition.direct]
    config.max_rounds = 1
    config.max_llm_calls = 1
    config.max_lean_calls = 1
    config.max_wall_seconds = min(config.max_wall_seconds, 120)

    problems = load_jsonl(args.benchmark_jsonl)
    runner = ExperimentRunner(config, PROJECT_ROOT, run_id=args.run_id, backend_name="manual")
    rows = runner.run_all(problems, [Condition.direct])
    summary_path = runner.logger.run_dir / "summary.csv"
    aggregate_path = write_aggregate_csv(summary_path)
    probe_path = runner.logger.run_dir / "direct_probe.csv"
    attempts = _load_direct_attempts(runner.logger.run_dir / "events.jsonl")

    with probe_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["problem_id", "solved", "lean_calls", "rounds", "proof_length", "notes"],
        )
        writer.writeheader()
        for row in rows:
            attempt = attempts.get(row.problem_id, {})
            candidate = str(attempt.get("candidate_lean_code") or row.proof or "")
            lean_result = attempt.get("lean_result") or {}
            error_summary = str(lean_result.get("error_summary") or "")
            notes = row.notes if row.solved or not error_summary else f"{row.notes}: {error_summary}"
            writer.writerow(
                {
                    "problem_id": row.problem_id,
                    "solved": row.solved,
                    "lean_calls": row.lean_calls,
                    "rounds": row.rounds,
                    "proof_length": len(candidate),
                    "notes": notes,
                }
            )

    solved = sum(1 for row in rows if row.solved)
    print(f"run_dir={runner.logger.run_dir}")
    print(f"summary_csv={summary_path}")
    print(f"aggregate_csv={aggregate_path}")
    print(f"direct_probe_csv={probe_path}")
    print(f"solved={solved}/{len(rows)}")


def _load_direct_attempts(events_path: Path) -> dict[str, dict]:
    attempts: dict[str, dict] = {}
    if not events_path.exists():
        return attempts
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event_type") != "direct_attempt":
                continue
            payload = event.get("payload") or {}
            lean_result = payload.get("lean_result") or {}
            lean_file = str(lean_result.get("lean_file") or "")
            problem_id = Path(lean_file).stem
            if problem_id:
                attempts[problem_id] = payload
    return attempts


if __name__ == "__main__":
    main()
