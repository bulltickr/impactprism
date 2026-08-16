from __future__ import annotations

from pathlib import Path

from ..go_manifest import parse_go_manifest, parse_go_sum
from ..manifest import parse_lockfile, parse_manifest
from ..python_manifest import canonical_name, is_python_repo
from .models import DependencyGraph

__all__ = ["dependency_map", "render_dependency_graph", "diff_graph"]

_NPM_KINDS = ("dependencies", "devDependencies")


def _resolve_ecosystem(repo_dir: str, ecosystem: str) -> str:
    if ecosystem != "auto":
        return ecosystem
    repo = Path(repo_dir)
    if (repo / "package.json").is_file():
        return "npm"
    if (repo / "go.mod").is_file():
        return "go"
    if is_python_repo(repo):
        return "python"
    raise ValueError("unsupported or missing ecosystem")


def dependency_map(repo_dir: str, *, ecosystem: str = "auto") -> dict:
    resolved = _resolve_ecosystem(repo_dir, ecosystem)
    mapping = {}
    if resolved == "npm":
        manifest = parse_manifest(repo_dir)
        lockfile = parse_lockfile(repo_dir)
        locked = lockfile.resolved_versions if lockfile is not None else {}
        if not isinstance(locked, dict):
            locked = {}
        for dependency in manifest.dependencies:
            if dependency.kind not in _NPM_KINDS:
                continue
            version = dependency.locked_version or dependency.version
            mapping[dependency.name] = version
        for name, version in sorted(locked.items()):
            if name not in mapping:
                mapping[name] = version
        return mapping
    if resolved == "go":
        manifest = parse_go_manifest(repo_dir)
        for dependency in manifest.dependencies:
            mapping[dependency.module] = dependency.version
        for entry in parse_go_sum(repo_dir):
            mapping.setdefault(entry.module, entry.version)
        return mapping
    if resolved == "python":
        manifest = parse_manifest(repo_dir)
        lockfile = parse_lockfile(repo_dir)
        locked = lockfile.resolved_versions if lockfile is not None else {}
        locked = {canonical_name(name): version for name, version in (locked or {}).items()}
        for dependency in manifest.dependencies:
            mapping[canonical_name(dependency.name)] = dependency.locked_version or locked.get(
                canonical_name(dependency.name), dependency.version
            )
        for name, version in sorted(locked.items()):
            mapping.setdefault(name, version)
        return mapping
    raise ValueError(f"unsupported ecosystem: {resolved!r}")


def render_dependency_graph(repo_dir: str, *, ecosystem: str = "auto") -> str:
    resolved = _resolve_ecosystem(repo_dir, ecosystem)
    mapping = dependency_map(repo_dir, ecosystem=resolved)
    if resolved == "npm":
        manifest = parse_manifest(repo_dir)
        dev_names = {
            dependency.name
            for dependency in manifest.dependencies
            if dependency.kind == "devDependencies"
        }
        lines = []
        for name in sorted(mapping):
            version = mapping[name]
            if name in dev_names:
                lines.append(f"  (dev) {name}@{version}")
            else:
                lines.append(f"{name}@{version}")
        return "\n".join(lines)
    return "\n".join(f"{name}@{version}" for name, version in sorted(mapping.items()))


def diff_graph(before: dict, after: dict) -> DependencyGraph:
    added = sorted(name for name in after if name not in before)
    removed = sorted(name for name in before if name not in after)
    text_before = "\n".join(f"{name}@{version}" for name, version in sorted(before.items()))
    text_after = "\n".join(f"{name}@{version}" for name, version in sorted(after.items()))
    return DependencyGraph(
        before=before,
        after=after,
        text_before=text_before,
        text_after=text_after,
        added=added,
        removed=removed,
    )
