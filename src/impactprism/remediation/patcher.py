"""Deterministic, offline manifest and lockfile patch generation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from impactprism.go_manifest import parse_go_sum

from .models import PatchSpec, PatchTarget, RemediationError

__all__ = ["build_manifest_patch", "apply_manifest_patch", "compute_lockfile_patch"]

_NPM_KINDS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_PLACEHOLDER_VERSION = "1.0.0"
_PLACEHOLDER_GO_VERSION = "v0.0.0"
_PLACEHOLDER_HASH = "h1:0000000000000000000000000000000000000000="
_PLACEHOLDER_YARN_HASH = "sha1-AAAAAAAAAAAAAAAAAAAAAAAAAAA="
_NPM_JSON_LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json")
_NPM_FAMILY_LOCKFILES = _NPM_JSON_LOCKFILES + ("yarn.lock", "pnpm-lock.yaml")


def build_manifest_patch(finding: dict, manifest, *, prefer_kind: str | None = None) -> PatchSpec | None:
    """Build a full-file manifest patch for an undeclared direct dependency."""
    if _finding_type(finding.get("finding_type")) != "UNDECLARED_DIRECT_USE":
        return None

    raw_package = finding.get("package")
    if not isinstance(raw_package, str) or not raw_package:
        return None

    ecosystem = str(finding.get("ecosystem", "")).lower()
    package, version = _split_package(raw_package, ecosystem)
    if not package:
        return None

    if _is_declared(manifest, package):
        return None

    if ecosystem == "npm":
        return _build_npm_patch(finding, manifest, package, version, prefer_kind)
    if ecosystem == "go":
        return _build_go_patch(manifest, package, version)
    return None


def apply_manifest_patch(repo_dir: str | os.PathLike[str], patch: PatchSpec) -> Path:
    """Apply a manifest patch after verifying that its path stays in the repository."""
    repo_path = Path(repo_dir).resolve()
    patch_path = patch.path.resolve()
    try:
        inside_repo = os.path.commonpath((str(repo_path), str(patch_path))) == str(repo_path)
    except ValueError:
        inside_repo = False
    if not inside_repo:
        raise RemediationError(f"Patch path escapes repository: {patch.path}")
    patch_path.write_text(patch.after, encoding="utf-8")
    return patch_path


def compute_lockfile_patch(
    repo_dir: str | os.PathLike[str],
    patch: PatchSpec,
    *,
    ecosystem: str,
    lockfile: str | None = None,
) -> PatchSpec | None:
    """Build a deterministic lockfile patch without invoking a package manager."""
    repo_path = Path(repo_dir)
    normalized_ecosystem = ecosystem.lower()
    if normalized_ecosystem == "npm":
        selected_lockfile = "package-lock.json" if lockfile is None else lockfile
        if selected_lockfile not in _NPM_FAMILY_LOCKFILES:
            return None
        if selected_lockfile in _NPM_JSON_LOCKFILES:
            return _compute_npm_lockfile_patch(repo_path, patch, selected_lockfile)
        if selected_lockfile == "yarn.lock":
            return _compute_yarn_lockfile_patch(repo_path, patch)
        return _compute_pnpm_lockfile_patch(repo_path, patch)
    if normalized_ecosystem == "go":
        if lockfile is not None and lockfile != "go.sum":
            return None
        return _compute_go_sum_patch(repo_path, patch)
    return None


def _build_npm_patch(
    finding: dict, manifest, package: str, version: str, prefer_kind: str | None
) -> PatchSpec | None:
    path = getattr(manifest, "package_path", None)
    if path is None:
        return None
    path = Path(path)
    before = path.read_text(encoding="utf-8")
    package_data = json.loads(before)
    if not isinstance(package_data, dict):
        return None

    prefer = prefer_kind if isinstance(prefer_kind, str) else ""
    if prefer in _NPM_KINDS:
        kind = prefer
    elif _is_test_file(finding.get("file")):
        kind = "devDependencies"
    else:
        kind = "dependencies"

    declared = package_data.get(kind)
    if not isinstance(declared, dict):
        declared = {}
        package_data[kind] = declared
    dependency_version = version or str(finding.get("version", "")) or "*"
    declared[package] = dependency_version
    after = json.dumps(package_data, indent=2, ensure_ascii=False) + "\n"
    return PatchSpec(
        path=path,
        target=PatchTarget.MANIFEST,
        after=after,
        before=before,
        package=package,
        version=dependency_version,
        kind=kind,
    )


def _build_go_patch(manifest, package: str, version: str) -> PatchSpec | None:
    path = getattr(manifest, "go_mod_path", None)
    if path is None:
        return None
    path = Path(path)
    before = path.read_text(encoding="utf-8")
    if not version:
        for entry in parse_go_sum(path.parent):
            if entry.module == package:
                version = entry.version
                break

    requirement = f"{package} {version}".rstrip()
    lines = before.splitlines(keepends=True)
    block_start = next(
        (index for index, line in enumerate(lines) if re.match(r"^\s*require\s*\(\s*$", line)),
        None,
    )
    if block_start is not None:
        closing = next(
            (index for index in range(block_start + 1, len(lines)) if lines[index].strip() == ")"),
            None,
        )
        if closing is not None:
            lines.insert(closing, f"\t{requirement}\n")
            after = "".join(lines)
        else:
            after = _append_text(before, f"\nrequire {requirement}\n")
    else:
        after = _append_text(before, f"\nrequire {requirement}\n")

    return PatchSpec(
        path=path,
        target=PatchTarget.MANIFEST,
        after=after,
        before=before,
        package=package,
        version=version,
        kind="require",
    )


def _compute_npm_lockfile_patch(
    repo_path: Path, patch: PatchSpec, filename: str = "package-lock.json"
) -> PatchSpec | None:
    path = repo_path / filename
    if not path.is_file():
        return None
    before = path.read_text(encoding="utf-8")
    try:
        data = json.loads(before)
        if not isinstance(data, dict):
            return None
        packages = data.get("packages")
        if packages is None:
            packages = {}
            data["packages"] = packages
        if not isinstance(packages, dict):
            return None
        package = patch.package
        key = f"node_modules/{package}"
        entry = packages.get(key)
        if entry is None:
            entry = {}
            packages[key] = entry
        if not isinstance(entry, dict):
            return None
        entry["version"] = patch.version or _PLACEHOLDER_VERSION
        dependencies = data.get("dependencies")
        if isinstance(dependencies, dict):
            dependencies.pop(package, None)
            dependencies.pop(key, None)
        after = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    except (OSError, TypeError, ValueError):
        return None
    return PatchSpec(
        path=path,
        target=PatchTarget.LOCKFILE,
        after=after,
        before=before,
        package=package,
        version=patch.version or _PLACEHOLDER_VERSION,
        kind=patch.kind,
    )


def _compute_yarn_lockfile_patch(repo_path: Path, patch: PatchSpec) -> PatchSpec | None:
    path = repo_path / "yarn.lock"
    try:
        before = path.read_text(encoding="utf-8")
        if not _is_parseable_yarn_lockfile(before):
            return None
        if _yarn_lockfile_contains_package(before, patch.package):
            return None
        version = patch.version or _PLACEHOLDER_VERSION
        descriptor = f'"{patch.package}@{version}":\n'
        addition = (
            descriptor
            + f'  version "{version}"\n'
            + f'  resolved "https://registry.yarnpkg.com/{patch.package}/-/{patch.package}-{version}.tgz"\n'
            + f"  integrity {_PLACEHOLDER_YARN_HASH}\n"
        )
        after = _append_text(before, addition)
    except (OSError, TypeError, UnicodeError, ValueError):
        return None
    return PatchSpec(
        path=path,
        target=PatchTarget.LOCKFILE,
        after=after,
        before=before,
        package=patch.package,
        version=version,
        kind=patch.kind,
    )


def _compute_pnpm_lockfile_patch(repo_path: Path, patch: PatchSpec) -> PatchSpec | None:
    path = repo_path / "pnpm-lock.yaml"
    try:
        before = path.read_text(encoding="utf-8")
        lines = before.splitlines(keepends=True)
        sections = _parse_simple_pnpm_sections(lines)
        if sections is None:
            return None

        packages_index = sections.get("packages")
        if packages_index is not None:
            next_section = min(
                (index for name, index in sections.items() if index > packages_index),
                default=len(lines),
            )
            package_pattern = re.compile(
                rf"""^\s+['\"]?/?{re.escape(patch.package)}@[^:\s]+['\"]?:\s*$"""
            )
            if any(package_pattern.match(line.rstrip("\r\n")) for line in lines[packages_index + 1 : next_section]):
                return None

            version = patch.version or _PLACEHOLDER_VERSION
            addition = (
                f"  {patch.package}@{version}:\n"
                f"    resolution: {{integrity: {_PLACEHOLDER_HASH}}}\n"
                f"    version: {version}\n"
            )
            prefix = "".join(lines[:next_section])
            suffix = "".join(lines[next_section:])
            if prefix and not prefix.endswith(("\n", "\r")):
                prefix += "\n"
            after = prefix + addition + suffix
        else:
            version = patch.version or _PLACEHOLDER_VERSION
            addition = (
                f"packages:\n"
                f"  {patch.package}@{version}:\n"
                f"    resolution: {{integrity: {_PLACEHOLDER_HASH}}}\n"
                f"    version: {version}\n"
            )
            after = _append_text(before, addition)
    except (OSError, TypeError, UnicodeError, ValueError):
        return None
    return PatchSpec(
        path=path,
        target=PatchTarget.LOCKFILE,
        after=after,
        before=before,
        package=patch.package,
        version=version,
        kind=patch.kind,
    )


def _is_parseable_yarn_lockfile(text: str) -> bool:
    """Recognize the small, line-oriented subset needed for a safe append."""
    saw_yarn_header = False
    saw_entry = False
    current_entry = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if "yarn lockfile" in stripped.lower():
                saw_yarn_header = True
            continue
        if not line[0].isspace():
            if not stripped.endswith(":"):
                return False
            header = stripped[:-1].strip()
            if header != "__metadata" and not _yarn_header_descriptors(header):
                return False
            current_entry = True
            saw_entry = True
            continue
        if not current_entry:
            return False
    return saw_yarn_header or saw_entry


def _yarn_header_descriptors(header: str) -> list[tuple[str, str]]:
    descriptors: list[tuple[str, str]] = []
    for key in _split_comma_separated(header):
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1]
        separator = key.find("@", 1) if key.startswith("@") else key.rfind("@")
        if separator <= 0 or separator == len(key) - 1:
            continue
        descriptors.append((key[:separator], key[separator + 1 :]))
    return descriptors


def _split_comma_separated(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    for index, character in enumerate(value):
        if character in "\"'":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif character == "," and quote is None:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _yarn_lockfile_contains_package(text: str, package: str) -> bool:
    for line in text.splitlines():
        if line[:1].isspace() or not line.strip().endswith(":"):
            continue
        if any(name == package for name, _ in _yarn_header_descriptors(line.strip()[:-1])):
            return True
    return False


def _parse_simple_pnpm_sections(lines: list[str]) -> dict[str, int] | None:
    sections: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[0].isspace():
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):(.*)$", stripped)
        if match is None:
            return None
        section_name, section_value = match.groups()
        if section_name in {"packages", "importers"} and not section_value.strip():
            sections.setdefault(section_name, index)
    if "packages" not in sections and "importers" not in sections:
        return None
    return sections


def _compute_go_sum_patch(repo_path: Path, patch: PatchSpec) -> PatchSpec | None:
    path = repo_path / "go.sum"
    if not path.is_file():
        return None
    try:
        before = path.read_text(encoding="utf-8")
        version = patch.version or _PLACEHOLDER_GO_VERSION
        exists = any(
            len(parts := line.split()) >= 2 and parts[0] == patch.package and parts[1] == version
            for line in before.splitlines()
        )
        after = before if exists else _append_text(before, f"{patch.package} {version} {_PLACEHOLDER_HASH}\n")
    except (OSError, TypeError, ValueError):
        return None
    return PatchSpec(
        path=path,
        target=PatchTarget.GO_SUM,
        after=after,
        before=before,
        package=patch.package,
        version=version,
        kind=patch.kind,
    )


def _is_declared(manifest, package: str) -> bool:
    by_name = getattr(manifest, "by_name", None)
    if callable(by_name) and by_name(package) is not None:
        return True
    dependency = getattr(manifest, "dependency", None)
    if callable(dependency) and dependency(package) is not None:
        return True
    dependency_names = getattr(manifest, "dependency_names", None)
    return callable(dependency_names) and package in dependency_names()


def _finding_type(value) -> str:
    if hasattr(value, "name"):
        return str(value.name)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _split_package(value: str, ecosystem: str) -> tuple[str, str]:
    if ecosystem == "npm":
        if value.startswith("@"):
            separator = value.find("@", 1)
        else:
            separator = value.rfind("@")
        if separator > 0:
            return value[:separator], value[separator + 1 :]
        return value, ""
    if ecosystem == "go":
        separator = value.rfind("@")
        if separator > 0:
            return value[:separator], value[separator + 1 :]
    return value, ""


def _is_test_file(file_path) -> bool:
    if not isinstance(file_path, str) or not file_path:
        return False
    normalized = file_path.replace("\\", "/")
    segments = [segment.lower() for segment in normalized.split("/") if segment]
    if any(segment in {"test", "tests", "__tests__", "spec"} for segment in segments[:-1]):
        return True
    filename = segments[-1] if segments else ""
    return ".test." in filename or ".spec." in filename


def _append_text(before: str, addition: str) -> str:
    if not before:
        return addition.lstrip("\n")
    separator = "" if before.endswith("\n") else "\n"
    return before + separator + addition.lstrip("\n")
