from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    candidates = _build_candidates()
    selected_ids = {
        "b3_p002",
        "b3_p003",
        "b3_p004",
        "b3_p006",
        "b3_p008",
        "b3_p010",
        "b3_p012",
        "b3_p014",
        "b3_p016",
        "b3_p018",
        "b3_p020",
        "b3_p022",
        "b3_p024",
        "b3_p026",
        "b3_p028",
        "b3_p030",
        "b3_p034",
        "b3_p038",
        "b3_p042",
        "b3_p048",
    }
    selected = [item for item in candidates if item["problem"]["problem_id"] in selected_ids]
    rejected = [item for item in candidates if item["problem"]["problem_id"] not in selected_ids]

    _write_problem_jsonl(PROJECT_ROOT / "benchmark/candidates/basic_lean_03_candidates.jsonl", candidates)
    _write_solution_jsonl(PROJECT_ROOT / "benchmark/candidates/basic_lean_03_candidate_solutions.jsonl", candidates)
    _write_problem_jsonl(PROJECT_ROOT / "benchmark/problems/basic_lean_03.jsonl", selected)
    _write_solution_jsonl(PROJECT_ROOT / "benchmark/solutions/basic_lean_03_solutions.jsonl", selected)
    _write_problem_jsonl(PROJECT_ROOT / "benchmark/candidates/basic_lean_03_rejected.jsonl", rejected)
    _write_solution_jsonl(PROJECT_ROOT / "benchmark/candidates/basic_lean_03_rejected_solutions.jsonl", rejected)


def _build_candidates() -> list[dict]:
    builders: list[tuple[str, Callable[[int], tuple[str, str]], str]] = [
        ("accumulator", _len_aux_right, "tail-recursive length accumulator"),
        ("accumulator", _len_aux_left, "left-accumulating length accumulator"),
        ("accumulator", _sum_aux_right, "tail-recursive sum accumulator"),
        ("list_recursion", _len_append, "custom length over append"),
        ("list_recursion", _map_append, "custom map over append"),
        ("list_bool", _all_append, "custom all over append"),
        ("list_bool", _any_append, "custom any over append"),
        ("custom_membership", _member_append_left, "custom membership preserved by append"),
        ("custom_filter", _filter_member_original, "custom filter membership implies original membership"),
        ("tree_recursion", _tree_size_map, "tree size preserved by map"),
        ("tree_recursion", _tree_size_mirror, "tree size preserved by mirror"),
        ("tree_recursion", _tree_mirror_involution, "tree mirror involution"),
        ("tree_recursion", _tree_map_id, "tree map identity"),
        ("tree_recursion", _tree_map_comp, "tree map composition"),
        ("tree_recursion", _tree_count_mirror, "tree count preserved by mirror"),
        ("nat_recursion", _nat_add, "custom Nat addition"),
        ("nat_recursion", _nat_double, "custom doubling"),
        ("quantifier", _exists_forall, "exists to pointwise exists"),
        ("quantifier", _forall_pair_split, "split paired universal evidence"),
        ("misleading", _option_witness, "finite cases with tempting simplification-only route"),
    ]
    candidates = []
    for index in range(1, 51):
        family, builder, private_label = builders[(index - 1) % len(builders)]
        statement, proof = builder(index)
        problem_id = f"b3_p{index:03d}"
        theorem_name = f"theorem_b3_p{index:03d}"
        candidates.append(
            {
                "problem": {
                    "problem_id": problem_id,
                    "source": "basic_lean_03",
                    "theorem_name": theorem_name,
                    "imports": [],
                    "statement": statement,
                    "metadata": {"suite": "basic_lean_03"},
                },
                "solution": {
                    "problem_id": problem_id,
                    "reference_proof": proof,
                    "metadata": {
                        "private_family": family,
                        "private_label": private_label,
                        "candidate_index": index,
                    },
                },
            }
        )
    return candidates


def _len_aux_right(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α : Type}} : List α → Nat
| [] => 0
| _ :: xs => b3_f{n} xs + 1

def b3_g{n} {{α : Type}} : List α → Nat → Nat
| [], acc => acc
| _ :: xs, acc => b3_g{n} xs (acc + 1)

theorem theorem_b3_p{n} {{α : Type}} (xs : List α) (acc : Nat) :
    b3_g{n} xs acc = b3_f{n} xs + acc""",
        f"""by
  induction xs generalizing acc with
  | nil => simp [b3_g{n}, b3_f{n}]
  | cons x xs ih =>
      simp [b3_g{n}, b3_f{n}, ih, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _len_aux_left(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α : Type}} : List α → Nat
| [] => 0
| _ :: xs => b3_f{n} xs + 1

def b3_g{n} {{α : Type}} : List α → Nat → Nat
| [], acc => acc
| _ :: xs, acc => b3_g{n} xs (1 + acc)

theorem theorem_b3_p{n} {{α : Type}} (xs : List α) (acc : Nat) :
    b3_g{n} xs acc = acc + b3_f{n} xs""",
        f"""by
  induction xs generalizing acc with
  | nil => simp [b3_g{n}, b3_f{n}]
  | cons x xs ih =>
      simp [b3_g{n}, b3_f{n}, ih, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _sum_aux_right(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} : List Nat → Nat
| [] => 0
| x :: xs => x + b3_f{n} xs

def b3_g{n} : List Nat → Nat → Nat
| [], acc => acc
| x :: xs, acc => b3_g{n} xs (acc + x)

theorem theorem_b3_p{n} (xs : List Nat) (acc : Nat) :
    b3_g{n} xs acc = acc + b3_f{n} xs""",
        f"""by
  induction xs generalizing acc with
  | nil => simp [b3_g{n}, b3_f{n}]
  | cons x xs ih =>
      simp [b3_g{n}, b3_f{n}, ih, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _len_append(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α : Type}} : List α → Nat
| [] => 0
| _ :: xs => b3_f{n} xs + 1

theorem theorem_b3_p{n} {{α : Type}} (xs ys : List α) :
    b3_f{n} (xs ++ ys) = b3_f{n} xs + b3_f{n} ys""",
        f"""by
  induction xs with
  | nil => simp [b3_f{n}]
  | cons x xs ih =>
      simp [b3_f{n}, ih, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _map_append(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α β : Type}} (h : α → β) : List α → List β
| [] => []
| x :: xs => h x :: b3_f{n} h xs

theorem theorem_b3_p{n} {{α β : Type}} (h : α → β) (xs ys : List α) :
    b3_f{n} h (xs ++ ys) = b3_f{n} h xs ++ b3_f{n} h ys""",
        f"""by
  induction xs with
  | nil => rfl
  | cons x xs ih => simp [b3_f{n}, ih]""",
    )


def _all_append(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α : Type}} (p : α → Bool) : List α → Bool
| [] => true
| x :: xs => p x && b3_f{n} p xs

theorem theorem_b3_p{n} {{α : Type}} (p : α → Bool) (xs ys : List α) :
    b3_f{n} p (xs ++ ys) = (b3_f{n} p xs && b3_f{n} p ys)""",
        f"""by
  induction xs with
  | nil => simp [b3_f{n}]
  | cons x xs ih => simp [b3_f{n}, ih, Bool.and_assoc]""",
    )


def _any_append(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α : Type}} (p : α → Bool) : List α → Bool
| [] => false
| x :: xs => p x || b3_f{n} p xs

theorem theorem_b3_p{n} {{α : Type}} (p : α → Bool) (xs ys : List α) :
    b3_f{n} p (xs ++ ys) = (b3_f{n} p xs || b3_f{n} p ys)""",
        f"""by
  induction xs with
  | nil => simp [b3_f{n}]
  | cons x xs ih => simp [b3_f{n}, ih, Bool.or_assoc]""",
    )


def _member_append_left(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} {{α : Type}} (z : α) : List α → Prop
| [] => False
| x :: xs => x = z ∨ b3_f{n} z xs

theorem theorem_b3_p{n} {{α : Type}} (z : α) (xs ys : List α) :
    b3_f{n} z xs → b3_f{n} z (xs ++ ys)""",
        f"""by
  induction xs with
  | nil => intro h; cases h
  | cons x xs ih =>
      intro h
      cases h with
      | inl hx => exact Or.inl hx
      | inr ht => exact Or.inr (ih ht)""",
    )


def _filter_member_original(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_m{n} {{α : Type}} (z : α) : List α → Prop
| [] => False
| x :: xs => x = z ∨ b3_m{n} z xs

def b3_f{n} {{α : Type}} (p : α → Bool) : List α → List α
| [] => []
| x :: xs => if p x then x :: b3_f{n} p xs else b3_f{n} p xs

theorem theorem_b3_p{n} {{α : Type}} (p : α → Bool) (z : α) (xs : List α) :
    b3_m{n} z (b3_f{n} p xs) → b3_m{n} z xs""",
        f"""by
  induction xs with
  | nil => intro h; cases h
  | cons x xs ih =>
      intro h
      cases hp : p x with
      | false =>
          simp [b3_f{n}, hp] at h
          exact Or.inr (ih h)
      | true =>
          simp [b3_f{n}, hp] at h
          cases h with
          | inl hx => exact Or.inl hx
          | inr ht => exact Or.inr (ih ht)""",
    )


def _tree_size_map(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""inductive B3T{n} (α : Type) where
| leaf : B3T{n} α
| node : B3T{n} α → α → B3T{n} α → B3T{n} α

def b3_f{n} {{α : Type}} : B3T{n} α → Nat
| .leaf => 0
| .node l _ r => b3_f{n} l + b3_f{n} r + 1

def b3_g{n} {{α β : Type}} (h : α → β) : B3T{n} α → B3T{n} β
| .leaf => .leaf
| .node l x r => .node (b3_g{n} h l) (h x) (b3_g{n} h r)

theorem theorem_b3_p{n} {{α β : Type}} (h : α → β) (t : B3T{n} α) :
    b3_f{n} (b3_g{n} h t) = b3_f{n} t""",
        f"""by
  induction t with
  | leaf => rfl
  | node l x r ihl ihr => simp [b3_f{n}, b3_g{n}, ihl, ihr]""",
    )


def _tree_size_mirror(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""inductive B3T{n} (α : Type) where
| leaf : B3T{n} α
| node : B3T{n} α → α → B3T{n} α → B3T{n} α

def b3_f{n} {{α : Type}} : B3T{n} α → Nat
| .leaf => 0
| .node l _ r => b3_f{n} l + b3_f{n} r + 1

def b3_g{n} {{α : Type}} : B3T{n} α → B3T{n} α
| .leaf => .leaf
| .node l x r => .node (b3_g{n} r) x (b3_g{n} l)

theorem theorem_b3_p{n} {{α : Type}} (t : B3T{n} α) :
    b3_f{n} (b3_g{n} t) = b3_f{n} t""",
        f"""by
  induction t with
  | leaf => rfl
  | node l x r ihl ihr =>
      simp [b3_f{n}, b3_g{n}, ihl, ihr, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _tree_mirror_involution(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""inductive B3T{n} (α : Type) where
| leaf : B3T{n} α
| node : B3T{n} α → α → B3T{n} α → B3T{n} α

def b3_f{n} {{α : Type}} : B3T{n} α → B3T{n} α
| .leaf => .leaf
| .node l x r => .node (b3_f{n} r) x (b3_f{n} l)

theorem theorem_b3_p{n} {{α : Type}} (t : B3T{n} α) :
    b3_f{n} (b3_f{n} t) = t""",
        f"""by
  induction t with
  | leaf => rfl
  | node l x r ihl ihr => simp [b3_f{n}, ihl, ihr]""",
    )


def _tree_map_id(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""inductive B3T{n} (α : Type) where
| leaf : B3T{n} α
| node : B3T{n} α → α → B3T{n} α → B3T{n} α

def b3_f{n} {{α β : Type}} (h : α → β) : B3T{n} α → B3T{n} β
| .leaf => .leaf
| .node l x r => .node (b3_f{n} h l) (h x) (b3_f{n} h r)

theorem theorem_b3_p{n} {{α : Type}} (t : B3T{n} α) :
    b3_f{n} (fun x => x) t = t""",
        f"""by
  induction t with
  | leaf => rfl
  | node l x r ihl ihr => simp [b3_f{n}, ihl, ihr]""",
    )


def _tree_map_comp(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""inductive B3T{n} (α : Type) where
| leaf : B3T{n} α
| node : B3T{n} α → α → B3T{n} α → B3T{n} α

def b3_f{n} {{α β : Type}} (h : α → β) : B3T{n} α → B3T{n} β
| .leaf => .leaf
| .node l x r => .node (b3_f{n} h l) (h x) (b3_f{n} h r)

theorem theorem_b3_p{n} {{α β γ : Type}} (f : α → β) (g : β → γ) (t : B3T{n} α) :
    b3_f{n} g (b3_f{n} f t) = b3_f{n} (fun x => g (f x)) t""",
        f"""by
  induction t with
  | leaf => rfl
  | node l x r ihl ihr => simp [b3_f{n}, ihl, ihr]""",
    )


def _tree_count_mirror(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""inductive B3T{n} (α : Type) where
| leaf : B3T{n} α
| node : B3T{n} α → α → B3T{n} α → B3T{n} α

def b3_f{n} {{α : Type}} (p : α → Bool) : B3T{n} α → Nat
| .leaf => 0
| .node l x r => b3_f{n} p l + (if p x then 1 else 0) + b3_f{n} p r

def b3_g{n} {{α : Type}} : B3T{n} α → B3T{n} α
| .leaf => .leaf
| .node l x r => .node (b3_g{n} r) x (b3_g{n} l)

theorem theorem_b3_p{n} {{α : Type}} (p : α → Bool) (t : B3T{n} α) :
    b3_f{n} p (b3_g{n} t) = b3_f{n} p t""",
        f"""by
  induction t with
  | leaf => rfl
  | node l x r ihl ihr =>
      cases p x <;> simp [b3_f{n}, b3_g{n}, ihl, ihr, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _nat_add(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} : Nat → Nat → Nat
| 0, m => m
| n + 1, m => b3_f{n} n m + 1

theorem theorem_b3_p{n} (n m : Nat) :
    b3_f{n} n m = n + m""",
        f"""by
  induction n with
  | zero => simp [b3_f{n}]
  | succ n ih => simp [b3_f{n}, ih, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _nat_double(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""def b3_f{n} : Nat → Nat
| 0 => 0
| n + 1 => b3_f{n} n + 2

theorem theorem_b3_p{n} (n : Nat) :
    b3_f{n} n = n + n""",
        f"""by
  induction n with
  | zero => rfl
  | succ n ih =>
      simp [b3_f{n}, ih, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]""",
    )


def _exists_forall(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""theorem theorem_b3_p{n} {{α β : Type}} (r : α → β → Prop) (f : β → β) :
    (∃ x : α, ∀ y : β, r x (f y)) → ∀ y : β, ∃ x : α, r x (f y)""",
        """by
  intro h y
  cases h with
  | intro x hx => exact Exists.intro x (hx y)""",
    )


def _forall_pair_split(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""theorem theorem_b3_p{n} {{α : Type}} (p q r : α → Prop) :
    (∀ x, p x → q x ∧ r x) → (∀ x, p x → q x) ∧ (∀ x, p x → r x)""",
        """by
  intro h
  constructor
  · intro x hp
    exact (h x hp).left
  · intro x hp
    exact (h x hp).right""",
    )


def _option_witness(index: int) -> tuple[str, str]:
    n = f"{index:03d}"
    return (
        f"""theorem theorem_b3_p{n} {{α : Type}} (fallback : α) (o : Option α) :
    (match o with | none => fallback | some x => x) = fallback ∨ ∃ x, o = some x""",
        """by
  cases o with
  | none =>
      exact Or.inl rfl
  | some x =>
      exact Or.inr (Exists.intro x rfl)""",
    )


def _write_problem_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item["problem"], ensure_ascii=False, sort_keys=True) + "\n")


def _write_solution_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item["solution"], ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
