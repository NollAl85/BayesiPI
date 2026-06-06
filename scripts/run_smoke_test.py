from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from analysis.summarize_results import write_aggregate_csv
from benchmark.toy_problems import toy_problems
from harness.experiment_runner import ExperimentRunner, load_config


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=["deterministic", "manual", "codex_subagents"],
        default="deterministic",
        help="Agent backend. Smoke tests default to deterministic.",
    )
    parser.add_argument(
        "--subagent-reasoning-effort",
        default=None,
        help="Optional Codex reasoning effort for codex_subagents, for example low, medium, high, or xhigh.",
    )
    args = parser.parse_args()
    config = load_config(PROJECT_ROOT / "config" / "default.yaml")
    runner = ExperimentRunner(
        config,
        PROJECT_ROOT,
        backend_name=args.backend,
        subagent_reasoning_effort=args.subagent_reasoning_effort,
    )
    rows = runner.run_all(toy_problems())
    summary_path = runner.logger.run_dir / "summary.csv"
    aggregate_path = write_aggregate_csv(summary_path)
    solved = sum(1 for row in rows if row.solved)
    print(f"run_dir={runner.logger.run_dir}")
    print(f"summary_csv={summary_path}")
    print(f"aggregate_csv={aggregate_path}")
    print(f"solved={solved}/{len(rows)}")
    if solved != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
