"""AST-based JavaScript/TypeScript import extraction.

Depends on ``impactprism.js_ast``. Produces import records in source order
without any de-duplication; only string-literal module specifiers are recorded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import budgets, js_ast
from .scope import is_excluded_directory, normalize_excludes

SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
SKIPPED_DIRECTORIES = {"node_modules", "build", "dist", "coverage", "public"}


@dataclass
class ImportRecord:
    kind: str
    specifier: str
    start: int
    end: int


def parse_imports(source: str) -> list:
    """Return the import records found in ``source``, in source order.

    Mappings:
      * ESM ``import``/``export ... from`` declarations -> ``"esm"``
      * ``require('x')`` call expressions             -> ``"cjs"``
      * ``import('x')`` / ``await import('x')``       -> ``"dynamic"``

    Only string-literal specifiers are recorded; non-literal arguments are
    ignored without raising.
    """
    records = []
    try:
        module = js_ast.parse(source)
    except budgets.ScannerBudgetError:
        raise
    except Exception:
        return records
    _collect(module, records)
    records.sort(key=lambda record: (record.start, record.end))
    return records


def _collect(node, records, _depth=0):
    if _depth > budgets.MAX_NESTING_DEPTH:
        raise budgets.ScannerBudgetError("ast_depth", budgets.MAX_NESTING_DEPTH)
    ntype = node.type
    if ntype in ("ImportDeclaration", "ImportExpression"):
        spec = _module_string(node)
        if spec is not None:
            kind = "esm" if ntype == "ImportDeclaration" else "dynamic"
            records.append(ImportRecord(kind, spec, node.start, node.end))
    elif ntype in ("ExportNamedDeclaration", "ExportAllDeclaration"):
        spec = getattr(node, "source", None)
        if spec:
            records.append(ImportRecord("esm", spec, node.start, node.end))
    elif ntype == "CallExpression":
        callee = node.children[0] if node.children else None
        if (
            callee is not None
            and callee.type == "Identifier"
            and getattr(callee, "name", None) == "require"
        ):
            arg = node.children[1] if len(node.children) > 1 else None
            if arg is not None and arg.type == "StringLiteral":
                records.append(ImportRecord("cjs", arg.source, node.start, node.end))
    for child in node.children:
        _collect(child, records, _depth + 1)


def _module_string(node):
    for child in node.children:
        if child.type == "StringLiteral":
            return child.source
    return None


def scan_imports(
    repo_dir,
    *,
    exclude=None,
    max_file_bytes=None,
    max_total_bytes=None,
    max_files=None,
    max_depth=None,
    max_seconds=None,
) -> dict:
    """Walk ``repo_dir`` and return a mapping of source file -> import records.

    Skips ``node_modules``, ``build``, ``dist``, ``coverage``, ``public``, any
    dot-directory and any non-source (or dot-prefixed) file. When ``exclude`` is
    given it must be a set of directory basenames that should also be skipped.
    Files are read as UTF-8 with errors ignored.

    The scan is bounded by resource budgets so an adversarial repository (an
    oversized file, a huge tree, or a deeply nested source file) can neither
    OOM nor hang the process. Each optional keyword argument defaults to the
    matching ``impactprism.budgets`` constant: ``max_file_bytes``,
    ``max_total_bytes``, ``max_files``, ``max_depth`` and ``max_seconds``.
    Exceeding any budget raises ``impactprism.budgets.ScannerBudgetError``; a
    per-file ``OSError`` is silently skipped as before.
    """
    result = {}
    repo = Path(repo_dir)
    if not repo.is_dir():
        return result
    if exclude is not None:
        exclude = normalize_excludes(exclude)
    if max_file_bytes is None:
        max_file_bytes = budgets.MAX_FILE_BYTES
    if max_total_bytes is None:
        max_total_bytes = budgets.MAX_TOTAL_BYTES
    if max_files is None:
        max_files = budgets.MAX_FILE_COUNT
    if max_depth is None:
        max_depth = budgets.MAX_WALK_DEPTH
    if max_seconds is None:
        max_seconds = budgets.MAX_SCAN_SECONDS
    walk = budgets.WalkBudget(
        repo,
        max_bytes=max_total_bytes,
        max_files=max_files,
        max_depth=max_depth,
        max_seconds=max_seconds,
    )
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
                if exclude is not None and is_excluded_directory(repo, Path(entry.path), exclude):
                    continue
                stack.append((Path(entry.path), depth + 1))
                continue
            if name.startswith("."):
                continue
            if Path(name).suffix.lower() not in SOURCE_EXTENSIONS:
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
