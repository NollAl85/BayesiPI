from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(summary_csv: Path | str) -> dict[str, dict[str, float]]:
    rows = _read_rows(Path(summary_csv))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition"]].append(row)

    aggregates: dict[str, dict[str, float]] = {}
    for condition, condition_rows in grouped.items():
        solved = [row for row in condition_rows if row["solved"].lower() == "true"]
        aggregates[condition] = {
            "problems": float(len(condition_rows)),
            "success_rate": len(solved) / len(condition_rows) if condition_rows else 0.0,
            "median_wall_time": _median_float(condition_rows, "wall_time"),
            "median_lean_calls": _median_float(condition_rows, "lean_calls"),
            "median_rounds": _median_float(condition_rows, "rounds"),
            "median_estimated_tokens": _median_float(condition_rows, "estimated_tokens"),
        }
    return aggregates


def write_aggregate_csv(summary_csv: Path | str, output_csv: Path | str | None = None) -> Path:
    source = Path(summary_csv)
    output = Path(output_csv) if output_csv else source.with_name("aggregate_summary.csv")
    aggregates = summarize(source)
    fieldnames = [
        "condition",
        "problems",
        "success_rate",
        "median_wall_time",
        "median_lean_calls",
        "median_rounds",
        "median_estimated_tokens",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for condition, metrics in sorted(aggregates.items()):
            writer.writerow({"condition": condition, **metrics})
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary_csv", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = write_aggregate_csv(args.summary_csv, args.output)
    print(output)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _median_float(rows: list[dict[str, str]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return statistics.median(values) if values else 0.0


if __name__ == "__main__":
    main()

