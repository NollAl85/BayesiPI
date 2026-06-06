# Lean PI Experiment Harness

This repository is a local research harness for testing whether a PI-style agent can improve Lean theorem-proving efficiency by allocating effort across proof approaches better than direct search or uniform multi-agent search.

The focus is not production theorem proving. The focus is whether structured progress assessment and belief-guided allocation improve use of a fixed budget.

## Conditions

The harness compares three conditions:

1. `direct`: one agent repeatedly proposes a proof, runs Lean, inspects errors, and retries.
2. `uniform`: multiple workers explore fixed proof approaches with equal budget and no reallocation.
3. `pi_initial_only`: a PI agent creates the initial allocation, but later PI belief updates are disabled.
4. `pi`: a PI agent proposes approaches, evaluates worker reports, updates beliefs, and reallocates effort.

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

The abandoned `basic_lean_03` synthetic benchmark branch is intentionally not merged. Low-reasoning direct Codex solved every selected task in one round and one Lean call, so that suite is saturated and not useful for PI-vs-uniform allocation analysis.

## Real Lean Tasks

`real_lean_01` is the replacement direction. It is based on real Lean proof obligations supplied through a generic JSONL adapter, then filtered by direct low-reasoning difficulty.

Generic input rows for `scripts/ingest_real_lean_tasks.py` may contain:

```json
{
  "problem_id": "real01_p001",
  "source": "sorrydb_or_local_project",
  "imports": ["Mathlib"],
  "context": "local definitions, namespaces, and setup",
  "statement": "theorem target ... : ...",
  "full_lean_source": "optional full file containing {{proof}} or sorry",
  "proof_placeholder": "{{proof}}",
  "project_root": "optional Lake project root",
  "module_path": "optional source module path",
  "theorem_name": "optional public theorem name",
  "reference_proof": "optional private validation proof",
  "metadata": {"public": "metadata only"}
}
```

The ingester writes public problems and optional private solutions separately:

```bash
python3 scripts/ingest_real_lean_tasks.py local_real_tasks.jsonl \
  --out-problems benchmark/candidates/real_lean_01_candidates.jsonl \
  --out-solutions benchmark/solutions/real_lean_01_solutions.jsonl
```

Run the cheapest empirical gate first:

```bash
CODEX_SUBAGENT_MAX_PARALLEL=1 \
CODEX_SUBAGENT_TIMEOUT_SECONDS=300 \
CODEX_SUBAGENT_EXTRA_ARGS="--ignore-user-config --ignore-rules" \
python3 scripts/probe_tasks.py benchmark/candidates/real_lean_01_candidates.jsonl \
  --config config/real_lean_01_probe.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --condition direct \
  --run-id real01_direct_probe_low_01
```

Then select only tasks that survive hard direct-probe filtering:

```bash
python3 scripts/select_real_lean_01.py \
  --candidates benchmark/candidates/real_lean_01_candidates.jsonl \
  --direct-summary logs/real01_direct_probe_low_01/summary.csv \
  --out-problems benchmark/problems/real_lean_01.jsonl
```

The selector fails loudly if fewer than 20 tasks survive, with the message `Candidate pool too easy: only X tasks survived. Import harder real tasks.` Do not override that by silently selecting one-call direct solves.

After selection, run the allocation benchmark:

```bash
python3 scripts/run_experiment.py benchmark/problems/real_lean_01.jsonl \
  --config config/real_lean_01_allocation.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id real01_low_01
```

## HTPI/SorryDB Pilot

The first real-task pilot uses HTPI/SorryDB-style proof obligations from `benchmark/problems/sorrydb_htpi_10_pilot.jsonl`.
These are real Lean `sorry` tasks reconstructed from HTPI rows in the SorryDB evaluation split, with local Lean checking through the pinned HTPI Lake project.

The direct-low gate used a deliberately harsh one-shot budget:

- `max_rounds: 1`
- `max_llm_calls: 1`
- `max_lean_calls: 1`

That probe solved 4/10 tasks and failed 6/10 tasks. This is useful for a pilot because the set is not saturated by direct-low, while still leaving some tasks reachable enough to test allocation behavior. The six direct-low failures are stored separately in `benchmark/problems/sorrydb_htpi_direct_failed_6.jsonl`.

Run the full pilot with:

```bash
bash scripts/run_sorrydb_htpi_pilot.sh
```

The script runs:

- `direct`
- `uniform`
- `pi_initial_only`
- `pi`

using `config/sorrydb_htpi_allocation.yaml`, low Codex reasoning, two parallel subagents, and the HTPI `lake env lean` checker. It then writes pilot analysis under `logs/sorrydb_htpi_all_low_01/pilot_analysis/`.

Interpret the outputs in two slices:

- all 10 tasks, for broad cost and success-rate context
- the 6 direct-low failures, which are the primary signal-bearing comparison

The primary scientific question is whether PI-guided allocation solves more direct-failed tasks than uniform allocation, or matches uniform success with fewer Lean calls, LLM calls, or estimated tokens. A strong-looking all-task score is not sufficient by itself; the direct-failed subset is the main comparison.

This is not yet a final benchmark. It is a pilot to test whether PI-style progress assessment improves allocation on real Lean obligations before expanding the problem set.

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
- `uniform_policy`
- `uniform_seed`

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

The event log is append-only JSONL. `approach_trace.csv` is the per-round allocation ledger: it records which approach was tried by direct/uniform/PI workers, worker progress claims, Lean success, proof_found, estimated tokens, and PI belief scores when available.

## Mathlib Notes

Toy problems can run with plain `lean`. Mathlib reconstruction should use a Lake project with a pinned Lean toolchain and compatible Mathlib revision. Avoid using Mathlib `master` blindly for reproducibility.

The official Mathlib workflow recommends using cached build artifacts with `lake exe cache get`; without those cached artifacts, building Mathlib locally can be very slow.
