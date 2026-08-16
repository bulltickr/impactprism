"""stdlib-only Python dependency manifest and lockfile parsing."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from . import budgets
from .manifest import Dependency, Lockfile, LockfileParseError, Manifest

PYTHON_MANIFEST_NAMES = ("pyproject.toml", "Pipfile", "requirements.txt")
PYTHON_LOCKFILE_NAMES = ("poetry.lock", "uv.lock", "Pipfile.lock", "requirements.txt")

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
_EXACT_RE = re.compile(r"(?:===|==)\s*([A-Za-z0-9][A-Za-z0-9+!._-]*)")
_DEV_GROUPS = {"dev", "development", "test", "tests", "testing"}

__all__ = [
    "PYTHON_MANIFEST_NAMES", "PYTHON_LOCKFILE_NAMES", "canonical_name",
    "is_python_repo", "parse_python_manifest", "parse_python_manifests",
    "parse_python_lockfile",
]


def canonical_name(name: str) -> str:
    """Return the PEP 503 comparison form used for imports and lockfiles."""
    return re.sub(r"[-_.]+", "-", str(name).strip().lower())


def is_python_repo(repo_dir) -> bool:
    repo = Path(repo_dir)
    return any((repo / name).is_file() for name in PYTHON_MANIFEST_NAMES)


def _read_text(path: Path, *, json_file: bool = False) -> str:
    limit = budgets.MAX_JSON_BYTES if json_file else budgets.MAX_FILE_BYTES
    if json_file:
        budgets.json_bytes_guard(path, limit)
    return budgets.read_text_limited(path, limit)


def _parse_requirement(value: object) -> tuple[str, str, str] | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.startswith(("#", "-", "--", "git+", "http://", "https://")):
        return None
    text = text.split(";", 1)[0].strip()
    match = _NAME_RE.match(text)
    if match is None:
        return None
    name = match.group(0)
    rest = text[match.end() :].strip()
    # Extras are part of a requirement, not part of the distribution name.
    if rest.startswith("["):
        closing = rest.find("]")
        if closing >= 0:
            rest = rest[closing + 1 :].strip()
    exact = _EXACT_RE.search(rest)
    locked = exact.group(1) if exact else None
    return name, rest or "*", locked


def _dependency(name, version, kind, *, locked_version=None, dev=None):
    return Dependency(
        name=str(name),
        version=str(version or "*"),
        kind=kind,
        dev=(kind == "devDependencies") if dev is None else bool(dev),
        locked_version=locked_version,
    )


def _lock_versions(lockfile: Lockfile | None) -> dict[str, str]:
    if lockfile is None:
        return {}
    return {canonical_name(name): version for name, version in lockfile.resolved_versions.items()}


def _with_locks(dependencies, lockfile):
    locked = _lock_versions(lockfile)
    result = []
    for dependency in dependencies:
        result.append(
            _dependency(
                dependency.name,
                dependency.version,
                dependency.kind,
                locked_version=locked.get(canonical_name(dependency.name)),
                dev=dependency.dev,
            )
        )
    return result


def _poetry_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("version", "*")
    return "*"


def _project_dependencies(project: dict) -> list[Dependency]:
    dependencies = []
    for raw in project.get("dependencies", []) or []:
        parsed = _parse_requirement(raw)
        if parsed:
            name, version, locked = parsed
            dependencies.append(_dependency(name, version, "dependencies", locked_version=locked))
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group, values in optional.items():
            kind = "devDependencies" if canonical_name(group) in _DEV_GROUPS else "optionalDependencies"
            if not isinstance(values, list):
                continue
            for raw in values:
                parsed = _parse_requirement(raw)
                if parsed:
                    name, version, locked = parsed
                    dependencies.append(_dependency(name, version, kind, locked_version=locked))
    return dependencies


def _poetry_dependencies(tool_poetry: dict) -> list[Dependency]:
    dependencies = []
    main = tool_poetry.get("dependencies", {})
    if isinstance(main, dict):
        for name, value in main.items():
            if canonical_name(name) == "python":
                continue
            dependencies.append(_dependency(name, _poetry_value(value), "dependencies"))
    for group_name, group in (tool_poetry.get("group", {}) or {}).items():
        if not isinstance(group, dict) or not isinstance(group.get("dependencies"), dict):
            continue
        kind = "devDependencies" if canonical_name(group_name) in _DEV_GROUPS else "optionalDependencies"
        for name, value in group["dependencies"].items():
            dependencies.append(_dependency(name, _poetry_value(value), kind))
    dev = tool_poetry.get("dev-dependencies", {})
    if isinstance(dev, dict):
        for name, value in dev.items():
            dependencies.append(_dependency(name, _poetry_value(value), "devDependencies"))
    return dependencies


def _parse_pyproject(path: Path, lockfile: Lockfile | None) -> Manifest:
    text = _read_text(path)
    data = tomllib.loads(text)
    project = data.get("project", {})
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    dependencies = _project_dependencies(project) if isinstance(project, dict) else []
    if isinstance(poetry, dict):
        dependencies.extend(_poetry_dependencies(poetry))
    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for group, values in dependency_groups.items():
            if not isinstance(values, list):
                continue
            kind = "devDependencies" if canonical_name(group) in _DEV_GROUPS else "optionalDependencies"
            for raw in values:
                if isinstance(raw, dict):
                    raw = raw.get("include-group")
                parsed = _parse_requirement(raw)
                if parsed:
                    name, version, locked = parsed
                    dependencies.append(_dependency(name, version, kind, locked_version=locked))
    return Manifest(
        name=str((project if isinstance(project, dict) else {}).get("name")
                 or (poetry if isinstance(poetry, dict) else {}).get("name") or ""),
        version=str((project if isinstance(project, dict) else {}).get("version")
                   or (poetry if isinstance(poetry, dict) else {}).get("version") or ""),
        package_path=path,
        dependencies=_with_locks(_dedupe(dependencies), lockfile),
    )


def _parse_pipfile(path: Path, lockfile: Lockfile | None) -> Manifest:
    data = tomllib.loads(_read_text(path))
    dependencies = []
    for section, kind in (("packages", "dependencies"), ("dev-packages", "devDependencies")):
        values = data.get(section, {})
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            dependencies.append(_dependency(name, _poetry_value(value), kind))
    return Manifest(name="", version="", package_path=path, dependencies=_with_locks(dependencies, lockfile))


def _parse_requirements(path: Path, lockfile: Lockfile | None) -> Manifest:
    dependencies = []
    kind = "devDependencies" if "dev" in path.name.lower() else "dependencies"
    for raw in _read_text(path).splitlines():
        parsed = _parse_requirement(raw)
        if parsed:
            name, version, locked = parsed
            dependencies.append(_dependency(name, version, kind, locked_version=locked))
    return Manifest(name="", version="", package_path=path, dependencies=_with_locks(_dedupe(dependencies), lockfile))


def _dedupe(dependencies):
    result = []
    seen = set()
    for dependency in dependencies:
        key = (canonical_name(dependency.name), dependency.kind)
        if key in seen:
            continue
        seen.add(key)
        result.append(dependency)
    return result


def parse_python_lockfile(repo_dir) -> Lockfile | None:
    repo = Path(repo_dir)
    for filename in PYTHON_LOCKFILE_NAMES:
        path = repo / filename
        if not path.is_file():
            continue
        try:
            if filename == "poetry.lock":
                data = tomllib.loads(_read_text(path))
                packages = data.get("package", [])
                resolved = {
                    str(item["name"]): str(item["version"])
                    for item in packages
                    if isinstance(item, dict) and item.get("name") and item.get("version")
                }
                return Lockfile(kind="poetry", resolved_versions=resolved)
            if filename == "uv.lock":
                data = tomllib.loads(_read_text(path))
                packages = data.get("package", [])
                resolved = {
                    str(item["name"]): str(item["version"])
                    for item in packages
                    if isinstance(item, dict) and item.get("name") and item.get("version")
                }
                return Lockfile(kind="uv", resolved_versions=resolved)
            if filename == "Pipfile.lock":
                data = json.loads(_read_text(path, json_file=True))
                if not isinstance(data, dict):
                    raise ValueError("Pipfile.lock root must be an object")
                resolved = {}
                for section in ("default", "develop"):
                    values = data.get(section, {})
                    if not isinstance(values, dict):
                        continue
                    for name, value in values.items():
                        if isinstance(value, str):
                            match = _EXACT_RE.search(value)
                            if match:
                                resolved.setdefault(str(name), match.group(1))
                        elif isinstance(value, dict) and value.get("version"):
                            match = _EXACT_RE.search(str(value["version"]))
                            if match:
                                resolved.setdefault(str(name), match.group(1))
                return Lockfile(kind="pipenv", resolved_versions=resolved)
            resolved = {}
            for raw in _read_text(path).splitlines():
                parsed = _parse_requirement(raw)
                if parsed and parsed[2]:
                    resolved[parsed[0]] = parsed[2]
            return Lockfile(kind="requirements", resolved_versions=resolved)
        except (OSError, ValueError, tomllib.TOMLDecodeError, budgets.ScannerBudgetError, RecursionError) as exc:
            raise LockfileParseError(lockfile_path=path, cause=exc) from exc
    return None


def parse_python_manifest(repo_dir) -> Manifest:
    repo = Path(repo_dir)
    lockfile = parse_python_lockfile(repo)
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        return _parse_pyproject(pyproject, lockfile)
    pipfile = repo / "Pipfile"
    if pipfile.is_file():
        return _parse_pipfile(pipfile, lockfile)
    requirements = repo / "requirements.txt"
    if requirements.is_file():
        return _parse_requirements(requirements, lockfile)
    raise ValueError(f"no supported Python manifest found in {repo}")


def parse_python_manifests(repo_dir) -> list[Manifest]:
    return [parse_python_manifest(repo_dir)]
