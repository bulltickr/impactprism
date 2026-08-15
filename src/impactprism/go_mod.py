from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

__all__ = (
    "GoRequire",
    "GoReplace",
    "GoModuleEntry",
    "GoWork",
    "VendorInfo",
    "GoMod",
    "ResolvedImport",
    "GoManifest",
    "parse_go_mod",
    "parse_go_sum",
    "parse_go_work",
    "parse_vendor_modules",
    "parse_go_manifest",
)


@dataclass
class GoRequire:
    module_path: str
    version: str
    indirect: bool


@dataclass
class GoReplace:
    old_path: str
    old_version: Optional[str]
    new_path: Optional[str]
    new_version: Optional[str]
    local_dir: Optional[str]


@dataclass
class GoModuleEntry:
    module_path: str
    version: Optional[str]
    direct: bool
    source: str
    replaced_by: Optional[GoReplace]


@dataclass
class GoWork:
    go_version: Optional[str]
    use_dirs: list
    requires: list
    replaces: list


@dataclass
class VendorInfo:
    modules: list
    go_version: Optional[str]


@dataclass
class GoMod:
    module_path: Optional[str]
    go_version: Optional[str]
    requires: list
    replaces: list


@dataclass
class ResolvedImport:
    module_path: str
    version: Optional[str]
    kind: str
    root_dir: Optional[Path]
    source: str
    direct: bool


@dataclass
class GoManifest:
    repo_dir: Path
    main_module: Optional[str]
    go_version: Optional[str]
    is_vendored: bool
    modules: list
    requires: list
    replaces: list
    sums: dict
    versions: dict

    def resolve_import_path(self, import_path: str) -> Optional[ResolvedImport]:
        matches = [
            entry
            for entry in self.modules
            if import_path == entry.module_path or import_path.startswith(entry.module_path + "/")
        ]
        if not matches:
            return None
        entry = max(matches, key=lambda item: len(item.module_path))
        replacement = entry.replaced_by
        if replacement is not None and replacement.local_dir is not None:
            root_dir = Path(replacement.local_dir).resolve()
            if not _is_within(root_dir, self.repo_dir.resolve()):
                return None
            return ResolvedImport(
                module_path=entry.module_path,
                version=None,
                kind="local",
                root_dir=root_dir,
                source=entry.source,
                direct=entry.direct,
            )
        if replacement is not None and replacement.new_path is not None:
            if entry.source == "vendor":
                root_dir = (self.repo_dir / "vendor" / replacement.new_path).resolve()
                if not _is_within(root_dir, self.repo_dir.resolve()):
                    return None
            else:
                root_dir = None
            return ResolvedImport(
                module_path=replacement.new_path,
                version=replacement.new_version,
                kind="vendor" if entry.source == "vendor" else "module",
                root_dir=root_dir,
                source=entry.source,
                direct=entry.direct,
            )
        if entry.source == "vendor":
            root_dir = (self.repo_dir / "vendor" / entry.module_path).resolve()
            if not _is_within(root_dir, self.repo_dir.resolve()):
                return None
            return ResolvedImport(
                module_path=entry.module_path,
                version=entry.version,
                kind="vendor",
                root_dir=root_dir,
                source=entry.source,
                direct=entry.direct,
            )
        return ResolvedImport(
            module_path=entry.module_path,
            version=entry.version,
            kind="module",
            root_dir=None,
            source=entry.source,
            direct=entry.direct,
        )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _strip_comment(line: str) -> tuple[str, str]:
    marker = line.find("//")
    if marker < 0:
        return line.rstrip(), ""
    return line[:marker].rstrip(), line[marker + 2 :].strip()


def _parse_replace(text: str, base_dir: Path) -> Optional[GoReplace]:
    if "=>" not in text:
        return None
    old_text, new_text = (part.strip() for part in text.split("=>", 1))
    old_tokens = old_text.split()
    new_tokens = new_text.split()
    if not old_tokens or not new_tokens or len(old_tokens) > 2 or len(new_tokens) > 2:
        return None
    old_path = old_tokens[0]
    old_version = old_tokens[1] if len(old_tokens) == 2 else None
    new_path = new_tokens[0]
    if len(new_tokens) == 1 and (new_path.startswith(".") or os.path.isabs(new_path)):
        local_dir = str((base_dir / new_path).resolve()) if not os.path.isabs(new_path) else str(Path(new_path).resolve())
        return GoReplace(old_path, old_version, None, None, local_dir)
    if len(new_tokens) != 2:
        return None
    return GoReplace(old_path, old_version, new_path, new_tokens[1], None)


def _parse_directives(path: Path, kind: str) -> tuple[Optional[str], Optional[str], list, list, list]:
    module_path: Optional[str] = None
    go_version: Optional[str] = None
    requires = []
    replaces = []
    use_dirs = []
    block: Optional[str] = None
    skip_block = False
    manifest_root = Path(path.parent).resolve()
    with path.open("r", encoding="utf-8") as manifest_file:
        for raw_line in manifest_file:
            line, comment = _strip_comment(raw_line.strip())
            stripped = line.strip()
            if block is not None:
                if stripped == ")":
                    block = None
                    skip_block = False
                    continue
                if skip_block or not stripped:
                    continue
                if block == "require":
                    tokens = stripped.split()
                    if len(tokens) >= 2:
                        requires.append(GoRequire(tokens[0], tokens[1], "indirect" in comment))
                elif block == "replace":
                    replacement = _parse_replace(stripped, path.parent)
                    if replacement is not None:
                        replaces.append(replacement)
                elif block == "use":
                    resolved_use_dir = (path.parent / stripped).resolve()
                    if _is_within(resolved_use_dir, manifest_root):
                        use_dirs.append(resolved_use_dir)
                continue
            if not stripped:
                continue
            tokens = stripped.split()
            directive = tokens[0]
            if directive in ("exclude", "retract"):
                if "(" in stripped and not stripped.endswith(")"):
                    block = directive
                    skip_block = True
                continue
            if directive == "module" and len(tokens) >= 2:
                module_path = tokens[1]
                continue
            if directive == "go" and len(tokens) >= 2:
                go_version = tokens[1]
                continue
            if directive == "toolchain":
                continue
            if directive in ("require", "replace", "use"):
                remainder = stripped[len(directive) :].strip()
                if remainder == "(":
                    block = directive
                    skip_block = False
                    continue
                if directive == "require":
                    if len(tokens) >= 3:
                        requires.append(GoRequire(tokens[1], tokens[2], "indirect" in comment))
                elif directive == "replace":
                    replacement = _parse_replace(stripped[len(directive) :].strip(), path.parent)
                    if replacement is not None:
                        replaces.append(replacement)
                elif directive == "use" and len(tokens) >= 2:
                    resolved_use_dir = (path.parent / tokens[1]).resolve()
                    if _is_within(resolved_use_dir, manifest_root):
                        use_dirs.append(resolved_use_dir)
    return module_path, go_version, requires, replaces, use_dirs


def parse_go_mod(path) -> GoMod:
    """Parse a Go module definition file."""
    manifest_path = Path(path)
    module_path, go_version, requires, replaces, _ = _parse_directives(manifest_path, "mod")
    return GoMod(module_path, go_version, requires, replaces)


def parse_go_sum(path) -> dict:
    """Parse Go checksums into module and checksum-type mappings."""
    sums = {}
    with Path(path).open("r", encoding="utf-8") as sum_file:
        for raw_line in sum_file:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            tokens = stripped.split()
            if len(tokens) < 3:
                continue
            module_path, version_token = tokens[:2]
            if version_token.endswith("/go.mod"):
                version = version_token[: -len("/go.mod")]
                hash_type = "go.mod"
            else:
                version = version_token
                hash_type = None
            entry = sums.setdefault(module_path + "@" + version, {})
            for checksum in tokens[2:]:
                checksum_type = hash_type or checksum.split(":", 1)[0]
                entry[checksum_type] = checksum
    return sums


def parse_go_work(path) -> GoWork:
    """Parse a Go workspace definition file."""
    manifest_path = Path(path)
    _, go_version, requires, replaces, use_dirs = _parse_directives(manifest_path, "work")
    return GoWork(go_version, use_dirs, requires, replaces)


def parse_vendor_modules(path) -> VendorInfo:
    """Parse vendor module metadata from vendor/modules.txt."""
    manifest_path = Path(path)
    modules = []
    go_version: Optional[str] = None
    current: Optional[GoModuleEntry] = None
    with manifest_path.open("r", encoding="utf-8") as vendor_file:
        for raw_line in vendor_file:
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("##"):
                marker = stripped[2:].strip()
                explicit = marker.startswith("explicit")
                if current is not None and explicit:
                    current.direct = True
                if explicit:
                    match = re.search(r"\bgo\s+([^\s;]+)", marker)
                    if match:
                        go_version = match.group(1)
                continue
            if not stripped.startswith("#"):
                continue
            header = stripped[1:].strip()
            if "=>" in header:
                old_text, new_text = (part.strip() for part in header.split("=>", 1))
                old_tokens = old_text.split()
                new_tokens = new_text.split()
                if not old_tokens:
                    current = None
                    continue
                old_path = old_tokens[0]
                old_version = old_tokens[1] if len(old_tokens) > 1 else None
                if len(new_tokens) == 1 and (new_tokens[0].startswith(".") or os.path.isabs(new_tokens[0])):
                    root = Path(manifest_path.parent.parent).resolve()
                    local_dir = (manifest_path.parent.parent / new_tokens[0]).resolve()
                    if _is_within(local_dir, root):
                        replacement = GoReplace(old_path, old_version, None, None, str(local_dir))
                    else:
                        replacement = None
                elif len(new_tokens) >= 2:
                    replacement = GoReplace(old_path, old_version, new_tokens[0], new_tokens[1], None)
                else:
                    replacement = None
                current = GoModuleEntry(old_path, old_version, False, "vendor", replacement)
                modules.append(current)
                continue
            tokens = header.split()
            if len(tokens) >= 1:
                current = GoModuleEntry(
                    tokens[0],
                    tokens[1] if len(tokens) > 1 else None,
                    False,
                    "vendor",
                    None,
                )
                modules.append(current)
    return VendorInfo(modules, go_version)


def _replacement_for(module_path: str, version: Optional[str], replaces: Iterable[GoReplace]) -> Optional[GoReplace]:
    exact = None
    wildcard = None
    for replacement in replaces:
        if replacement.old_path != module_path:
            continue
        if replacement.old_version is not None and replacement.old_version == version:
            exact = replacement
        elif replacement.old_version is None:
            wildcard = replacement
    return exact or wildcard


def _effective_replaces(go_mod_replaces: Iterable[GoReplace], work_replaces: Iterable[GoReplace]) -> list:
    replacements = list(go_mod_replaces)
    for replacement in work_replaces:
        replacements = [
            existing
            for existing in replacements
            if existing.old_path != replacement.old_path
            or (
                replacement.old_version is not None
                and existing.old_version != replacement.old_version
            )
        ]
        replacements.append(replacement)
    return replacements


def _add_entry(entries: dict, entry: GoModuleEntry) -> None:
    existing = entries.get(entry.module_path)
    if existing is None:
        entries[entry.module_path] = entry
        return
    if entry.source == "vendor":
        entries[entry.module_path] = entry
        return
    if entry.source == "go.work":
        existing.direct = entry.direct
        existing.source = entry.source
        if entry.version is not None:
            existing.version = entry.version
        if entry.replaced_by is not None:
            existing.replaced_by = entry.replaced_by
        return
    if existing.source not in ("vendor", "go.work") and entry.direct:
        existing.direct = True


def parse_go_manifest(repo_dir) -> GoManifest:
    """Parse Go module, workspace, checksum, and vendor metadata for a repository."""
    repository = Path(repo_dir).resolve()
    go_mod_path = repository / "go.mod"
    if not go_mod_path.is_file():
        raise FileNotFoundError(go_mod_path)
    main_go_mod = parse_go_mod(go_mod_path)
    work_path = repository / "go.work"
    work = parse_go_work(work_path) if work_path.is_file() else None
    sum_path = repository / "go.sum"
    sums = parse_go_sum(sum_path) if sum_path.is_file() else {}
    vendor_path = repository / "vendor" / "modules.txt"
    vendor = parse_vendor_modules(vendor_path) if vendor_path.is_file() else None

    all_requires = list(main_go_mod.requires)
    module_replaces = list(main_go_mod.replaces)
    entries = {}
    if main_go_mod.module_path is not None:
        _add_entry(entries, GoModuleEntry(main_go_mod.module_path, None, True, "go.mod", None))
    for requirement in main_go_mod.requires:
        _add_entry(
            entries,
            GoModuleEntry(
                requirement.module_path,
                requirement.version,
                not requirement.indirect,
                "go.mod",
                None,
            ),
        )

    if work is not None:
        all_requires.extend(work.requires)
        for requirement in work.requires:
            _add_entry(
                entries,
                GoModuleEntry(
                    requirement.module_path,
                    requirement.version,
                    not requirement.indirect,
                    "go.work",
                    None,
                ),
            )
        for use_dir in work.use_dirs:
            if not _is_within(use_dir, repository):
                continue
            use_mod_path = use_dir / "go.mod"
            if not use_mod_path.is_file():
                continue
            use_mod = parse_go_mod(use_mod_path)
            if use_mod.module_path is not None:
                _add_entry(
                    entries,
                    GoModuleEntry(use_mod.module_path, None, True, "go.work", None),
                )
            all_requires.extend(use_mod.requires)
            module_replaces.extend(use_mod.replaces)
            for requirement in use_mod.requires:
                _add_entry(
                    entries,
                    GoModuleEntry(
                        requirement.module_path,
                        requirement.version,
                        not requirement.indirect,
                        "go.mod",
                        None,
                    ),
                )

    effective_replaces = _effective_replaces(
        module_replaces,
        work.replaces if work is not None else [],
    )
    effective_replaces = [
        replacement
        for replacement in effective_replaces
        if replacement.local_dir is None
        or _is_within(Path(replacement.local_dir).resolve(), repository)
    ]
    for entry in entries.values():
        if entry.replaced_by is None:
            entry.replaced_by = _replacement_for(entry.module_path, entry.version, effective_replaces)
    if vendor is not None:
        for vendor_entry in vendor.modules:
            _add_entry(entries, vendor_entry)
        for entry in vendor.modules:
            if entry.replaced_by is None:
                entry.replaced_by = _replacement_for(entry.module_path, entry.version, effective_replaces)

    modules = list(entries.values())
    versions = {}
    for entry in modules:
        replacement = entry.replaced_by
        if replacement is not None and replacement.local_dir is not None:
            versions[entry.module_path] = replacement.local_dir
        elif replacement is not None and replacement.new_path is not None:
            versions[entry.module_path] = replacement.new_version
        else:
            versions[entry.module_path] = entry.version
    return GoManifest(
        repository,
        main_go_mod.module_path,
        main_go_mod.go_version or (work.go_version if work is not None else None),
        vendor is not None,
        modules,
        all_requires,
        effective_replaces,
        sums,
        versions,
    )
