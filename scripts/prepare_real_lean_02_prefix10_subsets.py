from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DIRECT_SOLVED_IDS = ("real_lean_02_004", "real_lean_02_009")
MIDDLE_IDS = (
    "real_lean_02_001",
    "real_lean_02_002",
    "real_lean_02_003",
    "real_lean_02_007",
    "real_lean_02_008",
    "real_lean_02_010",
)
UNSOLVED_WIDE_IDS = ("real_lean_02_005", "real_lean_02_006")
PRIVATE_EXPORT_KEYS = {
    "hidden_reference_proof",
    "reference_proof",
    "original_theorem",
    "original_theorem_name",
    "source_path",
}

SUBSET_IDS = {
    "middle": MIDDLE_IDS,
    "direct_solved": DIRECT_SOLVED_IDS,
    "unsolved_wide": UNSOLVED_WIDE_IDS,
}
EXPECTED_PREFIX10_IDS = DIRECT_SOLVED_IDS + MIDDLE_IDS + UNSOLVED_WIDE_IDS


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare real_lean_02 prefix-10 subset JSONL files.")
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "candidates" / "real_lean_02_prefix_10.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "problems",
    )
    args = parser.parse_args()

    rows = load_jsonl_rows(args.source)
    subsets = partition_prefix10_rows(rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "all": args.out_dir / "real_lean_02_prefix10_all.jsonl",
        "middle": args.out_dir / "real_lean_02_prefix10_middle_6.jsonl",
        "direct_solved": args.out_dir / "real_lean_02_prefix10_direct_solved_2.jsonl",
        "unsolved_wide": args.out_dir / "real_lean_02_prefix10_unsolved_by_wide_2.jsonl",
    }
    for name, path in outputs.items():
        write_jsonl_rows(path, subsets[name])
        print(f"{name}={path}")


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def partition_prefix10_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id = {row["problem_id"]: row for row in rows}
    expected = set(EXPECTED_PREFIX10_IDS)
    missing = sorted(expected - set(by_id))
    extra = sorted(set(by_id) - expected)
    if missing:
        raise ValueError(f"Missing expected prefix-10 problem ids: {', '.join(missing)}")
    if extra:
        raise ValueError(f"Unexpected problem ids in prefix-10 source: {', '.join(extra)}")
    subsets = {
        "all": [_sanitize_problem_row(row) for row in rows],
    }
    subsets.update({
        name: [by_id[problem_id] for problem_id in problem_ids]
        for name, problem_ids in SUBSET_IDS.items()
    })
    return {name: [_sanitize_problem_row(row) for row in subset_rows] for name, subset_rows in subsets.items()}


def _sanitize_problem_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _strip_private_keys(value)
        for key, value in row.items()
        if key not in PRIVATE_EXPORT_KEYS
    }


def _strip_private_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_private_keys(child)
            for key, child in value.items()
            if key not in PRIVATE_EXPORT_KEYS
        }
    if isinstance(value, list):
        return [_strip_private_keys(item) for item in value]
    return value


def write_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=False))
            handle.write("\n")


if __name__ == "__main__":
    main()
