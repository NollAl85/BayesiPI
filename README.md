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
- Mathlib reconstruction requires a local Lake/Mathlib checkout. The harness does not use web search during proof runs.

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

Real-task pipeline test coverage includes ingestion public/private splitting, `file_with_hole` rendering, `project_root` subprocess execution, direct-probe selector hard rejection and loud failure modes, probe CSV output, `pi_initial_only` approach tracing, uniform round-robin allocation pressure, and public payload leakage boundaries.

## real_lean_02 Pipeline

`real_lean_02` is the next benchmark pipeline after the HTPI/SorryDB pilot. Its purpose is not to prove as many theorems as possible; it is to find real Lean tasks where allocation matters.

The target empirical regime is:

- `direct_full`: 20-60% solved
- `uniform_constrained`: 40-80% solved
- `pi`: enough remaining headroom to differ from uniform

The primary signal-bearing subset is the `uniform_constrained` failed set, not direct one-shot failures.

Mathlib is preferred, but optional. The source-pluggable path first looks for local Mathlib/Lake projects, then local Lake projects with real Lean files containing `sorry`. It never clones repositories or falls back to synthetic tasks.

Point discovery at known local sources when possible:

```bash
export MATHLIB_ROOT=/path/to/mathlib-or-lake-project
export HTPI_ROOT=/path/to/local/htpi-or-sorrydb-project
export REAL_LEAN_SOURCE_ROOTS=/path/to/project-a:/path/to/project-b
```

All of these variables are optional. Discovery also checks `.`, `..`, `/private/tmp`, `/tmp`, `~/Code`, `~/code`, and `~/Documents`:

```bash
python3 scripts/discover_real_lean_sources.py \
  --roots . .. /private/tmp /tmp \
  --out logs/source_discovery.json
```

Generate candidates from the selected local source:

```bash
python3 scripts/generate_real_lean_02_candidates.py \
  --source-discovery logs/source_discovery.json \
  --limit 300 \
  --out-candidates benchmark/candidates/real_lean_02_candidates.jsonl \
  --out-solutions benchmark/solutions/real_lean_02_solutions.jsonl
```

If a usable Mathlib source is found, generation uses prefix-isolated reconstruction: it copies the original file imports and source prefix before the target declaration, replaces only the target proof with `{{proof}}`, and does not import the module containing the target theorem or broad `Mathlib`. When local `lake env lean` works, Mathlib candidates are checked with the private reference proof and rejected if the original theorem name or a trivial `aesop` proof closes the generated file. Otherwise, generation extracts file-with-hole tasks from local `sorry` declarations.

Public problems use anonymized theorem names like `real02_target_001` and no source module path. Original target theorem names, source paths, validation results, and reference proofs stay in the private solutions file; local `sorry` tasks write no reference solution unless one genuinely exists.

The older Mathlib-only sampler is still available when you explicitly want it:

```bash
python3 scripts/sample_mathlib_real_lean_02.py /path/to/mathlib-or-lake-project \
  --limit 100 \
  --validate-candidates \
  --out-candidates benchmark/candidates/real_lean_02_candidates.jsonl \
  --out-solutions benchmark/solutions/real_lean_02_solutions.jsonl
```

Audit the generated candidates for leakage before running expensive probes:

```bash
python3 scripts/audit_real_lean_02_candidates.py \
  --candidates benchmark/candidates/real_lean_02_candidates.jsonl \
  --solutions benchmark/solutions/real_lean_02_solutions.jsonl \
  --out logs/real_lean_02_leak_audit.csv
```

For local setup guidance without running any install:

```bash
bash scripts/setup_local_mathlib.sh
```

Run the three difficulty probes:

```bash
python3 scripts/probe_real_lean_02.py benchmark/candidates/real_lean_02_candidates.jsonl \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --probe all
```

This uses:

- `config/real_lean_02_direct_one_shot.yaml`
- `config/real_lean_02_direct_full.yaml`
- `config/real_lean_02_uniform_constrained.yaml`

Select the final benchmark only after `direct_full` and `uniform_constrained` probes exist:

```bash
python3 scripts/select_real_lean_02.py \
  --candidates benchmark/candidates/real_lean_02_candidates.jsonl \
  --solutions benchmark/solutions/real_lean_02_solutions.jsonl \
  --direct-one-shot-summary logs/real_lean_02_direct_one_shot/summary.csv \
  --direct-full-summary logs/real_lean_02_direct_full/summary.csv \
  --uniform-constrained-summary logs/real_lean_02_uniform_constrained/summary.csv \
  --out-problems benchmark/problems/real_lean_02.jsonl
```

The selector hard-rejects candidates solved by `direct_full`, candidates solved by `uniform_constrained` in one round, any direct one-shot solve when that probe is supplied, candidates where the original theorem is available in the generated environment, candidates with trivial reference proofs, reference proofs under 10 meaningful lines, candidates with failed or missing Mathlib validation, candidates with local setup failures, public payloads that leak private source information, and theorem statements that are too short or syntactic. If fewer than 20 candidates survive, it fails with:

```text
Candidate pool too easy or too small: only X survived.
Add harder local Lean sources or provide Mathlib/HTPI/SorryDB roots.
```

Run final allocation with:

```bash
python3 scripts/run_experiment.py benchmark/problems/real_lean_02.jsonl \
  --config config/real_lean_02_allocation.yaml \
  --backend codex_subagents \
  --subagent-reasoning-effort low \
  --run-id real02_low_01
```

Then analyze:

```bash
python3 scripts/analyze_real_lean_02.py \
  --summary logs/real02_low_01/summary.csv \
  --approach-trace logs/real02_low_01/approach_trace.csv \
  --direct-full-summary logs/real_lean_02_direct_full/summary.csv \
  --uniform-constrained-summary logs/real_lean_02_uniform_constrained/summary.csv \
  --out-dir logs/real02_low_01/real_lean_02_analysis
```

The analysis reports all-task aggregates, direct-full-failed aggregates, uniform-constrained-failed aggregates, solving approaches, PI belief traces, and whether PI changed beliefs after failed workers.

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
