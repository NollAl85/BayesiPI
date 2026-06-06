from __future__ import annotations

from pathlib import Path

from benchmark.benchmark import load_jsonl, write_jsonl
from harness.schemas import Problem


def load_mathlib_reconstruction_jsonl(path: Path | str) -> list[Problem]:
    """Load Mathlib reconstruction problems from the shared JSONL schema."""
    return load_jsonl(path)


def write_mathlib_reconstruction_jsonl(path: Path | str, problems: list[Problem]) -> None:
    """Write Mathlib reconstruction problems in the shared JSONL schema."""
    write_jsonl(path, problems)


def sample_from_local_mathlib(*, mathlib_root: Path | str, limit: int) -> list[Problem]:
    """Placeholder for later Mathlib theorem extraction.

    V1 intentionally avoids a deep Mathlib extractor. The experiment can use
    hand-curated JSONL problems first, then replace this function with a local
    parser once the toy harness is stable.
    """
    raise NotImplementedError(
        f"Mathlib sampling is not implemented yet for {Path(mathlib_root)} with limit={limit}."
    )

