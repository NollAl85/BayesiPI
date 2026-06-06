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
  summary.csv
```

The event log is append-only JSONL and is the main source for later analysis.

## Mathlib Notes

Toy problems can run with plain `lean`. Mathlib reconstruction should use a Lake project with a pinned Lean toolchain and compatible Mathlib revision. Avoid using Mathlib `master` blindly for reproducibility.

The official Mathlib workflow recommends using cached build artifacts with `lake exe cache get`; without those cached artifacts, building Mathlib locally can be very slow.

