"""Bounded, standard-library-only Python import scanning."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from . import budgets

__all__ = ["ImportRecord", "parse_imports", "parse_python_imports", "scan_imports", "scan_python_imports"]

SOURCE_EXTENSIONS = {".py", ".pyi"}
SKIPPED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "__pycache__",
    "build", "dist", "coverage", ".pytest_cache", "node_modules",
}


@dataclass
class ImportRecord:
    kind: str
    specifier: str
    start: int
    end: int


def _literal_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _offsets(source: str, node) -> tuple[int, int]:
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    lineno = max(1, getattr(node, "lineno", 1))
    start = starts[min(lineno - 1, len(starts) - 1)] + getattr(node, "col_offset", 0)
    end_line = max(lineno, getattr(node, "end_lineno", lineno))
    end = starts[min(end_line - 1, len(starts) - 1)] + getattr(node, "end_col_offset", 0)
    return start, max(start, end)


def parse_imports(source: str) -> list[ImportRecord]:
    """Extract static and literal dynamic imports without executing source."""
    if not isinstance(source, str):
        return []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return []

    records = []
    dynamic_import_names = {"__import__"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "importlib":
            continue
        for alias in node.names:
            if alias.name == "import_module":
                dynamic_import_names.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            start, end = _offsets(source, node)
            for alias in node.names:
                if alias.name:
                    records.append(ImportRecord("static", alias.name, start, end))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            specifier = "." * int(node.level or 0) + module
            if specifier:
                start, end = _offsets(source, node)
                records.append(ImportRecord("static", specifier, start, end))
        elif isinstance(node, ast.Call):
            dynamic = False
            if isinstance(node.func, ast.Name) and node.func.id in dynamic_import_names:
                dynamic = True
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                dynamic = True
            if dynamic and node.args:
                specifier = _literal_string(node.args[0])
                if specifier:
                    start, end = _offsets(source, node)
                    records.append(ImportRecord("dynamic", specifier, start, end))
    records.sort(key=lambda record: (record.start, record.end, record.specifier))
    return records


def scan_imports(
    repo_dir,
    *,
    exclude=None,
    max_file_bytes=None,
    max_total_bytes=None,
    max_files=None,
    max_depth=None,
    max_seconds=None,
) -> dict[Path, list[ImportRecord]]:
    """Walk Python sources under ``repo_dir`` subject to scanner budgets."""
    repo = Path(repo_dir)
    if not repo.is_dir():
        return {}
    if exclude is not None:
        exclude = set(exclude)
    max_file_bytes = budgets.MAX_FILE_BYTES if max_file_bytes is None else max_file_bytes
    max_total_bytes = budgets.MAX_TOTAL_BYTES if max_total_bytes is None else max_total_bytes
    max_files = budgets.MAX_FILE_COUNT if max_files is None else max_files
    max_depth = budgets.MAX_WALK_DEPTH if max_depth is None else max_depth
    max_seconds = budgets.MAX_SCAN_SECONDS if max_seconds is None else max_seconds
    walk = budgets.WalkBudget(
        repo, max_bytes=max_total_bytes, max_files=max_files,
        max_depth=max_depth, max_seconds=max_seconds,
    )
    result = {}
    stack = [(repo, 1)]
    while stack:
        directory, depth = stack.pop()
        walk.dir_depth = depth
        walk.check()
        try:
            entries = sorted(os.scandir(str(directory)), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            name = entry.name
            if is_dir:
                if name in SKIPPED_DIRECTORIES or name.startswith("."):
                    continue
                if exclude is not None and name in exclude:
                    continue
                stack.append((Path(entry.path), depth + 1))
                continue
            if name.startswith(".") or Path(name).suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            path = Path(entry.path)
            try:
                walk.touch_file(path, os.path.getsize(path))
                source = budgets.read_text_limited(path, max_bytes=max_file_bytes)
            except OSError:
                continue
            result[path] = parse_imports(source)
    walk.check()
    return result


scan_python_imports = scan_imports
parse_python_imports = parse_imports
