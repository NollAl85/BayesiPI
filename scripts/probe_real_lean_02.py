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


PROBES = {
    "direct_one_shot": (
        PROJECT_ROOT / "config" / "real_lean_02_direct_one_shot.yaml",
        [Condition.direct],
    ),
    "direct_full": (
        PROJECT_ROOT / "config" / "real_lean_02_direct_full.yaml",
        [Condition.direct],
    ),
    "uniform_constrained": (
        PROJECT_ROOT / "config" / "real_lean_02_uniform_constrained.yaml",
        [Condition.uniform],
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real_lean_02 candidate difficulty probes.")
    parser.add_argument(
        "candidates",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "candidates" / "real_lean_02_candidates.jsonl",
    )
    parser.add_argument(
        "--probe",
        action="append",
        choices=[*PROBES.keys(), "all"],
        default=None,
        help="Probe to run. Repeat for multiple. Defaults to all.",
    )
    parser.add_argument(
        "--backend",
        choices=["manual", "codex_subagents"],
        default="manual",
    )
    parser.add_argument("--subagent-reasoning-effort", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-id-prefix", default="real_lean_02")
    args = parser.parse_args()

    requested = args.probe or ["all"]
    probe_names = list(PROBES) if "all" in requested else requested
    problems = load_jsonl(args.candidates)
    if args.limit is not None:
        problems = problems[: args.limit]
    outputs: list[tuple[str, Path, Path]] = []
    for probe_name in probe_names:
        config_path, conditions = PROBES[probe_name]
        config = load_config(config_path)
        run_id = f"{args.run_id_prefix}_{probe_name}"
        runner = ExperimentRunner(
            config,
            PROJECT_ROOT,
            run_id=run_id,
            backend_name=args.backend,
            subagent_reasoning_effort=args.subagent_reasoning_effort,
        )
        rows = runner.run_all(problems, conditions)
        summary_path = runner.logger.run_dir / "summary.csv"
        aggregate_path = write_aggregate_csv(summary_path)
        _write_probe_csv(runner.logger.run_dir / "probe_tasks.csv", rows)
        outputs.append((probe_name, summary_path, aggregate_path))
    for probe_name, summary_path, aggregate_path in outputs:
        print(f"{probe_name}_summary={summary_path}")
        print(f"{probe_name}_aggregate={aggregate_path}")


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
