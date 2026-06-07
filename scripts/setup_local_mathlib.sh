#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Optional local Mathlib setup
============================

real_lean_02 can use Mathlib when a local checkout or Lake project is already
available, but Mathlib is not required. The benchmark generator will also use
local Lake projects containing real Lean files with `sorry`.

To point the harness at an existing Mathlib checkout:

  export MATHLIB_ROOT=/path/to/mathlib-or-lake-project

To point it at another local Lake project with `sorry` obligations:

  export HTPI_ROOT=/path/to/local/lake/project

or:

  export REAL_LEAN_SOURCE_ROOTS=/path/to/project-a:/path/to/project-b

Then run:

  python3 scripts/discover_real_lean_sources.py --out logs/source_discovery.json
  python3 scripts/generate_real_lean_02_candidates.py \
    --source-discovery logs/source_discovery.json \
    --limit 50 \
    --out-candidates benchmark/candidates/real_lean_02_candidates.jsonl \
    --out-solutions benchmark/solutions/real_lean_02_solutions.jsonl

This script intentionally does not clone or install Mathlib automatically.
Create or update local Lean projects outside the harness, then pass their paths
through the environment variables above.
EOF
