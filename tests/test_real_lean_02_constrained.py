from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from harness.experiment_runner import load_config
from scripts.analyze_real_lean_02_constrained import main as analyze_main
from scripts.prepare_real_lean_02_prefix10_subsets import (
    DIRECT_SOLVED_IDS,
    MIDDLE_IDS,
    UNSOLVED_WIDE_IDS,
    partition_prefix10_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_prefix10_partition_helper_classifies_expected_ids() -> None:
    rows = [
        {
            "problem_id": f"real_lean_02_{index:03d}",
            "hidden_reference_proof": "by exact private",
            "metadata": {"source_path": "Private.lean", "public_tag": "kept"},
        }
        for index in range(1, 11)
    ]

    subsets = partition_prefix10_rows(rows)

    assert [row["problem_id"] for row in subsets["direct_solved"]] == list(DIRECT_SOLVED_IDS)
    assert [row["problem_id"] for row in subsets["middle"]] == list(MIDDLE_IDS)
    assert [row["problem_id"] for row in subsets["unsolved_wide"]] == list(UNSOLVED_WIDE_IDS)
    assert [row["problem_id"] for row in subsets["all"]] == [
        f"real_lean_02_{index:03d}" for index in range(1, 11)
    ]
    for subset_rows in subsets.values():
        for row in subset_rows:
            assert "hidden_reference_proof" not in row
            assert "source_path" not in row["metadata"]
            assert row["metadata"]["public_tag"] == "kept"


def test_constrained_config_has_scarce_allocation_budget() -> None:
    config = load_config(PROJECT_ROOT / "config" / "real_lean_02_prefix10_constrained.yaml")

    assert config.workers_per_round == 2
    assert config.max_rounds == 3
    assert config.max_llm_calls == 8
    assert config.max_lean_calls == 8
    assert [approach.approach_id for approach in config.approaches] == [
        "unfold_definitions",
        "simp_rewrite",
        "library_search",
        "constructor_extensionality",
        "algebraic_normalization",
        "order_or_lattice_reasoning",
        "topology_analysis_reasoning",
        "linear_algebra_structure",
        "auxiliary_lemma",
        "contradiction_or_boundary",
    ]


def test_constrained_analysis_aggregates_fake_run(tmp_path: Path, monkeypatch) -> None:
    summary = tmp_path / "summary.csv"
    trace = tmp_path / "approach_trace.csv"
    middle = tmp_path / "middle.jsonl"
    direct_solved = tmp_path / "direct_solved.jsonl"
    unsolved_wide = tmp_path / "unsolved_wide.jsonl"
    out_dir = tmp_path / "analysis"
    _write_csv(
        summary,
        [
            {
                "run_id": "r",
                "problem_id": "real_lean_02_001",
                "condition": "uniform",
                "solved": "True",
                "wall_time": "10",
                "lean_calls": "2",
                "llm_calls": "2",
                "estimated_tokens": "100",
                "rounds": "1",
                "notes": "solved",
                "proof": "by exact h",
            },
            {
                "run_id": "r",
                "problem_id": "real_lean_02_001",
                "condition": "pi",
                "solved": "False",
                "wall_time": "20",
                "lean_calls": "4",
                "llm_calls": "5",
                "estimated_tokens": "300",
                "rounds": "3",
                "notes": "budget",
                "proof": "",
            },
        ],
    )
    _write_csv(
        trace,
        [
            {
                "run_id": "r",
                "problem_id": "real_lean_02_001",
                "condition": "pi",
                "round": "0",
                "approach_id": "simp_rewrite",
                "agent_role": "pi_initial",
                "progress_claim": "",
                "lean_success": "",
                "proof_found": "",
                "pi_belief_before": "",
                "pi_belief_after": "0.7",
                "estimated_tokens": "80",
                "lean_calls_so_far": "0",
                "llm_calls_so_far": "1",
            },
            {
                "run_id": "r",
                "problem_id": "real_lean_02_001",
                "condition": "pi",
                "round": "1",
                "approach_id": "simp_rewrite",
                "agent_role": "worker",
                "progress_claim": "directional_evidence",
                "lean_success": "False",
                "proof_found": "False",
                "pi_belief_before": "0.7",
                "pi_belief_after": "",
                "estimated_tokens": "100",
                "lean_calls_so_far": "1",
                "llm_calls_so_far": "2",
            },
        ],
    )
    _write_jsonl(middle, [{"problem_id": "real_lean_02_001"}])
    _write_jsonl(direct_solved, [{"problem_id": "real_lean_02_004"}])
    _write_jsonl(unsolved_wide, [{"problem_id": "real_lean_02_005"}])
    monkeypatch.setattr(
        "sys.argv",
        [
            "analyze_real_lean_02_constrained.py",
            "--summary",
            str(summary),
            "--approach-trace",
            str(trace),
            "--middle",
            str(middle),
            "--direct-solved",
            str(direct_solved),
            "--unsolved-wide",
            str(unsolved_wide),
            "--out-dir",
            str(out_dir),
        ],
    )

    analyze_main()

    all_rows = list(csv.DictReader((out_dir / "condition_aggregate_all.csv").open()))
    assert {row["condition"]: row["solved_count"] for row in all_rows} == {"pi": "0", "uniform": "1"}
    middle_rows = list(csv.DictReader((out_dir / "condition_aggregate_middle.csv").open()))
    assert {row["condition"]: row["problem_count"] for row in middle_rows} == {"pi": "1", "uniform": "1"}
    assert (out_dir / "per_problem_comparison.csv").exists()
    assert (out_dir / "pi_belief_trace.csv").exists()
    assert (out_dir / "approach_success_by_condition.csv").exists()


def test_constrained_run_scripts_exist_and_are_executable() -> None:
    middle_script = PROJECT_ROOT / "scripts" / "run_real_lean_02_prefix10_constrained.sh"
    all_script = PROJECT_ROOT / "scripts" / "run_real_lean_02_prefix10_all_constrained.sh"

    assert os.access(middle_script, os.X_OK)
    assert os.access(all_script, os.X_OK)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")
