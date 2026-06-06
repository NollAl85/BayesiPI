from __future__ import annotations

import argparse
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
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "basic_lean_03_allocation.yaml")
    parser.add_argument(
        "--backend",
        choices=["deterministic", "manual", "codex_subagents"],
        default="manual",
        help="Agent backend for the uniform probe.",
    )
    parser.add_argument("--subagent-reasoning-effort", default=None)
    parser.add_argument("--run-id", default="uniform_probe")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    config.conditions = [Condition.uniform]
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
    rows = runner.run_all(problems, [Condition.uniform])
    summary_path = runner.logger.run_dir / "summary.csv"
    aggregate_path = write_aggregate_csv(summary_path)
    solved = sum(1 for row in rows if row.solved)
    print(f"run_dir={runner.logger.run_dir}")
    print(f"summary_csv={summary_path}")
    print(f"aggregate_csv={aggregate_path}")
    print(f"approach_trace_csv={runner.logger.run_dir / 'approach_trace.csv'}")
    print(f"solved={solved}/{len(rows)}")


if __name__ == "__main__":
    main()
