from __future__ import annotations

from dataclasses import dataclass
import random
import re
from pathlib import Path
from typing import Callable

from benchmark.benchmark import load_jsonl, write_jsonl
from harness.schemas import Problem, ReferenceSolution


DEFAULT_REAL02_PREFIXES = (
    "LinearAlgebra",
    "Topology",
    "Analysis/Calculus",
    "Analysis/Normed",
    "GroupTheory",
    "RingTheory",
    "FieldTheory",
    "Order",
    "MeasureTheory/MeasurableSpace",
)

LOW_LEVEL_PREFIXES = (
    "Data/List",
    "Data/Nat",
    "Data/Bool",
    "Data/Option",
    "Logic",
    "Tactic",
)

DECL_RE = re.compile(
    r"^(?P<prefix>(?:@\[[^\]]+\]\s*)*(?:private\s+|protected\s+)?)"
    r"(?P<kind>theorem|lemma)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.′]*)(?=\s|:|\(|\[|\{|$)"
)
PROOF_ASSIGN_RE = re.compile(r":=\s*by\b")


@dataclass(frozen=True)
class ExtractedTheorem:
    original_name: str
    source_module: str
    source_path: str
    start_line: int
    public_name: str
    declaration_with_hole: str
    full_lean_source: str
    reference_proof: str
    statement: str


@dataclass
class _ContextScope:
    opener: str
    name: str | None
    entries: list["_ContextEntry"]


_ContextEntry = str | _ContextScope


def load_mathlib_reconstruction_jsonl(path: Path | str) -> list[Problem]:
    """Load Mathlib reconstruction problems from the shared JSONL schema."""
    return load_jsonl(path)


def write_mathlib_reconstruction_jsonl(path: Path | str, problems: list[Problem]) -> None:
    """Write Mathlib reconstruction problems in the shared JSONL schema."""
    write_jsonl(path, problems)


def sample_from_local_mathlib(
    *,
    mathlib_root: Path | str,
    limit: int,
    seed: int = 2,
    module_prefixes: list[str] | tuple[str, ...] = DEFAULT_REAL02_PREFIXES,
    project_root: Path | str | None = None,
    public_import: str = "Mathlib",
    source: str = "real_lean_02_mathlib",
) -> list[Problem]:
    problems, _ = sample_from_local_mathlib_with_solutions(
        mathlib_root=mathlib_root,
        limit=limit,
        seed=seed,
        module_prefixes=module_prefixes,
        project_root=project_root,
        public_import=public_import,
        source=source,
    )
    return problems


def sample_from_local_mathlib_with_solutions(
    *,
    mathlib_root: Path | str,
    limit: int,
    seed: int = 2,
    module_prefixes: list[str] | tuple[str, ...] = DEFAULT_REAL02_PREFIXES,
    project_root: Path | str | None = None,
    public_import: str = "Mathlib",
    source: str = "real_lean_02_mathlib",
) -> tuple[list[Problem], list[ReferenceSolution]]:
    mathlib_dir = _resolve_mathlib_dir(Path(mathlib_root))
    lake_root = Path(project_root) if project_root else _infer_project_root(mathlib_dir)
    modules = _candidate_files(mathlib_dir, tuple(module_prefixes))
    rng = random.Random(seed)
    rng.shuffle(modules)

    problems: list[Problem] = []
    solutions: list[ReferenceSolution] = []
    next_index = 1
    for path in modules:
        if len(problems) >= limit:
            break
        for extracted in _extract_theorems_from_file(
            path=path,
            mathlib_dir=mathlib_dir,
            public_index_start=next_index,
            public_import=public_import,
        ):
            problem_id = f"real_lean_02_{next_index:03d}"
            problem = Problem(
                problem_id=problem_id,
                source=source,
                theorem_name=extracted.public_name,
                imports=[],
                statement=extracted.statement,
                task_type="file_with_hole",
                preamble="",
                full_lean_source=extracted.full_lean_source,
                proof_placeholder="{{proof}}",
                project_root=str(lake_root),
                module_path=None,
                expected_theorem_name=extracted.public_name,
                metadata={
                    "source_order": "mathlib_theorem_reconstruction",
                    "public_import": public_import,
                    "anonymized": True,
                },
            )
            solution = ReferenceSolution(
                problem_id=problem_id,
                reference_proof=extracted.reference_proof,
                metadata={
                    "original_theorem_name": extracted.original_name,
                    "source_module": extracted.source_module,
                    "source_path": extracted.source_path,
                    "source_start_line": extracted.start_line,
                    "reference_meaningful_lines": meaningful_proof_lines(extracted.reference_proof),
                },
            )
            problems.append(problem)
            solutions.append(solution)
            next_index += 1
            if len(problems) >= limit:
                break
    if len(problems) < limit:
        raise RuntimeError(
            f"Only sampled {len(problems)} Mathlib candidates from {mathlib_dir}; requested {limit}. "
            "Use a larger local Mathlib checkout or broader module prefixes."
        )
    return problems, solutions


def meaningful_proof_lines(proof: str) -> int:
    count = 0
    for raw_line in proof.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        if line in {"by", "(", ")", "{", "}", "·", "|"}:
            continue
        count += 1
    return count


def _resolve_mathlib_dir(root: Path) -> Path:
    if root.name == "Mathlib" and root.is_dir():
        return root
    candidate = root / "Mathlib"
    if candidate.is_dir():
        return candidate
    lake_candidate = root / ".lake" / "packages" / "mathlib" / "Mathlib"
    if lake_candidate.is_dir():
        return lake_candidate
    raise FileNotFoundError(
        f"Could not find a Mathlib directory under {root}. Pass the Mathlib directory or a Lake project root."
    )


def _infer_project_root(mathlib_dir: Path) -> Path:
    if mathlib_dir.parent.name == "mathlib":
        return mathlib_dir.parent
    return mathlib_dir.parent


def _candidate_files(mathlib_dir: Path, module_prefixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for prefix in module_prefixes:
        root = mathlib_dir / prefix
        if root.is_file() and root.suffix == ".lean":
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.lean"))
    filtered = []
    for path in files:
        rel = path.relative_to(mathlib_dir).as_posix()
        if any(rel.startswith(prefix) for prefix in LOW_LEVEL_PREFIXES):
            continue
        if rel.endswith("Basic.lean") or rel.endswith("Defs.lean"):
            continue
        filtered.append(path)
    return sorted(set(filtered))


def _extract_theorems_from_file(
    *,
    path: Path,
    mathlib_dir: Path,
    public_index_start: int,
    public_import: str,
) -> list[ExtractedTheorem]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    source_module = "Mathlib/" + path.relative_to(mathlib_dir).with_suffix("").as_posix()
    extracted: list[ExtractedTheorem] = []
    public_index = public_index_start
    for index, line in enumerate(lines):
        match = DECL_RE.match(line.strip())
        if not match:
            continue
        if _has_unsupported_command_modifier(lines[:index]):
            continue
        block = _declaration_block(lines, index)
        if not _has_by_proof_assignment(block):
            continue
        reference_proof = _reference_proof(block)
        if meaningful_proof_lines(reference_proof) < 8:
            continue
        original_name = match.group("name")
        if original_name in reference_proof:
            continue
        public_name = f"real02_target_{public_index:03d}"
        anonymized_decl = _anonymize_declaration(block, public_name)
        if original_name in anonymized_decl:
            continue
        context = _public_context(lines[:index])
        full_source = _render_full_source(
            context=context,
            declaration_with_hole=_with_hole(anonymized_decl),
            public_import=public_import,
        )
        statement = _statement_from_declaration(_with_hole(anonymized_decl))
        extracted.append(
            ExtractedTheorem(
                original_name=original_name,
                source_module=source_module,
                source_path=str(path),
                start_line=index + 1,
                public_name=public_name,
                declaration_with_hole=_with_hole(anonymized_decl),
                full_lean_source=full_source,
                reference_proof=reference_proof,
                statement=statement,
            )
        )
        public_index += 1
    return extracted


def _declaration_block(lines: list[str], start_index: int) -> str:
    block: list[str] = []
    for offset, line in enumerate(lines[start_index:]):
        stripped = line.strip()
        if offset > 0 and block and _top_level_boundary(stripped, line):
            break
        block.append(line)
    return "\n".join(block).rstrip()


def _top_level_boundary(stripped: str, raw_line: str) -> bool:
    if not stripped or raw_line[:1].isspace():
        return False
    boundary_prefixes = (
        "@[",
        "theorem ",
        "lemma ",
        "def ",
        "abbrev ",
        "instance ",
        "class ",
        "structure ",
        "inductive ",
        "namespace ",
        "section ",
        "end ",
    )
    return stripped.startswith(boundary_prefixes)


def _reference_proof(block: str) -> str:
    match = _proof_assignment_match(block)
    return block[match.start() + 2 :].strip()


def _anonymize_declaration(block: str, public_name: str) -> str:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        match = DECL_RE.match(line.strip())
        if match:
            indent = line[: len(line) - len(line.lstrip())]
            replacement = DECL_RE.sub(f"theorem {public_name}", line.strip(), count=1)
            lines[index] = indent + replacement
            return "\n".join(lines)
    raise ValueError("Declaration block has no theorem or lemma header.")


def _with_hole(block: str) -> str:
    match = _proof_assignment_match(block)
    before = block[: match.start()]
    return f"{before.rstrip()} := {{{{proof}}}}"


def _statement_from_declaration(block_with_hole: str) -> str:
    return block_with_hole.strip()


def _has_by_proof_assignment(block: str) -> bool:
    return PROOF_ASSIGN_RE.search(block) is not None


def _proof_assignment_match(block: str) -> re.Match[str]:
    match = PROOF_ASSIGN_RE.search(block)
    if not match:
        raise ValueError("Declaration block has no `:= by` proof assignment.")
    return match


def _public_context(prefix_lines: list[str]) -> list[str]:
    root_entries: list[_ContextEntry] = []
    scope_stack: list[_ContextScope] = []
    for raw_line in prefix_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.endswith(" in"):
            continue
        if stripped.startswith("namespace "):
            _push_context_scope(
                root_entries,
                scope_stack,
                opener=stripped,
                name=stripped.removeprefix("namespace ").strip(),
            )
            continue
        if stripped.startswith("end "):
            ended = stripped.removeprefix("end ").strip()
            _pop_context_scope(root_entries, scope_stack, ended)
            continue
        if stripped in {"section", "noncomputable section"}:
            _push_context_scope(root_entries, scope_stack, opener=stripped, name=None)
            continue
        if stripped.startswith("open ") or stripped.startswith("open scoped "):
            _append_context_entry(root_entries, scope_stack, stripped)
            continue
        if stripped.startswith("local notation ") or stripped.startswith("notation "):
            _append_context_entry(root_entries, scope_stack, stripped)
            continue
        if stripped.startswith("variable ") or stripped.startswith("variables "):
            _append_context_entry(root_entries, scope_stack, stripped)
            continue
    return _trim_context(_flatten_context_entries(root_entries))


def _has_unsupported_command_modifier(prefix_lines: list[str]) -> bool:
    for raw_line in reversed(prefix_lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("@["):
            continue
        return stripped.endswith(" in")
    return False


def _render_full_source(*, context: list[str], declaration_with_hole: str, public_import: str) -> str:
    ending = _context_closing_lines(context)
    parts = [f"import {public_import}", *context, "", declaration_with_hole, *ending]
    return "\n".join(parts).strip() + "\n"


def _append_context_entry(
    root_entries: list[_ContextEntry],
    scope_stack: list[_ContextScope],
    value: str,
) -> None:
    entries = scope_stack[-1].entries if scope_stack else root_entries
    entries.append(value)


def _push_context_scope(
    root_entries: list[_ContextEntry],
    scope_stack: list[_ContextScope],
    *,
    opener: str,
    name: str | None,
) -> None:
    scope = _ContextScope(opener=opener, name=name, entries=[])
    _append_context_scope(root_entries, scope_stack, scope)
    scope_stack.append(scope)


def _append_context_scope(
    root_entries: list[_ContextEntry],
    scope_stack: list[_ContextScope],
    scope: _ContextScope,
) -> None:
    entries = scope_stack[-1].entries if scope_stack else root_entries
    entries.append(scope)


def _pop_context_scope(
    root_entries: list[_ContextEntry],
    scope_stack: list[_ContextScope],
    ended_name: str,
) -> None:
    if not scope_stack:
        return
    target_index = len(scope_stack) - 1
    if ended_name:
        for index in range(len(scope_stack) - 1, -1, -1):
            if scope_stack[index].name == ended_name:
                target_index = index
                break
        else:
            return
    while len(scope_stack) > target_index:
        scope = scope_stack.pop()
        parent_entries = scope_stack[-1].entries if scope_stack else root_entries
        if scope in parent_entries:
            parent_entries.remove(scope)


def _flatten_context_entries(entries: list[_ContextEntry]) -> list[str]:
    flattened: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            flattened.append(entry)
        else:
            flattened.append(entry.opener)
            flattened.extend(_flatten_context_entries(entry.entries))
    return flattened


def _trim_context(context: list[str]) -> list[str]:
    keep = set(range(len(context)))
    _drop_earliest_matching(context, keep, lambda line: line.startswith("open "), 20)
    _drop_earliest_matching(
        context,
        keep,
        lambda line: line.startswith("local notation ") or line.startswith("notation "),
        20,
    )
    _drop_earliest_matching(
        context,
        keep,
        lambda line: line.startswith("variable ") or line.startswith("variables "),
        60,
    )
    return [line for index, line in enumerate(context) if index in keep]


def _drop_earliest_matching(
    context: list[str],
    keep: set[int],
    predicate: Callable[[str], bool],
    max_count: int,
) -> None:
    indices = [index for index, line in enumerate(context) if predicate(line)]
    for index in indices[: max(0, len(indices) - max_count)]:
        keep.discard(index)


def _context_closing_lines(context: list[str]) -> list[str]:
    endings: list[str] = []
    for line in context:
        if line.startswith("namespace "):
            endings.append(f"end {line.removeprefix('namespace ').strip()}")
        elif line in {"section", "noncomputable section"}:
            endings.append("end")
    return list(reversed(endings))
