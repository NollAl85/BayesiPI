from __future__ import annotations

import csv
from pathlib import Path

from harness.schemas import Condition, ConditionResult
from scripts.probe_tasks import _write_probe_csv


def test_write_probe_csv_includes_expected_columns_and_proof_lines(tmp_path: Path) -> None:
    output = tmp_path / "probe_tasks.csv"
    rows = [
        ConditionResult(
            run_id="probe_test",
            problem_id="solved",
            condition=Condition.direct,
            solved=True,
            wall_time=1.0,
            lean_calls=1,
            llm_calls=1,
            estimated_tokens=10,
            rounds=1,
            notes="solved",
            proof="by\n  exact True.intro\n  done",
        ),
        ConditionResult(
            run_id="probe_test",
            problem_id="unsolved",
            condition=Condition.uniform,
            solved=False,
            wall_time=2.0,
            lean_calls=2,
            llm_calls=2,
            estimated_tokens=20,
            rounds=2,
            notes="round budget exhausted",
            proof=None,
        ),
    ]

    _write_probe_csv(output, rows)

    with output.open("r", encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert list(written[0]) == ["problem_id", "condition", "solved", "lean_calls", "rounds", "proof_lines", "notes"]
    assert written[0]["problem_id"] == "solved"
    assert written[0]["condition"] == "direct"
    assert written[0]["solved"] == "True"
    assert written[0]["lean_calls"] == "1"
    assert written[0]["rounds"] == "1"
    assert written[0]["proof_lines"] == "3"
    assert written[1]["problem_id"] == "unsolved"
    assert written[1]["proof_lines"] == "0"
