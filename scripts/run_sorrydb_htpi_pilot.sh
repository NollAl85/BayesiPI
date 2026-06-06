#!/usr/bin/env bash
set -euo pipefail

RUN_ID="sorrydb_htpi_all_low_01"

CODEX_SUBAGENT_MAX_PARALLEL=2 \
CODEX_SUBAGENT_TIMEOUT_SECONDS=600 \
CODEX_SUBAGENT_EXTRA_ARGS="--ignore-user-config --ignore-rules" \
python3 scripts/run_experiment.py benchmark/problems/sorrydb_htpi_10_pilot.jsonl \
  --config config/sorrydb_htpi_allocation.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id "${RUN_ID}"

python3 scripts/analyze_sorrydb_htpi_pilot.py \
  --summary "logs/${RUN_ID}/summary.csv" \
  --approach-trace "logs/${RUN_ID}/approach_trace.csv" \
  --direct-failed benchmark/problems/sorrydb_htpi_direct_failed_6.jsonl \
  --out-dir "logs/${RUN_ID}/pilot_analysis"

echo "summary.csv: logs/${RUN_ID}/summary.csv"
echo "aggregate.csv: logs/${RUN_ID}/aggregate_summary.csv"
echo "approach_trace.csv: logs/${RUN_ID}/approach_trace.csv"
echo "pilot_analysis/: logs/${RUN_ID}/pilot_analysis/"
