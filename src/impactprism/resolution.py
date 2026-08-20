"""Bounded, non-executing JavaScript/TypeScript module resolution helpers.

This module only interprets static JSON/JSONC configuration and package
metadata. It never imports or executes repository code, build configuration,
generators, or package-manager commands.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import budgets


_SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json")
_CONDITION_ORDER = {
    "esm": ("import", "node", "default"),
    "dynamic": ("import", "node", "default"),
    "cjs": ("require", "node", "default"),
}


@dataclass(frozen=True)
class ResolutionDecision:
    """Classification of one module specifier for drift analysis."""

    kind: str
    reason: str = ""


def _strip_jsonc(source: str) -> str:
    """Remove comments and trailing commas without interpreting strings."""

    output: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(source):
        char = source[i]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            i += 1
            continue
        if char == "/" and i + 1 < len(source) and source[i + 1] == "/":
            i += 2
            while i < len(source) and source[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and i + 1 < len(source) and source[i + 1] == "*":
            i += 2
            while i + 1 < len(source) and source[i:i + 2] != "*/":
                i += 1
            i = min(len(source), i + 2)
            continue
        output.append(char)
        i += 1

    cleaned = "".join(output)
    result: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(cleaned):
        char = cleaned[i]
        if not in_string and char == ",":
            j = i + 1
            while j < len(cleaned) and cleaned[j].isspace():
                j += 1
            if j < len(cleaned) and cleaned[j] in "}]":
                i += 1
                continue
        result.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        i += 1
    return "".join(result)


def _read_json(path: Path) -> dict | None:
    try:
        budgets.json_bytes_guard(path, budgets.MAX_JSON_BYTES)
        raw = budgets.read_text_limited(path, budgets.MAX_JSON_BYTES)
        value = json.loads(_strip_jsonc(raw.lstrip("\ufeff")))
    except (OSError, ValueError, TypeError, budgets.ScannerBudgetError):
        return None
    return value if isinstance(value, dict) else None


def _package_name(specifier: str) -> str | None:
    if not specifier or specifier.startswith((".", "/", "#", "node:")):
        return None
    parts = specifier.split("/")
    if specifier.startswith("@"):
        return "/".join(parts[:2]) if len(parts) >= 2 else None
    return parts[0]


def _subpath(package_name: str, specifier: str) -> str:
    if specifier == package_name:
        return "."
    return "./" + specifier[len(package_name):].lstrip("/")


def _replace_star(value: str, match: str | None) -> str:
    return value.replace("*", match or "") if "*" in value else value


def _match_pattern(pattern: str, value: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == value else None
    prefix, suffix = pattern.split("*", 1)
    if not value.startswith(prefix) or not value.endswith(suffix):
        return None
    end = len(value) - len(suffix) if suffix else len(value)
    if end < len(prefix):
        return None
    return value[len(prefix):end]


def _select_condition(value, kind: str):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for candidate in value:
            selected = _select_condition(candidate, kind)
            if selected is not None:
                return selected
        return None
    if not isinstance(value, dict):
        return None
    if any(str(key).startswith(".") for key in value):
        return None
    for condition in _CONDITION_ORDER.get(kind, ("default",)):
        if condition in value:
            selected = _select_condition(value[condition], kind)
            if selected is not None:
                return selected
    return None


def _select_subpath(mapping, key: str, kind: str):
    if isinstance(mapping, (str, list)):
        return _select_condition(mapping, kind) if key == "." else None
    if not isinstance(mapping, dict):
        return None
    if not any(str(item).startswith(".") for item in mapping):
        return _select_condition(mapping, kind) if key == "." else None
    if key in mapping:
        return _select_condition(mapping[key], kind)
    candidates = []
    for pattern, value in mapping.items():
        if not isinstance(pattern, str):
            continue
        match = _match_pattern(pattern, key)
        if match is not None:
            candidates.append((pattern.count("*"), len(pattern), pattern, value, match))
    if not candidates:
        return None
    _stars, _length, _pattern, value, match = max(candidates)
    selected = _select_condition(value, kind)
    return _replace_star(selected, match) if selected is not None else None


def _resolve_candidate(path: Path) -> bool:
    if path.is_file():
        return True
    if path.suffix:
        return False
    has_source_suffix = any(path.with_suffix(suffix).is_file() for suffix in _SOURCE_SUFFIXES)
    has_index = any(
        (path / name).is_file()
        for name in ("index.ts", "index.tsx", "index.js", "index.jsx")
    )
    return has_source_suffix or has_index


def _resolve_local_target(
    base: Path,
    target: str,
    match: str | None = None,
    root: Path | None = None,
) -> bool:
    if not isinstance(target, str) or target.startswith("/"):
        return False
    relative = target[2:] if target.startswith("./") else target
    candidate = (base / _replace_star(relative, match)).resolve()
    if root is not None:
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return False
    return _resolve_candidate(candidate)


class ResolutionContext:
    """Resolve static local aliases and workspace package exports."""

    def __init__(self, repo_dir, manifests=()):
        self.repo = (
            Path(repo_dir).resolve()
            if repo_dir is not None
            else Path(".").resolve()
        )
        self.manifests = tuple(manifests or ())
        self.local_packages = {
            str(manifest.name): Path(manifest.package_path).parent.resolve()
            for manifest in self.manifests
            if getattr(manifest, "name", None) and getattr(manifest, "package_path", None)
        }
        self._json_cache: dict[Path, dict | None] = {}
        self._tsconfig_cache: dict[Path, dict | None] = {}

    def classify(
        self, file_path: Path, specifier: str, kind: str = "esm"
    ) -> ResolutionDecision:
        if not isinstance(specifier, str) or not specifier:
            return ResolutionDecision("external")
        if specifier.startswith("#"):
            return self._package_import(file_path, specifier, kind)
        package = _package_name(specifier)
        if package in self.local_packages:
            return self._workspace_export(package, specifier, kind)
        alias = self._tsconfig_alias(file_path, specifier)
        if alias is not None:
            return alias
        return ResolutionDecision("external")

    def _json(self, path: Path) -> dict | None:
        path = path.resolve()
        if path not in self._json_cache:
            self._json_cache[path] = _read_json(path)
        return self._json_cache[path]

    def _nearest_package(self, file_path: Path) -> tuple[Path, dict] | None:
        current = Path(file_path).resolve().parent
        root = self.repo
        while True:
            candidate = current / "package.json"
            value = self._json(candidate) if candidate.is_file() else None
            if value is not None:
                return current, value
            if current == root or current.parent == current:
                return None
            current = current.parent

    def _package_import(self, file_path: Path, specifier: str, kind: str) -> ResolutionDecision:
        package = self._nearest_package(file_path)
        if package is None:
            return ResolutionDecision(
                "unresolved", "no package.json was found for the package import"
            )
        package_dir, package_json = package
        imports = package_json.get("imports")
        if not isinstance(imports, dict):
            return ResolutionDecision("unresolved", "package.json has no static imports mapping")
        candidates = []
        for pattern, value in imports.items():
            if not isinstance(pattern, str) or not pattern.startswith("#"):
                continue
            match = _match_pattern(pattern, specifier)
            if match is not None:
                candidates.append((pattern == specifier, len(pattern), pattern, value, match))
        if not candidates:
            return ResolutionDecision("unresolved", "package import is not declared in package.json")
        _exact, _length, _pattern, value, match = max(candidates)
        target = _select_condition(value, kind)
        if isinstance(target, str) and target.startswith("./"):
            if _resolve_local_target(package_dir, target, match, root=self.repo):
                return ResolutionDecision("local")
            return ResolutionDecision(
                "unresolved",
                f"package import {specifier!r} targets a missing local path",
            )
        return ResolutionDecision("unresolved", "package import target is not a supported local path")

    def _workspace_export(self, package: str, specifier: str, kind: str) -> ResolutionDecision:
        package_dir = self.local_packages[package]
        package_json = self._json(package_dir / "package.json") or {}
        exports = package_json.get("exports")
        if exports is None:
            return ResolutionDecision("local")
        key = _subpath(package, specifier)
        target = _select_subpath(exports, key, kind)
        if target is None:
            return ResolutionDecision(
                "unresolved",
                f"workspace package {package!r} does not export {key!r}",
            )
        if target.startswith("./") and _resolve_local_target(
            package_dir, target, root=self.repo
        ):
            return ResolutionDecision("local")
        if not target.startswith("./"):
            return ResolutionDecision("local")
        return ResolutionDecision(
            "unresolved", f"workspace export {key!r} targets a missing local path"
        )

    def _tsconfig(self, file_path: Path) -> tuple[Path, dict] | None:
        current = Path(file_path).resolve().parent
        while True:
            candidate = current / "tsconfig.json"
            if candidate.is_file():
                if candidate not in self._tsconfig_cache:
                    self._tsconfig_cache[candidate] = _read_json(candidate)
                value = self._tsconfig_cache[candidate]
                if value is not None:
                    return current, value
            if current == self.repo or current.parent == current:
                return None
            current = current.parent

    def _tsconfig_alias(self, file_path: Path, specifier: str) -> ResolutionDecision | None:
        config = self._tsconfig(file_path)
        if config is None:
            return None
        config_dir, value = config
        options = value.get("compilerOptions")
        if not isinstance(options, dict):
            return None
        paths = options.get("paths")
        if isinstance(paths, dict):
            matches = []
            for pattern, targets in paths.items():
                if not isinstance(pattern, str) or not isinstance(targets, list):
                    continue
                match = _match_pattern(pattern, specifier)
                if match is not None:
                    matches.append(
                        (pattern == specifier, len(pattern), pattern, targets, match)
                    )
            if matches:
                _exact, _length, pattern, targets, match = max(matches)
                base = config_dir / str(options.get("baseUrl", "."))
                for target in targets:
                    if isinstance(target, str) and _resolve_local_target(
                        base, target, match, root=self.repo
                    ):
                        return ResolutionDecision("local")
                return ResolutionDecision(
                    "unresolved",
                    f"tsconfig path alias {pattern!r} has no existing target",
                )
        base_url = options.get("baseUrl")
        if isinstance(base_url, str) and _resolve_candidate((config_dir / base_url / specifier).resolve()):
            return ResolutionDecision("local")
        return None
