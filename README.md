# Lean PI Experiment Harness

This repository is a local research harness for testing whether a PI-style agent can improve Lean theorem-proving efficiency by allocating effort across proof approaches better than direct search or uniform multi-agent search.

The focus is not production theorem proving. The focus is whether structured progress assessment and belief-guided allocation improve use of a fixed budget.

## Conditions

The harness compares three conditions:

1. `direct`: one agent repeatedly proposes a proof, runs Lean, inspects errors, and retries.
2. `uniform`: multiple workers explore fixed proof approaches with equal budget and no reallocation.
3. `pi`: a PI agent proposes approaches, evaluates worker reports, updates beliefs, and reallocates effort.

## Local Assumptions

- Python 3.11 or newer.
- `lean` is available on `PATH`.
- `lake` is optional for toy problems, but recommended for Mathlib work.
- No web search or external retrieval is used during experiment runs.
- Mathlib reconstruction is supported by the schema and adapters, but V1 smoke tests use toy problems.

## Quick Start

From this directory:

```bash
python3 scripts/run_smoke_test.py
```

This runs all three conditions on trivial Lean examples, writes logs under `logs/<run_id>/`, and emits a `summary.csv`.

For a manual Codex/subagent-backed run:

```bash
python3 scripts/run_experiment.py benchmark/problems/basic_lean_01.jsonl --backend manual --run-id basic_manual_01
```

Each agent call writes a prompt to `logs/<run_id>/pending/<call_id>_prompt.md` and waits for `logs/<run_id>/pending/<call_id>_response.json`. Open the prompt, send it to Codex or a subagent, save the JSON response file, and the experiment will continue.

For an automated Codex CLI run:

```bash
python3 scripts/run_experiment.py benchmark/problems/basic_lean_01.jsonl --backend codex_subagents --subagent-reasoning-effort low --run-id basic_codex_01
```

This runs one isolated `codex exec` task per agent call. `direct` uses one task per proof attempt, `uniform` starts one worker task per approach in the round, and `pi` first starts a PI planning task before starting worker tasks from the PI assignments. Lean is still run locally by the harness after every worker response.

Useful environment variables:

- `CODEX_SUBAGENT_COMMAND`: override the Codex CLI command.
- `CODEX_SUBAGENT_MODEL`: pass a model to Codex.
- `CODEX_SUBAGENT_REASONING_EFFORT`: set Codex reasoning effort, for example `low`, `medium`, `high`, or `xhigh`.
- `CODEX_SUBAGENT_EXTRA_ARGS`: append other extra `codex exec` flags.
- `CODEX_SUBAGENT_MAX_PARALLEL`: cap concurrent worker tasks.
- `CODEX_SUBAGENT_TIMEOUT_SECONDS`: set a per-task timeout.

## Benchmark Validation

`basic_lean_02` keeps public problems and private reference proofs separate:

```bash
python3 scripts/validate_benchmark.py benchmark/problems/basic_lean_02.jsonl --solutions benchmark/solutions/basic_lean_02_solutions.jsonl
```

To run a tiny-budget direct probe through the manual backend:

```bash
python3 scripts/run_direct_probe.py benchmark/problems/basic_lean_02.jsonl
```

`basic_lean_03` is the allocation-sensitive suite. Public problem IDs and theorem names are anonymized (`b3_p001`, `theorem_b3_p001`, ...), while route/category labels live only in solution-side metadata.

Generate or refresh the candidate/final files:

```bash
python3 scripts/generate_basic_lean_03.py
```

The generator writes a validated starting selection from a 50-problem candidate
pool. After low-reasoning direct/uniform probe summaries exist, rerun
`scripts/select_basic_lean_03.py` to replace that starting selection with an
empirically filtered one.

Validate the full candidate pool and the selected final suite:

```bash
python3 scripts/validate_benchmark.py benchmark/candidates/basic_lean_03_candidates.jsonl \
  --solutions benchmark/candidates/basic_lean_03_candidate_solutions.jsonl

python3 scripts/validate_benchmark.py benchmark/problems/basic_lean_03.jsonl \
  --solutions benchmark/solutions/basic_lean_03_solutions.jsonl
```

Probe and select:

```bash
python3 scripts/run_direct_probe.py benchmark/candidates/basic_lean_03_candidates.jsonl \
  --config config/basic_lean_03_probe.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id basic03_direct_probe_01 \
  --limit 30

python3 scripts/run_uniform_probe.py benchmark/candidates/basic_lean_03_candidates.jsonl \
  --config config/basic_lean_03_allocation.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id basic03_uniform_probe_01 \
  --limit 30

python3 scripts/select_basic_lean_03.py \
  --candidates benchmark/candidates/basic_lean_03_candidates.jsonl \
  --solutions benchmark/candidates/basic_lean_03_candidate_solutions.jsonl \
  --direct-summary logs/basic03_direct_probe_01/summary.csv \
  --uniform-summary logs/basic03_uniform_probe_01/summary.csv \
  --out-problems benchmark/problems/basic_lean_03.jsonl \
  --out-solutions benchmark/solutions/basic_lean_03_solutions.jsonl \
  --out-rejected benchmark/candidates/basic_lean_03_rejected.jsonl \
  --out-rejected-solutions benchmark/candidates/basic_lean_03_rejected_solutions.jsonl
```

Run the allocation benchmark:

```bash
python3 scripts/run_experiment.py benchmark/problems/basic_lean_03.jsonl \
  --config config/basic_lean_03_allocation.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id basic03_low_01
```

## Configuration

The default configuration is in `config/default.yaml`.

Important budget fields:

- `max_rounds`
- `workers_per_round`
- `max_llm_calls`
- `max_lean_calls`
- `max_wall_seconds`
- `lean_timeout_seconds`
- `max_estimated_tokens`

`max_estimated_tokens` is optional. Token estimates are approximate and based on prompt/response text length, which is useful for local Codex-driven runs where exact API billing metadata is unavailable.

## Logs

Each run writes:

```text
logs/<run_id>/
  config.yaml
  problems.jsonl
  events.jsonl
  prompts/
  responses/
  lean/
  pending/
  codex_subagents/
  summary.csv
  aggregate_summary.csv
  approach_trace.csv
```

The event log is append-only JSONL. `approach_trace.csv` records per-round worker/PI activity, including approaches tried, worker progress claims, Lean success, and PI belief scores when available.

## Mathlib Notes

Toy problems can run with plain `lean`. Mathlib reconstruction should use a Lake project with a pinned Lean toolchain and compatible Mathlib revision. Avoid using Mathlib `master` blindly for reproducibility.

The official Mathlib workflow recommends using cached build artifacts with `lake exe cache get`; without those cached artifacts, building Mathlib locally can be very slow.
