"""Go package-import extraction and module-usage classification.

Depends on ``impactprism.go_mod`` for module resolution. A hand-written
comment/string-aware scanner extracts ``import`` declarations from ``*.go``
sources, then the package import graph is aggregated to the module level and
cross-referenced against the module manifest (declared/direct vs observed use).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import budgets
from . import go_mod

__all__ = [
    "GoImport",
    "GoSourceImports",
    "PackageEdge",
    "ModuleUsage",
    "GoImportGraph",
    "parse_go_source",
    "scan_go_imports",
    "build_import_graph",
]

SKIPPED_DIRECTORIES = {"vendor", ".git"}


@dataclass
class GoImport:
    """A single Go import specifier."""

    kind: str
    name: str | None
    module_path: str


@dataclass
class GoSourceImports:
    """The imports found in a single Go source file."""

    path: Path
    imports: list


@dataclass
class PackageEdge:
    """A package-level import edge between two Go packages."""

    package_dir: Path
    import_path: str
    resolved: go_mod.ResolvedImport | None


@dataclass
class ModuleUsage:
    """Aggregated usage of one resolved Go module."""

    module_path: str
    version: str | None
    direct: bool
    used: bool
    import_count: int
    importing_files: list = field(default_factory=list)
    importing_packages: list = field(default_factory=list)


@dataclass
class GoImportGraph:
    """Combined module manifest and package import graph for a Go repo."""

    manifest: go_mod.GoManifest
    sources: dict
    package_edges: list
    module_usage: dict
    unresolved: list
    stdlib_imports: list

    def directly_used_modules(self) -> list:
        """Return modules declared direct that are actually imported."""
        return _sorted_usages(usage for usage in self.module_usage.values() if usage.direct and usage.used)

    def indirectly_used_modules(self) -> list:
        """Return modules declared indirect that are actually imported."""
        return _sorted_usages(usage for usage in self.module_usage.values() if not usage.direct and usage.used)

    def declared_unused_modules(self) -> list:
        """Return modules declared direct that are never imported."""
        return _sorted_usages(usage for usage in self.module_usage.values() if usage.direct and not usage.used)


def _sorted_usages(usages) -> list:
    return sorted(usages, key=lambda usage: usage.module_path)


def parse_go_source(source: str, path: Path) -> list:
    """Return the list of GoImport records found in one Go source file.

    A hand-written tokenizer skips ``//`` and ``/* */`` comments as well as
    interpreted, raw and rune literals so that only real ``import``
    declarations are parsed. Malformed input never raises; whatever could be
    parsed is returned.
    """
    return _parse_import_declarations(_tokenize(source))


def _tokenize(source: str) -> list:
    tokens = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index)
            index = length if newline == -1 else newline + 1
            continue
        if source.startswith("/*", index):
            close = source.find("*/", index + 2)
            index = length if close == -1 else close + 2
            continue
        if char == '"':
            content = []
            index += 1
            while index < length:
                if source[index] == "\\" and index + 1 < length:
                    content.append(source[index : index + 2])
                    index += 2
                elif source[index] == '"':
                    index += 1
                    break
                else:
                    content.append(source[index])
                    index += 1
            tokens.append(("string", "".join(content)))
            continue
        if char == "`":
            close = source.find("`", index + 1)
            if close == -1:
                tokens.append(("string", source[index + 1 :]))
                index = length
            else:
                tokens.append(("string", source[index + 1 : close]))
                index = close + 1
            continue
        if char == "'":
            index += 1
            while index < length and source[index] != "'":
                if source[index] == "\\" and index + 1 < length:
                    index += 2
                else:
                    index += 1
            index += 1
            continue
        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
            tokens.append(("ident", source[start:index]))
            continue
        if char in "().":
            tokens.append(("punct", char))
            index += 1
            continue
        index += 1
    return tokens


def _parse_import_declarations(tokens: list) -> list:
    imports = []
    index = 0
    length = len(tokens)
    while index < length:
        token_kind, token_value = tokens[index]
        if token_kind == "ident" and token_value == "import":
            index += 1
            if index < length and tokens[index] == ("punct", "("):
                index += 1
                while index < length and tokens[index] != ("punct", ")"):
                    spec, index = _parse_import_spec(tokens, index)
                    if spec is not None:
                        imports.append(spec)
                index += 1
            else:
                spec, index = _parse_import_spec(tokens, index)
                if spec is not None:
                    imports.append(spec)
        else:
            index += 1
    return imports


def _parse_import_spec(tokens: list, index: int):
    if index >= len(tokens):
        return None, index
    token_kind, token_value = tokens[index]
    if token_kind == "string":
        return GoImport("normal", None, token_value), index + 1
    name = None
    kind = "normal"
    if token_kind == "punct" and token_value == ".":
        name = "."
        kind = "dot"
        index += 1
    elif token_kind == "ident" and token_value != "import":
        name = token_value
        kind = "underscore" if name == "_" else "alias"
        index += 1
    else:
        return None, index + 1
    if index < len(tokens) and tokens[index][0] == "string":
        return GoImport(kind, name, tokens[index][1]), index + 1
    return None, index


def scan_go_imports(
    repo_dir,
    *,
    exclude=None,
    max_file_bytes=None,
    max_total_bytes=None,
    max_files=None,
    max_depth=None,
    max_seconds=None,
) -> dict:
    """Walk ``repo_dir`` for ``*.go`` files and map each path to its imports.

    Skips the ``vendor`` tree, ``.git`` and any dot-directory. Files are read
    as UTF-8 with errors ignored.

    Scanning is bounded by resource budgets defaulting to the
    ``impactprism.budgets`` constants: ``max_file_bytes`` caps each file read,
    ``max_total_bytes`` the aggregate bytes of all touched files, ``max_files``
    the number of ``*.go`` files processed, ``max_depth`` the directory depth
    walked, and ``max_seconds`` the wall-clock budget. Exceeding any of them
    raises ``budgets.ScannerBudgetError``.
    """
    result = {}
    repo = Path(repo_dir)
    if not repo.is_dir():
        return result
    exclude = set(exclude or [])
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
                if name == "vendor" or name.startswith(".") or name in exclude:
                    continue
                stack.append((Path(entry.path), depth + 1))
                continue
            if name.startswith(".") or not name.endswith(".go"):
                continue
            path = Path(entry.path)
            try:
                walk.touch_file(path, os.path.getsize(path))
                source = budgets.read_text_limited(path, max_bytes=max_file_bytes)
            except OSError:
                continue
            result[path] = parse_go_source(source, path)
    walk.check()
    return result


def _is_stdlib(import_path: str) -> bool:
    if import_path.startswith("/"):
        return False
    first = import_path.split("/", 1)[0]
    return "." not in first


def _is_main_module_import(manifest, import_path: str) -> bool:
    main_module = getattr(manifest, "main_module", None)
    if not main_module:
        return False
    return import_path == main_module or import_path.startswith(main_module + "/")


def build_import_graph(repo_dir, manifest=None, *, exclude=None) -> GoImportGraph:
    """Build the package import graph and module-usage classification.

    If ``manifest`` is omitted the repo manifest is loaded via
    ``go_mod.parse_go_manifest``. Standard-library imports are collected
    separately; every non-stdlib import is resolved through the manifest.
    """
    repo = Path(repo_dir)
    if manifest is None:
        manifest = go_mod.parse_go_manifest(repo)
    sources = scan_go_imports(repo, exclude=exclude)

    module_usage = {}
    for entry in getattr(manifest, "modules", []):
        if getattr(entry, "replaced_by", None) is None:
            module_usage[entry.module_path] = ModuleUsage(
                module_path=entry.module_path,
                version=entry.version,
                direct=entry.direct,
                used=False,
                import_count=0,
            )

    package_edges = []
    unresolved = []
    stdlib_imports = []
    for path in sorted(sources):
        package_dir = path.parent
        for go_import in sources[path]:
            import_path = go_import.module_path
            if _is_stdlib(import_path):
                stdlib_imports.append(import_path)
                continue
            try:
                resolved = manifest.resolve_import_path(import_path)
            except Exception:
                resolved = None
            if resolved is None and _is_main_module_import(manifest, import_path):
                resolved = go_mod.ResolvedImport(
                    module_path=manifest.main_module,
                    version=None,
                    kind="module",
                    root_dir=Path(repo),
                    source="go.mod",
                    direct=True,
                )
            package_edges.append(PackageEdge(package_dir, import_path, resolved))
            if resolved is None:
                unresolved.append(import_path)
                continue
            usage = module_usage.get(resolved.module_path)
            if usage is None:
                usage = ModuleUsage(
                    module_path=resolved.module_path,
                    version=resolved.version,
                    direct=resolved.direct,
                    used=True,
                    import_count=0,
                )
                module_usage[resolved.module_path] = usage
            usage.used = True
            usage.import_count += 1
            if path not in usage.importing_files:
                usage.importing_files.append(path)
            if package_dir not in usage.importing_packages:
                usage.importing_packages.append(package_dir)

    return GoImportGraph(
        manifest=manifest,
        sources=sources,
        package_edges=package_edges,
        module_usage=module_usage,
        unresolved=unresolved,
        stdlib_imports=stdlib_imports,
    )
