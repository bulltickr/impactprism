from __future__ import annotations

import json
import os
import re

from . import budgets
from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = [
    "Dependency",
    "Manifest",
    "Lockfile",
    "LockfileParseError",
    "parse_manifest",
    "parse_lockfile",
    "parse_python_manifest",
    "parse_python_lockfile",
    "parse_python_manifests",
    "discover_workspaces",
    "parse_manifests",
    "manifest_for_file",
]


class LockfileParseError(Exception):
    """Raised when a present lockfile cannot be parsed."""

    def __init__(self, *, lockfile_path, cause):
        self.lockfile_path = lockfile_path
        self.cause = cause
        super().__init__(f"could not parse lockfile {lockfile_path}: {cause}")


@dataclass
class Dependency:
    name: str
    version: str
    kind: str
    dev: bool
    locked_version: str | None


@dataclass
class Manifest:
    name: str
    version: str
    package_path: Path | None
    dependencies: list[Dependency]

    def by_name(self, name: str) -> Dependency | None:
        return next((dependency for dependency in self.dependencies if dependency.name == name), None)

    def dependency_names(self) -> set[str]:
        return {dependency.name for dependency in self.dependencies}


@dataclass
class Lockfile:
    kind: str
    resolved_versions: dict[str, str]


_DEPENDENCY_KINDS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_LOCKFILE_NAMES = (
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
    ("yarn.lock", "yarn"),
    ("pnpm-lock.yaml", "pnpm"),
)
_YARN_VERSION = re.compile(r'^\s+version\s*:?\s*["\']?([^"\'\s]+)["\']?\s*$')
_PNPM_VERSION = re.compile(r'^\s+version:\s*["\']?([^"\'\s]+)["\']?\s*$')
_SKIPPED_PREFIXES = ("link:", "workspace:", "file:", "portal:")
_YARN_DESCRIPTOR = re.compile(r"^(.+?)@([a-z0-9]+):")


def parse_manifest(repo_dir: str | os.PathLike[str]) -> Manifest:
    repo_path = Path(repo_dir)
    package_path = repo_path / "package.json"
    if not package_path.is_file() and _is_python_repo(repo_path):
        from .python_manifest import parse_python_manifest

        return parse_python_manifest(repo_path)
    package_data = _read_package_json(package_path)
    try:
        lockfile = parse_lockfile(repo_path)
    except LockfileParseError:
        lockfile = None
    return _manifest_from_package(package_data, package_path, lockfile)


def _read_package_json(package_path: Path) -> dict:
    try:
        budgets.json_bytes_guard(package_path, budgets.MAX_JSON_BYTES)
        text = budgets.read_text_limited(package_path, budgets.MAX_JSON_BYTES)
        budgets.check_json_depth(text, budgets.MAX_JSON_DEPTH)
        package_data = json.loads(text)
    except budgets.ScannerBudgetError:
        raise
    if not isinstance(package_data, dict):
        raise ValueError("package.json root must be an object")
    return package_data


def _manifest_from_package(package_data, package_path: Path, lockfile) -> Manifest:
    resolved_versions = lockfile.resolved_versions if lockfile is not None else {}
    dependencies = []
    for kind in _DEPENDENCY_KINDS:
        declared = package_data.get(kind, {})
        if not isinstance(declared, dict):
            continue
        for name, version in declared.items():
            dependency_name = str(name)
            dependency_version = str(version)
            dependencies.append(
                Dependency(
                    name=dependency_name,
                    version=dependency_version,
                    kind=kind,
                    dev=kind == "devDependencies",
                    locked_version=resolved_versions.get(dependency_name),
                )
            )

    return Manifest(
        name=str(package_data.get("name", "")),
        version=str(package_data.get("version", "")),
        package_path=package_path,
        dependencies=dependencies,
    )


def parse_lockfile(repo_dir: str | os.PathLike[str]) -> Lockfile | None:
    repo_path = Path(repo_dir)
    for filename, kind in _LOCKFILE_NAMES:
        lockfile_path = repo_path / filename
        if not lockfile_path.is_file():
            continue
        if kind == "npm":
            return Lockfile(kind=kind, resolved_versions=_parse_npm_lockfile(lockfile_path))
        if kind == "yarn":
            return Lockfile(kind=kind, resolved_versions=_parse_yarn_lockfile(lockfile_path))
        return Lockfile(kind=kind, resolved_versions=_parse_pnpm_lockfile(lockfile_path))
    if _is_python_repo(repo_path):
        from .python_manifest import parse_python_lockfile

        return parse_python_lockfile(repo_path)
    return None


def discover_workspaces(repo_dir: str | os.PathLike[str]) -> list[Path]:
    repo_path = Path(repo_dir)
    patterns = _workspace_patterns(repo_path)
    matches: list[Path] = []
    match_count = 0
    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        excluded = pattern.startswith("!")
        normalized = pattern[1:] if excluded else pattern
        normalized = normalized.strip("/")
        if not normalized:
            continue
        try:
            candidates = (
                repo_path.rglob(normalized)
                if "**" in normalized
                else repo_path.glob(normalized)
            )
        except (OSError, ValueError):
            continue
        for candidate in candidates:
            match_count += 1
            if match_count > budgets.MAX_WORKSPACE_MATCHES:
                raise budgets.ScannerBudgetError("workspace_matches", budgets.MAX_WORKSPACE_MATCHES)
            try:
                candidate.resolve().relative_to(repo_path.resolve())
            except ValueError:
                continue
            if not candidate.is_dir():
                continue
            if not (candidate / "package.json").is_file():
                continue
            if excluded:
                matches = [match for match in matches if match.resolve() != candidate.resolve()]
            else:
                matches.append(candidate)
    unique: dict[str, Path] = {}
    for match in sorted(matches, key=lambda path: str(path)):
        unique[str(match.resolve())] = match
    return list(unique.values())


def _workspace_patterns(repo_path: Path) -> list[object]:
    """Read package-manager workspace globs without running package-manager code."""
    patterns: list[object] = []
    try:
        package_data = _read_package_json(repo_path / "package.json")
    except (OSError, ValueError):
        package_data = {}
    workspaces = package_data.get("workspaces")
    if isinstance(workspaces, list):
        patterns.extend(workspaces)
    elif isinstance(workspaces, dict):
        packages = workspaces.get("packages")
        if isinstance(packages, list):
            patterns.extend(packages)

    workspace_file = repo_path / "pnpm-workspace.yaml"
    if not workspace_file.is_file():
        return patterns
    try:
        budgets.json_bytes_guard(workspace_file, budgets.MAX_FILE_BYTES)
        raw = budgets.read_text_limited(workspace_file, budgets.MAX_FILE_BYTES)
        config = yaml.safe_load(raw)
    except budgets.ScannerBudgetError:
        raise
    except (OSError, RecursionError, yaml.YAMLError, TypeError):
        return patterns
    if isinstance(config, dict) and isinstance(config.get("packages"), list):
        patterns.extend(config["packages"])
    return patterns


def parse_manifests(repo_dir: str | os.PathLike[str]) -> list[Manifest]:
    repo_path = Path(repo_dir)
    if not (repo_path / "package.json").is_file() and _is_python_repo(repo_path):
        from .python_manifest import parse_python_manifests

        return parse_python_manifests(repo_path)
    manifests = [parse_manifest(repo_path)]
    for workspace in discover_workspaces(repo_path):
        manifests.append(_parse_workspace_manifest(repo_path, workspace))
    return manifests


def manifest_for_file(repo_dir: str | os.PathLike[str], file_path) -> Manifest:
    manifests = parse_manifests(repo_dir)
    return _manifest_for_path(manifests, file_path)


def _parse_workspace_manifest(repo_root: Path, workspace: Path) -> Manifest:
    package_path = workspace / "package.json"
    package_data = _read_package_json(package_path)
    try:
        lockfile = _effective_lockfile_for_dir(repo_root, workspace)
    except LockfileParseError:
        lockfile = None
    return _manifest_from_package(package_data, package_path, lockfile)


def _is_python_repo(repo_path: Path) -> bool:
    return any(
        (repo_path / name).is_file()
        for name in ("pyproject.toml", "Pipfile", "requirements.txt")
    )


def parse_python_manifest(repo_dir):
    from .python_manifest import parse_python_manifest as parser

    return parser(repo_dir)


def parse_python_lockfile(repo_dir):
    from .python_manifest import parse_python_lockfile as parser

    return parser(repo_dir)


def parse_python_manifests(repo_dir):
    from .python_manifest import parse_python_manifests as parser

    return parser(repo_dir)


def _manifest_for_path(manifests: list[Manifest], file_path) -> Manifest:
    target = Path(file_path)
    best = manifests[0]
    best_parts = -1
    for manifest in manifests:
        package_dir = manifest.package_path.parent
        try:
            target.relative_to(package_dir)
        except ValueError:
            continue
        if len(package_dir.parts) > best_parts:
            best = manifest
            best_parts = len(package_dir.parts)
    return best


def _lockfile_for_manifest(repo_root: Path, manifest: Manifest) -> Lockfile | None:
    if manifest.package_path is None:
        return None
    return _effective_lockfile_for_dir(repo_root, manifest.package_path.parent)


def _effective_lockfile_for_dir(repo_root: Path, manifest_dir: Path) -> Lockfile | None:
    lockfile_path = _effective_lockfile_path(repo_root, manifest_dir)
    if lockfile_path is None:
        return None
    return parse_lockfile(lockfile_path.parent)


def _effective_lockfile_path(repo_root: Path, manifest_dir: Path) -> Path | None:
    root = Path(repo_root).resolve()
    start = Path(manifest_dir).resolve()
    for filename, _kind in _LOCKFILE_NAMES:
        candidate = start / filename
        if candidate.is_file():
            return candidate
    if start == root:
        return None
    current = start.parent
    walk_steps = 0
    while current is not None:
        walk_steps += 1
        if walk_steps > budgets.MAX_WALK_DEPTH:
            return None
        for filename, _kind in _LOCKFILE_NAMES:
            candidate = current / filename
            if candidate.is_file():
                return candidate
        if current == root:
            break
        current = current.parent
    return None


def _parse_npm_lockfile(path: Path) -> dict[str, str]:
    try:
        budgets.json_bytes_guard(path, budgets.MAX_JSON_BYTES)
        text = budgets.read_text_limited(path, budgets.MAX_JSON_BYTES)
        budgets.check_json_depth(text, budgets.MAX_JSON_DEPTH)
        data = json.loads(text)
        if not isinstance(data, dict):
            raise LockfileParseError(
                lockfile_path=path,
                cause=ValueError("npm lockfile root must be an object"),
            )

        resolved: dict[str, str] = {}
        packages = data.get("packages")
        if isinstance(packages, dict):
            for key, package in packages.items():
                if not isinstance(key, str) or not key.startswith("node_modules/"):
                    continue
                if not isinstance(package, dict):
                    continue
                version = package.get("version")
                if not isinstance(version, str):
                    continue
                name = key.rsplit("node_modules/", 1)[-1]
                if name:
                    resolved.setdefault(name, version)

        dependencies = data.get("dependencies")
        if isinstance(dependencies, dict):
            _collect_npm_dependencies(dependencies, resolved)
        return resolved
    except (OSError, json.JSONDecodeError, budgets.ScannerBudgetError, RecursionError) as exc:
        raise LockfileParseError(lockfile_path=path, cause=exc) from exc


def _collect_npm_dependencies(
    dependencies: dict[object, object], resolved: dict[str, str], _depth: int = 0
) -> None:
    if _depth > budgets.MAX_NESTING_DEPTH:
        raise budgets.ScannerBudgetError("nesting", budgets.MAX_NESTING_DEPTH)
    for name, package in dependencies.items():
        if not isinstance(name, str) or not isinstance(package, dict):
            continue
        version = package.get("version")
        if isinstance(version, str):
            resolved.setdefault(name, version)
        nested = package.get("dependencies")
        if isinstance(nested, dict):
            _collect_npm_dependencies(nested, resolved, _depth + 1)


def _parse_yarn_lockfile(path: Path) -> dict[str, str]:
    try:
        return _parse_yarn_lockfile_body(path)
    except LockfileParseError:
        raise
    except Exception as exc:
        raise LockfileParseError(lockfile_path=path, cause=exc) from exc


def _parse_yarn_lockfile_body(path: Path) -> dict[str, str]:
    resolved: dict[str, str] = {}
    current_names: list[str] = []
    with path.open("r", encoding="utf-8") as lockfile:
        for line in lockfile:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not line[0].isspace() and stripped.endswith(":"):
                header = stripped[:-1].strip()
                current_names = []
                for key in _split_yarn_keys(header):
                    parsed = _parse_yarn_key(key)
                    if parsed is not None:
                        name, selector = parsed
                        if not selector.startswith(_SKIPPED_PREFIXES):
                            current_names.append(name)
                continue
            match = _YARN_VERSION.match(line)
            if match and current_names:
                version = match.group(1)
                if version.startswith(_SKIPPED_PREFIXES):
                    continue
                for name in current_names:
                    resolved.setdefault(name, version)
                continue
            if line and not line[0].isspace():
                current_names = []
    return resolved


def _split_yarn_keys(header: str) -> list[str]:
    keys = []
    start = 0
    quote: str | None = None
    for index, character in enumerate(header):
        if character in "\"'":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif character == "," and quote is None:
            keys.append(header[start:index].strip())
            start = index + 1
    keys.append(header[start:].strip())
    return [key for key in keys if key]


def _parse_yarn_key(key: str) -> tuple[str, str] | None:
    key = key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1]
    key = key.split("#", 1)[0]
    match = _YARN_DESCRIPTOR.match(key)
    if match is not None:
        name = match.group(1)
        selector = match.group(2)
    else:
        separator = key.rfind("@")
        if separator <= 0 or separator == len(key) - 1:
            return None
        name = key[:separator]
        selector = key[separator + 1 :]
    if not name or not selector or name.startswith(_SKIPPED_PREFIXES):
        return None
    return name, selector


def _parse_pnpm_lockfile(path: Path) -> dict[str, str]:
    try:
        return _parse_pnpm_lockfile_body(path)
    except LockfileParseError:
        raise
    except Exception as exc:
        raise LockfileParseError(lockfile_path=path, cause=exc) from exc


def _parse_pnpm_lockfile_body(path: Path) -> dict[str, str]:
    resolved: dict[str, str] = {}
    active_section: str | None = None
    pending_bare: str | None = None
    with path.open("r", encoding="utf-8") as lockfile:
        for line in lockfile:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indentation = len(line) - len(line.lstrip())
            if indentation == 0 and stripped in ("packages:", "snapshots:"):
                active_section = stripped[:-1]
                pending_bare = None
                continue
            if indentation == 0 and active_section is not None:
                active_section = None
                pending_bare = None
                continue
            if active_section is None:
                continue

            if stripped.endswith(":"):
                candidate = stripped[:-1].strip()
                parsed = _parse_pnpm_key(candidate)
                if parsed is not None:
                    name, version = parsed
                    pending_bare = name if version is None else None
                    if version is not None:
                        resolved.setdefault(name, version)
                    continue
            if pending_bare is not None:
                match = _PNPM_VERSION.match(line)
                if match:
                    resolved.setdefault(pending_bare, match.group(1))
                    pending_bare = None
    return resolved


def _parse_pnpm_key(key: str) -> tuple[str, str | None] | None:
    key = key.strip()
    quoted = len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'"
    if quoted:
        key = key[1:-1]
    had_leading_slash = key.startswith("/")
    if had_leading_slash:
        key = key[1:]
    if not key or key.startswith(_SKIPPED_PREFIXES):
        return None

    separator = key.rfind("@")
    if separator > 0 and separator < len(key) - 1:
        name = key[:separator]
        version = key[separator + 1 :]
        if version.startswith(_SKIPPED_PREFIXES) or not name:
            return None
        return name, version
    if had_leading_slash and "/" not in key.strip("/"):
        return key, None
    return None
