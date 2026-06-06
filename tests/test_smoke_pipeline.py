from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmark.toy_problems import toy_problems
from harness.experiment_runner import ExperimentRunner, load_config


pytestmark = pytest.mark.skipif(shutil.which("lean") is None, reason="Lean is not installed")


def test_smoke_pipeline_solves_all_conditions() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(project_root / "config" / "default.yaml")
    runner = ExperimentRunner(config, project_root, run_id="pytest_smoke")

    rows = runner.run_all(toy_problems())

    assert len(rows) == 9
    assert all(row.solved for row in rows)
    assert (runner.logger.run_dir / "summary.csv").exists()
    assert (runner.logger.run_dir / "events.jsonl").exists()

