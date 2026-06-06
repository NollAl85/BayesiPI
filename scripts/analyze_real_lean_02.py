from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze real_lean_02 final allocation runs.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--approach-trace", type=Path, required=True)
    parser.add_argument("--direct-full-summary", type=Path, required=True)
    parser.add_argument("--uniform-constrained-summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = _read_csv(args.summary)
    trace_rows = _read_csv(args.approach_trace)
    direct_failed = _failed_ids(args.direct_full_summary, "direct")
    uniform_failed = _failed_ids(args.uniform_constrained_summary, "uniform")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    _write_aggregate(args.out_dir / "condition_aggregate_all.csv", rows)
    _write_aggregate(args.out_dir / "condition_aggregate_direct_full_failed.csv", _filter_rows(rows, direct_failed))
    _write_aggregate(
        args.out_dir / "condition_aggregate_uniform_constrained_failed.csv",
        _filter_rows(rows, uniform_failed),
    )
    _write_problem_condition_summary(args.out_dir / "problem_condition_summary.csv", rows)
    _write_solving_approaches(args.out_dir / "solving_approaches.csv", rows, trace_rows)
    _write_pi_belief_trace(args.out_dir / "pi_belief_trace.csv", trace_rows)
    _write_pi_belief_changes(args.out_dir / "pi_belief_changes.csv", trace_rows)
    print(f"condition_aggregate_all={args.out_dir / 'condition_aggregate_all.csv'}")
    print(
        "condition_aggregate_uniform_constrained_failed="
        f"{args.out_dir / 'condition_aggregate_uniform_constrained_failed.csv'}"
    )
    print(f"solving_approaches={args.out_dir / 'solving_approaches.csv'}")


def _write_aggregate(path: Path, rows: list[dict[str, str]]) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition"]].append(row)
    fieldnames = [
        "condition",
        "problems",
        "solved",
        "success_rate",
        "total_wall_time",
        "median_wall_time",
        "total_lean_calls",
        "median_lean_calls",
        "total_llm_calls",
        "median_llm_calls",
        "total_estimated_tokens",
        "median_estimated_tokens",
        "median_rounds",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for condition, condition_rows in sorted(grouped.items()):
            solved = [row for row in condition_rows if _bool(row.get("solved"))]
            writer.writerow(
                {
                    "condition": condition,
                    "problems": len(condition_rows),
                    "solved": len(solved),
                    "success_rate": len(solved) / len(condition_rows) if condition_rows else 0,
                    "total_wall_time": _sum_float(condition_rows, "wall_time"),
                    "median_wall_time": _median_float(condition_rows, "wall_time"),
                    "total_lean_calls": _sum_float(condition_rows, "lean_calls"),
                    "median_lean_calls": _median_float(condition_rows, "lean_calls"),
                    "total_llm_calls": _sum_float(condition_rows, "llm_calls"),
                    "median_llm_calls": _median_float(condition_rows, "llm_calls"),
                    "total_estimated_tokens": _sum_float(condition_rows, "estimated_tokens"),
                    "median_estimated_tokens": _median_float(condition_rows, "estimated_tokens"),
                    "median_rounds": _median_float(condition_rows, "rounds"),
                }
            )


def _write_problem_condition_summary(path: Path, rows: list[dict[str, str]]) -> None:
    _write_rows(path, rows, list(rows[0]) if rows else [])


def _write_solving_approaches(path: Path, rows: list[dict[str, str]], trace_rows: list[dict[str, str]]) -> None:
    solving_trace = {}
    for row in trace_rows:
        if _bool(row.get("proof_found")):
            solving_trace[(row["problem_id"], row["condition"])] = row
    output = []
    for row in rows:
        trace = solving_trace.get((row["problem_id"], row["condition"]), {})
        output.append(
            {
                "problem_id": row["problem_id"],
                "condition": row["condition"],
                "solved": row["solved"],
                "solving_approach_id": trace.get("approach_id", ""),
                "pi_belief_before_solving": trace.get("pi_belief_before", ""),
                "pi_belief_after_solving": trace.get("pi_belief_after", ""),
                "lean_calls": row.get("lean_calls", ""),
                "llm_calls": row.get("llm_calls", ""),
                "estimated_tokens": row.get("estimated_tokens", ""),
            }
        )
    _write_rows(path, output, list(output[0]) if output else [])


def _write_pi_belief_trace(path: Path, trace_rows: list[dict[str, str]]) -> None:
    rows = [row for row in trace_rows if row.get("condition") in {"pi", "pi_initial_only"}]
    _write_rows(path, rows, list(rows[0]) if rows else [])


def _write_pi_belief_changes(path: Path, trace_rows: list[dict[str, str]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in trace_rows:
        if row.get("condition") == "pi":
            grouped[(row["problem_id"], row["condition"])].append(row)
    output = []
    for (problem_id, condition), rows in sorted(grouped.items()):
        had_failed_worker = any(row.get("agent_role") == "worker" and not _bool(row.get("proof_found")) for row in rows)
        changed_after_failed_worker = False
        for row in rows:
            if row.get("agent_role") != "pi_update":
                continue
            before = row.get("pi_belief_before", "")
            after = row.get("pi_belief_after", "")
            if had_failed_worker and before not in ("", after):
                changed_after_failed_worker = True
        output.append(
            {
                "problem_id": problem_id,
                "condition": condition,
                "had_failed_worker": had_failed_worker,
                "pi_changed_beliefs_after_failed_workers": changed_after_failed_worker,
            }
        )
    _write_rows(path, output, list(output[0]) if output else [])


def _failed_ids(path: Path, condition: str) -> set[str]:
    return {
        row["problem_id"]
        for row in _read_csv(path)
        if row.get("condition") == condition and not _bool(row.get("solved"))
    }


def _filter_rows(rows: list[dict[str, str]], ids: set[str]) -> list[dict[str, str]]:
    return [row for row in rows if row["problem_id"] in ids]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _bool(value: str | None) -> bool:
    return str(value).lower() == "true"


def _sum_float(rows: list[dict[str, str]], field: str) -> float:
    return sum(float(row[field]) for row in rows if row.get(field) not in (None, ""))


def _median_float(rows: list[dict[str, str]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return statistics.median(values) if values else 0.0


if __name__ == "__main__":
    main()
