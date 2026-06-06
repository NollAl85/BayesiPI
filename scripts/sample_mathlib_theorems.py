from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap import ensure_project_dependencies

ensure_project_dependencies()

from benchmark.mathlib_adapter import sample_from_local_mathlib, write_mathlib_reconstruction_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mathlib_root", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "benchmark" / "mathlib_sample.jsonl")
    args = parser.parse_args()
    problems = sample_from_local_mathlib(mathlib_root=args.mathlib_root, limit=args.limit)
    write_mathlib_reconstruction_jsonl(args.output, problems)
    print(args.output)


if __name__ == "__main__":
    main()
