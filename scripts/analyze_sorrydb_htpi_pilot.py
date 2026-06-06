from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable


CONDITION_ORDER = {
    "direct": 0,
    "uniform": 1,
    "pi_initial_only": 2,
    "pi": 3,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze an HTPI/SorryDB pilot run.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--approach-trace", type=Path, required=True)
    parser.add_argument("--direct-failed", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    summary_rows = _read_csv(args.summary)
    trace_rows = _read_csv(args.approach_trace)
    direct_failed_ids = _read_problem_ids(args.direct_failed)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = sorted(summary_rows, key=_summary_sort_key)
    direct_failed_rows = [
        row for row in all_rows if row.get("problem_id") in direct_failed_ids
    ]

    _write_csv(args.out_dir / "pilot_summary_all.csv", all_rows)
    _write_csv(args.out_dir / "pilot_summary_direct_failed.csv", direct_failed_rows)
    _write_csv(
        args.out_dir / "condition_aggregate_all.csv",
        _condition_aggregates(all_rows),
    )
    _write_csv(
        args.out_dir / "condition_aggregate_direct_failed.csv",
        _condition_aggregates(direct_failed_rows),
    )
    _write_csv(
        args.out_dir / "approach_usage.csv",
        _approach_usage(trace_rows),
    )
    _write_csv(
        args.out_dir / "pi_belief_trace.csv",
        _pi_belief_trace(trace_rows),
    )

    print(f"pilot_summary_all={args.out_dir / 'pilot_summary_all.csv'}")
    print(f"pilot_summary_direct_failed={args.out_dir / 'pilot_summary_direct_failed.csv'}")
    print(f"condition_aggregate_all={args.out_dir / 'condition_aggregate_all.csv'}")
    print(f"condition_aggregate_direct_failed={args.out_dir / 'condition_aggregate_direct_failed.csv'}")
    print(f"approach_usage={args.out_dir / 'approach_usage.csv'}")
    print(f"pi_belief_trace={args.out_dir / 'pi_belief_trace.csv'}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_problem_ids(path: Path) -> set[str]:
    problem_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            problem_id = row.get("problem_id")
            if not problem_id:
                raise ValueError(f"Missing problem_id at {path}:{line_number}")
            problem_ids.add(str(problem_id))
    return problem_ids


def _condition_aggregates(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition"]].append(row)

    aggregates: list[dict[str, object]] = []
    for condition, condition_rows in sorted(grouped.items(), key=lambda item: _condition_key(item[0])):
        solved = [row for row in condition_rows if _bool(row.get("solved"))]
        aggregates.append(
            {
                "condition": condition,
                "problems": len(condition_rows),
                "solved": len(solved),
                "success_rate": _ratio(len(solved), len(condition_rows)),
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
    return aggregates


def _approach_usage(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row.get("condition", ""),
            row.get("agent_role", ""),
            row.get("approach_id", ""),
        )
        grouped[key].append(row)

    output: list[dict[str, object]] = []
    for (condition, agent_role, approach_id), trace_rows in sorted(
        grouped.items(), key=lambda item: (_condition_key(item[0][0]), item[0][1], item[0][2])
    ):
        lean_success = sum(1 for row in trace_rows if _bool(row.get("lean_success")))
        proof_found = sum(1 for row in trace_rows if _bool(row.get("proof_found")))
        output.append(
            {
                "condition": condition,
                "agent_role": agent_role,
                "approach_id": approach_id,
                "trace_rows": len(trace_rows),
                "lean_success": lean_success,
                "proof_found": proof_found,
                "total_estimated_tokens": _sum_float(trace_rows, "estimated_tokens"),
                "total_lean_calls_so_far": _sum_float(trace_rows, "lean_calls_so_far"),
                "total_llm_calls_so_far": _sum_float(trace_rows, "llm_calls_so_far"),
                "progress_claims": _join_counts(row.get("progress_claim", "") for row in trace_rows),
            }
        )
    return output


def _pi_belief_trace(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        if not (
            row.get("condition") in {"pi", "pi_initial_only"}
            and (row.get("pi_belief_before") or row.get("pi_belief_after") or row.get("agent_role", "").startswith("pi"))
        ):
            continue
        output.append(
            {
                "run_id": row.get("run_id", ""),
                "problem_id": row.get("problem_id", ""),
                "condition": row.get("condition", ""),
                "round": row.get("round", ""),
                "approach_id": row.get("approach_id", ""),
                "agent_role": row.get("agent_role", ""),
                "pi_belief_before": row.get("pi_belief_before", ""),
                "pi_belief_after": row.get("pi_belief_after", ""),
                "estimated_tokens": row.get("estimated_tokens", ""),
                "lean_calls_so_far": row.get("lean_calls_so_far", ""),
                "llm_calls_so_far": row.get("llm_calls_so_far", ""),
            }
        )
    return sorted(output, key=_trace_sort_key)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fieldnames(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["empty"]
    names: list[str] = []
    for row in rows:
        for name in row:
            if name not in names:
                names.append(name)
    return names


def _summary_sort_key(row: dict[str, str]) -> tuple[str, int]:
    return (row.get("problem_id", ""), _condition_key(row.get("condition", "")))


def _trace_sort_key(row: dict[str, object]) -> tuple[str, int, float, str]:
    return (
        str(row.get("problem_id", "")),
        _condition_key(str(row.get("condition", ""))),
        _float(row.get("round")),
        str(row.get("approach_id", "")),
    )


def _condition_key(condition: str) -> int:
    return CONDITION_ORDER.get(condition, 99)


def _bool(value: str | None) -> bool:
    return str(value or "").lower() == "true"


def _float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _sum_float(rows: list[dict[str, str]], field: str) -> float:
    return sum(_float(row.get(field)) for row in rows)


def _median_float(rows: list[dict[str, str]], field: str) -> float:
    values = [_float(row.get(field)) for row in rows if row.get(field) not in (None, "")]
    return statistics.median(values) if values else 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _join_counts(values: Iterable[str]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        key = value or ""
        if key:
            counts[key] += 1
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))


if __name__ == "__main__":
    main()
