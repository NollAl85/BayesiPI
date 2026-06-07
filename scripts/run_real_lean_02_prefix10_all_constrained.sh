#!/usr/bin/env bash
set -euo pipefail

RUN_ID="real02_prefix10_all_constrained_low_01"

CODEX_SUBAGENT_MAX_PARALLEL=2 \
CODEX_SUBAGENT_TIMEOUT_SECONDS=600 \
CODEX_SUBAGENT_EXTRA_ARGS="--ignore-user-config --ignore-rules" \
python3 scripts/run_experiment.py benchmark/problems/real_lean_02_prefix10_all.jsonl \
  --config config/real_lean_02_prefix10_constrained.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id "${RUN_ID}"

python3 scripts/analyze_real_lean_02_constrained.py \
  --summary "logs/${RUN_ID}/summary.csv" \
  --approach-trace "logs/${RUN_ID}/approach_trace.csv" \
  --middle benchmark/problems/real_lean_02_prefix10_middle_6.jsonl \
  --direct-solved benchmark/problems/real_lean_02_prefix10_direct_solved_2.jsonl \
  --unsolved-wide benchmark/problems/real_lean_02_prefix10_unsolved_by_wide_2.jsonl \
  --out-dir "logs/${RUN_ID}/constrained_analysis"

echo "summary.csv=logs/${RUN_ID}/summary.csv"
echo "aggregate_summary.csv=logs/${RUN_ID}/aggregate_summary.csv"
echo "approach_trace.csv=logs/${RUN_ID}/approach_trace.csv"
echo "constrained_analysis=logs/${RUN_ID}/constrained_analysis/"
