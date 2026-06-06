from __future__ import annotations

from dataclasses import dataclass
import random
import re
from pathlib import Path

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
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)\b"
)


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
        block = _declaration_block(lines, index)
        if ":= by" not in block and ":=\nby" not in block:
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
    seen_assignment = False
    for line in lines[start_index:]:
        stripped = line.strip()
        if seen_assignment and block and _top_level_boundary(stripped, line):
            break
        block.append(line)
        if ":=" in line:
            seen_assignment = True
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
    _, proof = block.split(":=", 1)
    return proof.strip()


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
    before, _ = block.split(":=", 1)
    return f"{before.rstrip()} := {{{{proof}}}}"


def _statement_from_declaration(block_with_hole: str) -> str:
    return block_with_hole.strip()


def _public_context(prefix_lines: list[str]) -> list[str]:
    namespace_stack: list[str] = []
    opens: list[str] = []
    variables: list[str] = []
    noncomputable = False
    for raw_line in prefix_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.startswith("namespace "):
            namespace_stack.append(stripped.removeprefix("namespace ").strip())
            continue
        if stripped.startswith("end "):
            ended = stripped.removeprefix("end ").strip()
            if namespace_stack and (not ended or namespace_stack[-1] == ended):
                namespace_stack.pop()
            continue
        if stripped.startswith("noncomputable section"):
            noncomputable = True
            continue
        if stripped.startswith("open ") or stripped.startswith("open scoped "):
            _append_unique(opens, stripped)
            continue
        if stripped.startswith("variable ") or stripped.startswith("variables "):
            _append_unique(variables, stripped)
            continue
    context: list[str] = []
    if noncomputable:
        context.append("noncomputable section")
    context.extend(opens[-20:])
    context.extend(f"namespace {name}" for name in namespace_stack)
    context.extend(variables[-40:])
    return context


def _render_full_source(*, context: list[str], declaration_with_hole: str, public_import: str) -> str:
    namespace_names = [
        line.removeprefix("namespace ").strip()
        for line in context
        if line.startswith("namespace ")
    ]
    has_section = "noncomputable section" in context
    ending = [f"end {name}" for name in reversed(namespace_names)]
    if has_section:
        ending.append("end")
    parts = [f"import {public_import}", *context, "", declaration_with_hole, *ending]
    return "\n".join(parts).strip() + "\n"


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
