from __future__ import annotations

from harness.schemas import Problem


def toy_problems() -> list[Problem]:
    return [
        Problem(
            problem_id="toy_nat_add_zero",
            source="toy",
            theorem_name=None,
            imports=[],
            statement="example (n : Nat) : n + 0 = n",
            hidden_reference_proof="by\n  simpa",
            metadata={"domain": "nat", "difficulty": "trivial"},
        ),
        Problem(
            problem_id="toy_nat_add_comm",
            source="toy",
            theorem_name=None,
            imports=[],
            statement="example (a b : Nat) : a + b = b + a",
            hidden_reference_proof="by\n  exact Nat.add_comm a b",
            metadata={"domain": "nat", "difficulty": "trivial"},
        ),
        Problem(
            problem_id="toy_and_intro",
            source="toy",
            theorem_name=None,
            imports=[],
            statement="example (p q : Prop) (hp : p) (hq : q) : p ∧ q",
            hidden_reference_proof="by\n  exact And.intro hp hq",
            metadata={"domain": "logic", "difficulty": "trivial"},
        ),
    ]

