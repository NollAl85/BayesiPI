from __future__ import annotations

from dataclasses import dataclass
import random
import re
from pathlib import Path
from typing import Callable

from harness.lean_runner import LeanRunner
from harness.schemas import Problem


SORRY_RE = re.compile(r"(?<![A-Za-z0-9_])sorry(?![A-Za-z0-9_])")
PROOF_ASSIGN_RE = re.compile(r":=\s*by\b")
DECL_RE = re.compile(
    r"^(?P<prefix>\s*(?:@\[[^\]]+\]\s*)*(?:private\s+|protected\s+)?)"
    r"(?P<kind>theorem|lemma)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.′]*)(?=\s|:|\(|\[|\{|$)"
)
PRIVATE_CONTEXT_RE = re.compile(r"\b(?:private|protected)\b")


@dataclass(frozen=True)
class ExtractedSorryCandidate:
    problem: Problem
    original_name: str
    source_path: str
    source_line: int


@dataclass
class _ContextScope:
    opener: str
    name: str | None
    entries: list["_ContextEntry"]


_ContextEntry = str | _ContextScope


def sample_from_sorry_project(
    *,
    project_root: Path | str,
    limit: int,
    seed: int = 2,
    source: str = "real_lean_02_sorry_project",
    start_index: int = 1,
    validate_candidates: bool = False,
    lean_command: list[str] | None = None,
    lean_timeout_seconds: int = 30,
) -> list[Problem]:
    extracted = extract_sorry_project_candidates(
        project_root=project_root,
        limit=limit,
        seed=seed,
        source=source,
        start_index=start_index,
        validate_candidates=validate_candidates,
        lean_command=lean_command,
        lean_timeout_seconds=lean_timeout_seconds,
    )
    return [candidate.problem for candidate in extracted]


def extract_sorry_project_candidates(
    *,
    project_root: Path | str,
    limit: int,
    seed: int = 2,
    source: str = "real_lean_02_sorry_project",
    start_index: int = 1,
    validate_candidates: bool = False,
    lean_command: list[str] | None = None,
    lean_timeout_seconds: int = 30,
) -> list[ExtractedSorryCandidate]:
    root = Path(project_root)
    files = _candidate_files(root)
    rng = random.Random(seed)
    rng.shuffle(files)
    extracted: list[ExtractedSorryCandidate] = []
    public_index = start_index
    runner = LeanRunner(command=lean_command or ["lake", "env", "lean"], timeout_seconds=lean_timeout_seconds)
    for path in files:
        if len(extracted) >= limit:
            break
        text = _read_text(path)
        if text is None or "sorry" not in text:
            continue
        lines = text.splitlines()
        for line_index, line in enumerate(lines):
            if len(extracted) >= limit:
                break
            match = DECL_RE.match(line)
            if not match:
                continue
            if _has_unsupported_command_modifier(lines[:line_index]):
                continue
            block = _declaration_block(lines, line_index)
            if len(SORRY_RE.findall(block)) != 1:
                continue
            candidate = _build_candidate(
                project_root=root,
                path=path,
                lines=lines,
                declaration_start=line_index,
                block=block,
                original_name=match.group("name"),
                public_index=public_index,
                source=source,
            )
            if candidate is None:
                continue
            problem = candidate.problem
            metadata = dict(problem.metadata)
            metadata["validation_attempted"] = bool(validate_candidates)
            if validate_candidates:
                validation_error = _validation_error(runner, problem)
                if validation_error is not None:
                    continue
                metadata["candidate_validated"] = True
            else:
                metadata["candidate_validated"] = False
            candidate = ExtractedSorryCandidate(
                problem=problem.model_copy(update={"metadata": metadata}),
                original_name=candidate.original_name,
                source_path=candidate.source_path,
                source_line=candidate.source_line,
            )
            extracted.append(candidate)
            public_index += 1
    return extracted


def _build_candidate(
    *,
    project_root: Path,
    path: Path,
    lines: list[str],
    declaration_start: int,
    block: str,
    original_name: str,
    public_index: int,
    source: str,
) -> ExtractedSorryCandidate | None:
    public_problem_id = f"real_lean_02_{public_index:03d}"
    public_name = f"real02_target_{public_index:03d}"
    anonymized = _anonymize_declaration(block, public_name)
    if original_name in anonymized:
        return None
    declaration_with_hole = _with_hole(anonymized)
    context = _public_context(lines[:declaration_start])
    imports = _import_lines(lines)
    full_source = _render_full_source(imports=imports, context=context, declaration_with_hole=declaration_with_hole)
    if original_name in full_source:
        return None
    problem = Problem(
        problem_id=public_problem_id,
        source=source,
        theorem_name=public_name,
        imports=[],
        statement=declaration_with_hole,
        task_type="file_with_hole",
        preamble="",
        full_lean_source=full_source,
        proof_placeholder="{{proof}}",
        project_root=str(project_root),
        module_path=None,
        expected_theorem_name=public_name,
        metadata={
            "source_order": "local_sorry_project",
            "anonymized": True,
            "source_kind": "sorry_project",
            "public_import_count": len(imports),
        },
    )
    return ExtractedSorryCandidate(
        problem=problem,
        original_name=original_name,
        source_path=str(path),
        source_line=declaration_start + 1,
    )


def _candidate_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_root.rglob("*.lean"):
        if any(part in {".git", ".lake", "build", ".pytest_cache", "__pycache__"} for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


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
    prefixes = (
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
    return stripped.startswith(prefixes)


def _anonymize_declaration(block: str, public_name: str) -> str:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        match = DECL_RE.match(line)
        if not match:
            continue
        replacement = DECL_RE.sub(f"theorem {public_name}", line.strip(), count=1)
        lines[index] = line[: len(line) - len(line.lstrip())] + replacement
        return "\n".join(lines)
    raise ValueError("Declaration block has no theorem or lemma header.")


def _with_hole(block: str) -> str:
    match = PROOF_ASSIGN_RE.search(block)
    if match is None:
        raise ValueError("Declaration block has no `:= by` proof assignment.")
    before = block[: match.start()]
    return f"{before.rstrip()} := {{{{proof}}}}"


def _import_lines(lines: list[str]) -> list[str]:
    imports: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.startswith("import "):
            if stripped not in imports:
                imports.append(stripped)
            continue
        if imports and not stripped.startswith("import "):
            break
    return imports


def _public_context(prefix_lines: list[str]) -> list[str]:
    root_entries: list[_ContextEntry] = []
    scope_stack: list[_ContextScope] = []
    for raw_line in prefix_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("import "):
            continue
        if stripped.endswith(" in"):
            continue
        if PRIVATE_CONTEXT_RE.search(stripped):
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
        if stripped in {"noncomputable section", "section"}:
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


def _render_full_source(*, imports: list[str], context: list[str], declaration_with_hole: str) -> str:
    ending = _context_closing_lines(context)
    parts = [*imports, *context, "", declaration_with_hole, *ending]
    return "\n".join(part for part in parts if part is not None).strip() + "\n"


def _validation_error(runner: LeanRunner, problem: Problem) -> str | None:
    sorry_result = runner.check(problem, "by\n  sorry")
    if sorry_result.success:
        return "lean_runner_accepted_sorry"
    if _looks_like_setup_failure(sorry_result.error_summary):
        return "lean_setup_failed"
    skeleton_result = runner.check(problem, "by\n  exact False.elim (by contradiction)")
    if _looks_like_setup_failure(skeleton_result.error_summary):
        return "lean_setup_failed"
    return None


def _looks_like_setup_failure(error_summary: str) -> bool:
    lowered = error_summary.lower()
    markers = (
        "unknown package",
        "unknown module",
        "object file",
        "no such file",
        "failed to load",
        "unknown constant",
        "unknown namespace",
        "invalid import",
        "permission denied",
    )
    return any(marker in lowered for marker in markers)


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
