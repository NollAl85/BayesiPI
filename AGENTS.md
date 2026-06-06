# Agent Instructions

## Purpose

This project is a Codex-native research harness for evaluating whether a PI-style coordinator can allocate theorem-proving effort more effectively than direct search or uniform multi-agent search.

The experiment asks:

> Can structured progress assessment and belief-guided allocation improve Lean theorem-proving efficiency under a fixed budget?

The theorem prover is the environment. Progress assessment is the object of study.

## Experimental Conditions

### A. Direct

One agent repeatedly:

- reads the theorem and imports,
- proposes a Lean proof,
- runs Lean,
- inspects errors,
- retries until solved or budget exhausted.

### B. Uniform Multi-Agent

Several workers receive different proof approaches. Each worker receives an equal budget. There is no PI and no reallocation.

### C. PI-Guided Multi-Agent

A PI agent:

- proposes proof approaches,
- assigns workers,
- reads worker reports and Lean feedback,
- evaluates progress quality,
- updates belief and uncertainty scores,
- reallocates remaining effort.

## PI Behavior

The PI must not reward activity for its own sake.

Reward evidence that:

- simplifies the core theorem,
- discovers an invariant,
- reduces proof complexity,
- reveals useful structure,
- closes critical proof obstacles.

Do not overvalue:

- long reports without Lean evidence,
- local lemma plumbing,
- repeated syntax fixes,
- activity that does not reduce the hard part of the theorem.

Progress categories:

- `proof_found`
- `structural_progress`
- `directional_evidence`
- `technical_progress`
- `no_progress`
- `evidence_against`

## Worker Behavior

Workers should stay focused on the assigned approach. They should report honestly when stuck and distinguish technical Lean friction from genuine mathematical obstacles.

Examples of approaches:

- induction,
- contradiction,
- minimal counterexample,
- simplification,
- algebraic normalization,
- extensionality,
- case analysis,
- library search.

## Coding Conventions

- Keep the harness simple and local.
- Use Pydantic models for structured records.
- Use YAML for configuration.
- Do not make network calls during experiment runs.
- Keep Mathlib extraction lightweight.
- Log all prompts, responses, Lean outputs, PI updates, worker reports, and budget counters.
- Never expose `hidden_reference_proof` to agents.
- Public benchmark files live under `benchmark/problems/`.
- Reference proofs live under `benchmark/solutions/` and are validation-only. Agents must not inspect or use these files during experiment runs.
- Agents should work only from generated prompt files, Lean feedback, local imports, and their assigned role.

## Budget Discipline

All conditions must use comparable budgets:

- Lean calls,
- agent calls,
- estimated tokens,
- wall-clock time,
- rounds.

PI calls count against the same agent-call and estimated-token budgets as worker and direct-agent calls.

## Medium-Basic Benchmarks

`basic_lean_02` is intended to create real retries and allocation decisions. Agents should expect:

- induction over `Nat` and `List`,
- custom recursive definitions,
- nested case analysis,
- multi-step rewriting,
- quantifier and witness manipulation,
- Boolean and Option case splits.

The PI should distinguish structural progress, such as the right induction variable or case split, from technical progress, such as fixing a rewrite orientation or syntax error.
