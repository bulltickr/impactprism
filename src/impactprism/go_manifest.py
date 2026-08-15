"""Go module manifest parsing: go.mod, go.work, go.sum, and vendor/modules.txt."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "GoDependency",
    "ReplaceRule",
    "GoManifest",
    "GoWork",
    "VendorModule",
    "GoSumEntry",
    "parse_go_manifest",
    "parse_go_mod_text",
    "parse_go_work",
    "parse_go_sum",
    "detect_vendor",
    "parse_vendor_modules",
]

_BLOCK_DIRECTIVES = ("require", "replace", "exclude", "retract")
_WORK_BLOCK_DIRECTIVES = ("use", "replace")


@dataclass
class GoDependency:
    module: str
    version: str
    indirect: bool
    replaced: bool
    replacement: str | None
    replacement_local: bool

    @property
    def direct(self) -> bool:
        return not self.indirect


@dataclass
class ReplaceRule:
    old: str
    old_version: str | None
    new: str
    new_version: str | None
    local: bool


@dataclass
class GoManifest:
    module_path: str
    go_version: str
    toolchain: str | None
    dependencies: list[GoDependency]
    replaces: list[ReplaceRule]
    go_mod_path: Path

    def dependency(self, name: str) -> GoDependency | None:
        return next((dependency for dependency in self.dependencies if dependency.module == name), None)

    def dependency_names(self) -> set[str]:
        return {dependency.module for dependency in self.dependencies}

    def replacement_for(self, module: str) -> str | None:
        for rule in self.replaces:
            if rule.old == module:
                return _replacement_target(rule)
        return None


@dataclass
class GoWork:
    go_version: str
    toolchain: str | None
    uses: list[str]
    replaces: list[ReplaceRule]
    go_work_path: Path


@dataclass
class VendorModule:
    module: str
    version: str
    explicit: bool
    packages: list[str]


@dataclass
class GoSumEntry:
    module: str
    version: str
    is_mod_hash: bool
    hash: str


def parse_go_manifest(repo_dir: str | os.PathLike[str]) -> GoManifest:
    repo_path = Path(repo_dir)
    go_mod_path = repo_path / "go.mod"
    with go_mod_path.open("r", encoding="utf-8") as go_mod:
        text = go_mod.read()
    return parse_go_mod_text(text, go_mod_path)


def parse_go_mod_text(text: str, go_mod_path: Path) -> GoManifest:
    module_path = ""
    go_version = ""
    toolchain = None
    dependencies: list[GoDependency] = []
    replaces: list[ReplaceRule] = []
    block = None
    for code, comment in _lines_with_comments(text):
        stripped = code.strip()
        if not stripped:
            continue
        if block is not None:
            if stripped == ")":
                block = None
                continue
            if stripped.endswith(")"):
                _parse_mod_entry(block, stripped[:-1].strip(), "indirect" in comment, dependencies, replaces)
                block = None
                continue
            _parse_mod_entry(block, stripped, "indirect" in comment, dependencies, replaces)
            continue
        parts = stripped.split()
        keyword = parts[0]
        if keyword == "module":
            module_path = stripped[len("module"):].strip()
        elif keyword == "go":
            go_version = stripped[len("go"):].strip()
        elif keyword == "toolchain":
            toolchain = stripped[len("toolchain"):].strip()
        elif keyword in _BLOCK_DIRECTIVES:
            if stripped.endswith("("):
                block = keyword
                continue
            _parse_mod_entry(keyword, stripped[len(keyword):].strip(), "indirect" in comment, dependencies, replaces)
    for dependency in dependencies:
        rule = _replacement_rule(replaces, dependency.module, dependency.version)
        if rule is not None:
            dependency.replaced = True
            dependency.replacement = _replacement_target(rule)
            dependency.replacement_local = rule.local
    return GoManifest(
        module_path=module_path,
        go_version=go_version,
        toolchain=toolchain,
        dependencies=dependencies,
        replaces=replaces,
        go_mod_path=go_mod_path,
    )


def _parse_mod_entry(
    directive: str,
    body: str,
    indirect: bool,
    dependencies: list[GoDependency],
    replaces: list[ReplaceRule],
) -> None:
    if directive == "require":
        tokens = body.split()
        for index in range(0, len(tokens) - 1, 2):
            dependencies.append(
                GoDependency(
                    module=tokens[index],
                    version=tokens[index + 1],
                    indirect=indirect,
                    replaced=False,
                    replacement=None,
                    replacement_local=False,
                )
            )
    elif directive == "replace":
        rule = _parse_replace_tokens(body.split())
        if rule is not None:
            replaces.append(rule)


def parse_go_work(repo_dir: str | os.PathLike[str]) -> GoWork | None:
    repo_path = Path(repo_dir)
    go_work_path = repo_path / "go.work"
    if not go_work_path.is_file():
        return None
    with go_work_path.open("r", encoding="utf-8") as go_work:
        text = go_work.read()
    go_version = ""
    toolchain = None
    uses: list[str] = []
    replaces: list[ReplaceRule] = []
    block = None
    for code, _ in _lines_with_comments(text):
        stripped = code.strip()
        if not stripped:
            continue
        if block is not None:
            if stripped == ")":
                block = None
                continue
            if stripped.endswith(")"):
                _parse_work_entry(block, stripped[:-1].strip(), uses, replaces)
                block = None
                continue
            _parse_work_entry(block, stripped, uses, replaces)
            continue
        parts = stripped.split()
        keyword = parts[0]
        if keyword == "go":
            go_version = stripped[len("go"):].strip()
        elif keyword == "toolchain":
            toolchain = stripped[len("toolchain"):].strip()
        elif keyword in _WORK_BLOCK_DIRECTIVES:
            if stripped.endswith("("):
                block = keyword
                continue
            _parse_work_entry(keyword, stripped[len(keyword):].strip(), uses, replaces)
    return GoWork(
        go_version=go_version,
        toolchain=toolchain,
        uses=uses,
        replaces=replaces,
        go_work_path=go_work_path,
    )


def _parse_work_entry(directive: str, body: str, uses: list[str], replaces: list[ReplaceRule]) -> None:
    if directive == "use":
        uses.extend(body.split())
    elif directive == "replace":
        rule = _parse_replace_tokens(body.split())
        if rule is not None:
            replaces.append(rule)


def parse_go_sum(repo_dir: str | os.PathLike[str]) -> list[GoSumEntry]:
    repo_path = Path(repo_dir)
    go_sum_path = repo_path / "go.sum"
    if not go_sum_path.is_file():
        return []
    entries: list[GoSumEntry] = []
    with go_sum_path.open("r", encoding="utf-8") as go_sum:
        for line in go_sum:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            parts = stripped.split()
            if len(parts) != 3:
                continue
            module, version, hash_value = parts
            is_mod_hash = version.endswith("/go.mod")
            if is_mod_hash:
                version = version[: -len("/go.mod")]
            entries.append(GoSumEntry(module=module, version=version, is_mod_hash=is_mod_hash, hash=hash_value))
    return entries


def detect_vendor(repo_dir: str | os.PathLike[str]) -> bool:
    return (Path(repo_dir) / "vendor" / "modules.txt").is_file()


def parse_vendor_modules(repo_dir: str | os.PathLike[str]) -> list[VendorModule] | None:
    modules_file = Path(repo_dir) / "vendor" / "modules.txt"
    if not modules_file.is_file():
        return None
    modules: list[VendorModule] = []
    current = None
    with modules_file.open("r", encoding="utf-8") as modules_file_handle:
        for line in modules_file_handle:
            if line.startswith("# "):
                parts = line[2:].strip().split()
                if len(parts) >= 2:
                    current = VendorModule(module=parts[0], version=parts[1], explicit=False, packages=[])
                    modules.append(current)
            elif line.startswith("##"):
                if current is not None and "explicit" in line:
                    current.explicit = True
            elif line[:1].isspace():
                package = line.strip()
                if current is not None and package:
                    current.packages.append(package)
    return modules


def _lines_with_comments(text: str) -> list[tuple[str, str]]:
    lines = []
    for line in text.splitlines():
        code, _, comment = line.partition("//")
        lines.append((code, comment))
    return lines


def _parse_replace_tokens(tokens: list[str]) -> ReplaceRule | None:
    if "=>" not in tokens:
        return None
    separator = tokens.index("=>")
    left = tokens[:separator]
    right = tokens[separator + 1 :]
    return ReplaceRule(
        old=left[0],
        old_version=left[1] if len(left) > 1 else None,
        new=right[0],
        new_version=right[1] if len(right) > 1 else None,
        local=len(right) == 1,
    )


def _replacement_rule(replaces: list[ReplaceRule], module: str, version: str) -> ReplaceRule | None:
    for rule in replaces:
        if rule.old == module and (rule.old_version is None or rule.old_version == version):
            return rule
    return None


def _replacement_target(rule: ReplaceRule) -> str:
    if rule.local or rule.new_version is None:
        return rule.new
    return f"{rule.new} {rule.new_version}"
