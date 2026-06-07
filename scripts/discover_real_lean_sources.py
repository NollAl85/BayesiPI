from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_ROOTS = (
    ".",
    "..",
    "/private/tmp",
    "/tmp",
    "~/Code",
    "~/code",
    "~/Documents",
)

ENV_ROOTS = (
    "MATHLIB_ROOT",
    "MATHLIB_PROJECT_ROOT",
    "REAL_LEAN_SOURCE_ROOTS",
    "SORRYDB_SOURCE_ROOTS",
    "HTPI_ROOT",
)

SORRY_RE = re.compile(r"(?<![A-Za-z0-9_])sorry(?![A-Za-z0-9_])")
DECL_RE = re.compile(r"^\s*(?:@\[[^\]]+\]\s*)*(?:private\s+|protected\s+)?(?:theorem|lemma)\s+")
PRUNE_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".lake",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover local Lean/Lake sources without network access.")
    parser.add_argument("--roots", nargs="+", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("logs/source_discovery.json"))
    parser.add_argument("--lake-timeout-seconds", type=int, default=20)
    parser.add_argument("--max-project-files", type=int, default=5000)
    args = parser.parse_args()

    roots = args.roots if args.roots is not None else default_roots()
    sources = discover_sources(
        roots,
        check_lake=True,
        lake_timeout_seconds=args.lake_timeout_seconds,
        max_project_files=args.max_project_files,
    )
    write_discovery(args.out, sources)
    print(f"sources={len(sources)}")
    print(f"out={args.out}")


def default_roots() -> list[Path]:
    roots = [Path(root).expanduser() for root in DEFAULT_ROOTS]
    for env_name in ENV_ROOTS:
        raw_value = os.environ.get(env_name)
        if not raw_value:
            continue
        for value in _split_env_paths(raw_value):
            roots.append(Path(value).expanduser())
    return _unique_paths(roots)


def discover_sources(
    roots: list[Path] | tuple[Path, ...],
    *,
    check_lake: bool = True,
    lake_timeout_seconds: int = 20,
    max_project_files: int = 5000,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_project_roots: set[Path] = set()
    seen_mathlib_roots: set[Path] = set()
    for root in _unique_paths([Path(root).expanduser() for root in roots]):
        if not root.exists():
            continue
        if root.is_file():
            root = root.parent
        for current in _walk_dirs(root):
            resolved = _resolve(current)
            if _is_lake_project(current):
                if resolved in seen_project_roots:
                    continue
                seen_project_roots.add(resolved)
                record = _lake_project_record(
                    current,
                    check_lake=check_lake,
                    lake_timeout_seconds=lake_timeout_seconds,
                    max_project_files=max_project_files,
                )
                records.append(record)
                mathlib_root = record.get("mathlib_root")
                if mathlib_root:
                    seen_mathlib_roots.add(_resolve(Path(mathlib_root)))
                continue
            mathlib_dir = _mathlib_dir_at(current)
            if mathlib_dir is None:
                continue
            resolved_mathlib = _resolve(mathlib_dir)
            if resolved_mathlib in seen_mathlib_roots:
                continue
            seen_mathlib_roots.add(resolved_mathlib)
            records.append(
                _mathlib_record(
                    project_root=current,
                    mathlib_root=mathlib_dir,
                    check_lake=check_lake,
                    lake_timeout_seconds=lake_timeout_seconds,
                    max_project_files=max_project_files,
                )
            )
    records.sort(key=lambda row: (str(row["kind"]), str(row["project_root"] or ""), str(row["mathlib_root"] or "")))
    return records


def write_discovery(path: Path, sources: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _walk_dirs(root: Path):
    try:
        if root.is_dir():
            yield root
    except OSError:
        return
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in PRUNE_DIRS and not name.startswith(".elan")]
        yield current_path


def _lake_project_record(
    project_root: Path,
    *,
    check_lake: bool,
    lake_timeout_seconds: int,
    max_project_files: int,
) -> dict[str, Any]:
    mathlib_root = _mathlib_dir_at(project_root) or project_root / ".lake" / "packages" / "mathlib" / "Mathlib"
    if not mathlib_root.is_dir():
        mathlib_root = None
    stats = _lean_stats(project_root, max_files=max_project_files)
    kind = "lake_project"
    if mathlib_root is not None and _looks_like_mathlib(mathlib_root):
        kind = "mathlib"
    elif stats["sorry_count"] > 0:
        kind = "sorry_project"
    return {
        "source_id": _source_id(kind, project_root),
        "kind": kind,
        "project_root": str(project_root),
        "mathlib_root": str(mathlib_root) if mathlib_root else None,
        "lean_files": stats["lean_files"],
        "sorry_count": stats["sorry_count"],
        "theorem_lemma_count": stats["theorem_lemma_count"],
        "lean_toolchain": _lean_toolchain(project_root),
        "can_run_lake_env_lean": _can_run_lake_env_lean(project_root, check_lake, lake_timeout_seconds),
    }


def _mathlib_record(
    *,
    project_root: Path,
    mathlib_root: Path,
    check_lake: bool,
    lake_timeout_seconds: int,
    max_project_files: int,
) -> dict[str, Any]:
    scan_root = project_root if _is_lake_project(project_root) else mathlib_root
    stats = _lean_stats(scan_root, max_files=max_project_files)
    return {
        "source_id": _source_id("mathlib", project_root),
        "kind": "mathlib",
        "project_root": str(project_root),
        "mathlib_root": str(mathlib_root),
        "lean_files": stats["lean_files"],
        "sorry_count": stats["sorry_count"],
        "theorem_lemma_count": stats["theorem_lemma_count"],
        "lean_toolchain": _lean_toolchain(project_root),
        "can_run_lake_env_lean": _can_run_lake_env_lean(project_root, check_lake, lake_timeout_seconds),
    }


def _lean_stats(root: Path, *, max_files: int) -> dict[str, Any]:
    lean_files: list[str] = []
    sorry_count = 0
    theorem_lemma_count = 0
    scanned = 0
    try:
        iterator = root.rglob("*.lean")
    except OSError:
        iterator = iter(())
    for path in iterator:
        if scanned >= max_files:
            break
        if any(part in PRUNE_DIRS for part in path.parts):
            continue
        scanned += 1
        lean_files.append(str(path))
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        sorry_count += len(SORRY_RE.findall(text))
        theorem_lemma_count += sum(1 for line in text.splitlines() if DECL_RE.match(line))
    return {
        "lean_files": sorted(lean_files),
        "sorry_count": sorry_count,
        "theorem_lemma_count": theorem_lemma_count,
    }


def _can_run_lake_env_lean(project_root: Path, check_lake: bool, timeout_seconds: int) -> bool:
    if not check_lake or not _is_lake_project(project_root):
        return False
    with tempfile.TemporaryDirectory(prefix="real_lean_discovery_") as tmp_dir:
        lean_file = Path(tmp_dir) / "DiscoverySmoke.lean"
        lean_file.write_text("example : True := by\n  trivial\n", encoding="utf-8")
        try:
            completed = subprocess.run(
                ["lake", "env", "lean", str(lean_file)],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
    return completed.returncode == 0


def _mathlib_dir_at(path: Path) -> Path | None:
    if path.name == "Mathlib" and _looks_like_mathlib(path):
        return path
    child = path / "Mathlib"
    if child.is_dir() and _looks_like_mathlib(child):
        return child
    lake_child = path / ".lake" / "packages" / "mathlib" / "Mathlib"
    if lake_child.is_dir() and _looks_like_mathlib(lake_child):
        return lake_child
    return None


def _looks_like_mathlib(path: Path) -> bool:
    return path.is_dir() and (
        (path / "Data").is_dir()
        or (path / "Algebra").is_dir()
        or (path / "Topology").is_dir()
        or any(path.glob("*.lean"))
    )


def _is_lake_project(path: Path) -> bool:
    return (path / "lakefile.lean").is_file() or (path / "lakefile.toml").is_file()


def _lean_toolchain(project_root: Path) -> str | None:
    path = project_root / "lean-toolchain"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _source_id(kind: str, path: Path) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", path.name.strip() or "root").strip("_").lower()
    digest = hashlib.sha1(str(_resolve(path)).encode("utf-8")).hexdigest()[:8]
    return f"{kind}_{slug}_{digest}"


def _split_env_paths(raw_value: str) -> list[str]:
    values: list[str] = []
    for chunk in raw_value.replace(",", os.pathsep).split(os.pathsep):
        value = chunk.strip()
        if value:
            values.append(value)
    return values


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = _resolve(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


if __name__ == "__main__":
    main()
