from __future__ import annotations

import argparse
import csv
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
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--backend",
        choices=["deterministic", "manual", "codex_subagents"],
        default="manual",
    )
    parser.add_argument("--subagent-reasoning-effort", default=None)
    parser.add_argument("--condition", action="append", choices=[condition.value for condition in Condition])
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    conditions = [Condition(value) for value in args.condition] if args.condition else config.conditions
    problems = load_jsonl(args.benchmark_jsonl)
    if args.limit is not None:
        problems = problems[: args.limit]
    runner = ExperimentRunner(
        config,
        PROJECT_ROOT,
        run_id=args.run_id,
        backend_name=args.backend,
        subagent_reasoning_effort=args.subagent_reasoning_effort,
    )
    rows = runner.run_all(problems, conditions)
    summary_path = runner.logger.run_dir / "summary.csv"
    aggregate_path = write_aggregate_csv(summary_path)
    probe_path = runner.logger.run_dir / "probe_tasks.csv"
    _write_probe_csv(probe_path, rows)
    solved = sum(1 for row in rows if row.solved)
    print(f"run_dir={runner.logger.run_dir}")
    print(f"summary_csv={summary_path}")
    print(f"aggregate_csv={aggregate_path}")
    print(f"approach_trace_csv={runner.logger.run_dir / 'approach_trace.csv'}")
    print(f"probe_tasks_csv={probe_path}")
    print(f"solved={solved}/{len(rows)}")


def _write_probe_csv(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["problem_id", "condition", "solved", "lean_calls", "rounds", "proof_lines", "notes"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "problem_id": row.problem_id,
                    "condition": row.condition.value,
                    "solved": row.solved,
                    "lean_calls": row.lean_calls,
                    "rounds": row.rounds,
                    "proof_lines": _proof_lines(row.proof),
                    "notes": row.notes,
                }
            )


def _proof_lines(proof: str | None) -> int:
    if not proof:
        return 0
    return sum(1 for line in proof.splitlines() if line.strip())


if __name__ == "__main__":
    main()
