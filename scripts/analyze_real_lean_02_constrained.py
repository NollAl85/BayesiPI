from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


AGGREGATE_FIELDS = [
    "condition",
    "problem_count",
    "solved_count",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze constrained real_lean_02 prefix-10 runs.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--approach-trace", type=Path, required=True)
    parser.add_argument("--middle", type=Path, required=True)
    parser.add_argument("--direct-solved", type=Path, required=True)
    parser.add_argument("--unsolved-wide", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = read_csv_rows(args.summary)
    trace_rows = read_csv_rows(args.approach_trace)
    middle_ids = load_problem_ids(args.middle)
    direct_solved_ids = load_problem_ids(args.direct_solved)
    unsolved_wide_ids = load_problem_ids(args.unsolved_wide)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_condition_aggregate(args.out_dir / "condition_aggregate_all.csv", rows)
    write_condition_aggregate(
        args.out_dir / "condition_aggregate_middle.csv",
        filter_summary_rows(rows, middle_ids),
    )
    write_condition_aggregate(
        args.out_dir / "condition_aggregate_direct_solved.csv",
        filter_summary_rows(rows, direct_solved_ids),
    )
    write_condition_aggregate(
        args.out_dir / "condition_aggregate_unsolved_wide.csv",
        filter_summary_rows(rows, unsolved_wide_ids),
    )
    write_per_problem_comparison(args.out_dir / "per_problem_comparison.csv", rows)
    write_pi_belief_trace(args.out_dir / "pi_belief_trace.csv", trace_rows)
    write_approach_success_by_condition(args.out_dir / "approach_success_by_condition.csv", trace_rows)

    for name in [
        "condition_aggregate_all.csv",
        "condition_aggregate_middle.csv",
        "condition_aggregate_direct_solved.csv",
        "condition_aggregate_unsolved_wide.csv",
        "per_problem_comparison.csv",
        "pi_belief_trace.csv",
        "approach_success_by_condition.csv",
    ]:
        print(f"{name}={args.out_dir / name}")


def load_problem_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ids.add(json.loads(line)["problem_id"])
    return ids


def filter_summary_rows(rows: list[dict[str, str]], problem_ids: set[str]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("problem_id") in problem_ids]


def write_condition_aggregate(path: Path, rows: list[dict[str, str]]) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition"]].append(row)
    output: list[dict[str, Any]] = []
    for condition, condition_rows in sorted(grouped.items()):
        solved_count = sum(1 for row in condition_rows if parse_bool(row.get("solved")))
        output.append(
            {
                "condition": condition,
                "problem_count": len(condition_rows),
                "solved_count": solved_count,
                "success_rate": solved_count / len(condition_rows) if condition_rows else 0.0,
                "total_wall_time": sum_numeric(condition_rows, "wall_time"),
                "median_wall_time": median_numeric(condition_rows, "wall_time"),
                "total_lean_calls": sum_numeric(condition_rows, "lean_calls"),
                "median_lean_calls": median_numeric(condition_rows, "lean_calls"),
                "total_llm_calls": sum_numeric(condition_rows, "llm_calls"),
                "median_llm_calls": median_numeric(condition_rows, "llm_calls"),
                "total_estimated_tokens": sum_numeric(condition_rows, "estimated_tokens"),
                "median_estimated_tokens": median_numeric(condition_rows, "estimated_tokens"),
                "median_rounds": median_numeric(condition_rows, "rounds"),
            }
        )
    write_rows(path, output, AGGREGATE_FIELDS)


def write_per_problem_comparison(path: Path, rows: list[dict[str, str]]) -> None:
    by_problem: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    conditions: list[str] = []
    for row in rows:
        condition = row["condition"]
        by_problem[row["problem_id"]][condition] = row
        if condition not in conditions:
            conditions.append(condition)

    fieldnames = ["problem_id"]
    for condition in conditions:
        fieldnames.extend(
            [
                f"{condition}_solved",
                f"{condition}_llm_calls",
                f"{condition}_lean_calls",
                f"{condition}_rounds",
                f"{condition}_estimated_tokens",
            ]
        )
    output: list[dict[str, str]] = []
    for problem_id, condition_rows in sorted(by_problem.items()):
        out = {"problem_id": problem_id}
        for condition in conditions:
            row = condition_rows.get(condition, {})
            out[f"{condition}_solved"] = row.get("solved", "")
            out[f"{condition}_llm_calls"] = row.get("llm_calls", "")
            out[f"{condition}_lean_calls"] = row.get("lean_calls", "")
            out[f"{condition}_rounds"] = row.get("rounds", "")
            out[f"{condition}_estimated_tokens"] = row.get("estimated_tokens", "")
        output.append(out)
    write_rows(path, output, fieldnames)


def write_pi_belief_trace(path: Path, trace_rows: list[dict[str, str]]) -> None:
    rows = [
        row
        for row in trace_rows
        if row.get("condition") in {"pi", "pi_initial_only"}
        and row.get("agent_role") in {"pi_initial", "pi_update", "worker"}
    ]
    fieldnames = list(trace_rows[0]) if trace_rows else []
    write_rows(path, rows, fieldnames)


def write_approach_success_by_condition(path: Path, trace_rows: list[dict[str, str]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in trace_rows:
        if row.get("agent_role") != "worker":
            continue
        approach_id = row.get("approach_id", "")
        if not approach_id:
            continue
        grouped[(row.get("condition", ""), approach_id)].append(row)

    fieldnames = [
        "condition",
        "approach_id",
        "attempts",
        "lean_successes",
        "proof_found_count",
        "proof_found_rate",
        "median_estimated_tokens",
        "progress_claims",
    ]
    output: list[dict[str, Any]] = []
    for (condition, approach_id), rows in sorted(grouped.items()):
        proof_found_count = sum(1 for row in rows if parse_bool(row.get("proof_found")))
        claims = Counter(row.get("progress_claim", "") for row in rows if row.get("progress_claim"))
        output.append(
            {
                "condition": condition,
                "approach_id": approach_id,
                "attempts": len(rows),
                "lean_successes": sum(1 for row in rows if parse_bool(row.get("lean_success"))),
                "proof_found_count": proof_found_count,
                "proof_found_rate": proof_found_count / len(rows) if rows else 0.0,
                "median_estimated_tokens": median_numeric(rows, "estimated_tokens"),
                "progress_claims": ";".join(f"{claim}:{count}" for claim, count in sorted(claims.items())),
            }
        )
    write_rows(path, output, fieldnames)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_bool(value: str | None) -> bool:
    return str(value).lower() == "true"


def sum_numeric(rows: list[dict[str, str]], field: str) -> float:
    return sum(float(row[field]) for row in rows if row.get(field) not in (None, ""))


def median_numeric(rows: list[dict[str, str]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return statistics.median(values) if values else 0.0


if __name__ == "__main__":
    main()
