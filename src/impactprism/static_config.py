"""Bounded extraction of literal aliases from common bundler configs.

Bundler configuration is executable JavaScript. This module never imports,
evaluates, or invokes it. It tokenizes a small static subset and accepts only
literal alias objects/arrays plus ``path.resolve(__dirname, ...)`` targets.
Everything else is intentionally treated as unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import budgets, js_ast


_CONFIG_NAMES = (
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.cjs",
    "vite.config.ts",
    "vite.config.mts",
    "vite.config.cts",
    "webpack.config.js",
    "webpack.config.mjs",
    "webpack.config.cjs",
    "webpack.config.ts",
    "webpack.config.mts",
    "webpack.config.cts",
)
_UNKNOWN = object()


@dataclass(frozen=True)
class StaticPath:
    """A path expression known to be relative to a config directory."""

    parts: tuple[str, ...]


@dataclass(frozen=True)
class AliasRule:
    find: str
    replacement: str | StaticPath


class _StaticParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0
        self.objects: list[dict] = []

    def _current(self):
        return self.tokens[self.index]

    def _at(self, value: str) -> bool:
        token = self._current()
        return token.type == "punct" and token.value == value

    def _advance(self):
        token = self._current()
        self.index = min(self.index + 1, len(self.tokens) - 1)
        return token

    def parse_all_objects(self):
        while self._current().type != "eof":
            if self._at("{") and self._is_config_object_start():
                self._parse_object()
            elif self._at("{"):
                self._skip_balanced()
            else:
                self._advance()
        return self.objects

    def _is_config_object_start(self):
        index = self.index
        if index == 0:
            return False
        previous = self.tokens[index - 1]
        if previous.type == "name" and previous.value == "default":
            return True
        if (
            previous.type == "punct"
            and previous.value == "("
            and index >= 2
            and self.tokens[index - 2].type == "name"
            and self.tokens[index - 2].value == "defineConfig"
        ):
            return True
        return (
            previous.type == "punct"
            and previous.value == "="
            and index >= 4
            and self.tokens[index - 2].type == "name"
            and self.tokens[index - 2].value == "exports"
            and self.tokens[index - 3].type == "punct"
            and self.tokens[index - 3].value == "."
            and self.tokens[index - 4].type == "name"
            and self.tokens[index - 4].value == "module"
        )

    def _skip_balanced(self):
        depth = 0
        while self._current().type != "eof":
            if self._at("{"):
                depth += 1
            elif self._at("}"):
                depth -= 1
                if depth == 0:
                    self._advance()
                    return
            self._advance()

    def _parse_object(self):
        self._advance()  # {
        value = {}
        self.objects.append(value)
        while self._current().type != "eof" and not self._at("}"):
            if self._at(","):
                self._advance()
                continue
            key = self._parse_key()
            if key is None or not self._at(":"):
                self._skip_member()
                continue
            self._advance()  # :
            value[key] = self._parse_value()
            if self._at(","):
                self._advance()
        if self._at("}"):
            self._advance()
        return value

    def _parse_key(self):
        token = self._current()
        if token.type in ("name", "string", "number"):
            self._advance()
            return str(token.value)
        return None

    def _parse_value(self):
        token = self._current()
        if token.type == "string":
            self._advance()
            return token.value
        if token.type == "punct" and token.value == "{":
            return self._parse_object()
        if token.type == "punct" and token.value == "[":
            return self._parse_array()
        if token.type == "punct" and token.value == "(":
            self._advance()
            value = self._parse_value()
            while self._current().type != "eof" and not self._at(")"):
                self._advance()
            if self._at(")"):
                self._advance()
            return value
        if token.type == "name" and token.value == "__dirname":
            self._advance()
            return self._parse_path_call(())
        if token.type == "name":
            return self._parse_name_value()
        self._advance()
        return _UNKNOWN

    def _parse_name_value(self):
        first = self._advance().value
        if not self._at("."):
            return _UNKNOWN
        self._advance()
        method = self._current()
        if method.type != "name" or method.value not in ("resolve", "join"):
            return _UNKNOWN
        self._advance()
        if not self._at("("):
            return _UNKNOWN
        self._advance()
        args = []
        while self._current().type != "eof" and not self._at(")"):
            if self._at(","):
                self._advance()
                continue
            args.append(self._parse_value())
            if self._at(","):
                self._advance()
        if self._at(")"):
            self._advance()
        if first != "path" or not args or not isinstance(args[0], StaticPath):
            return _UNKNOWN
        if not all(isinstance(arg, str) for arg in args[1:]):
            return _UNKNOWN
        return StaticPath(args[0].parts + tuple(args[1:]))

    def _parse_path_call(self, parts):
        if self._at("."):
            self._advance()
        return StaticPath(parts)

    def _parse_array(self):
        self._advance()  # [
        values = []
        while self._current().type != "eof" and not self._at("]"):
            if self._at(","):
                self._advance()
                continue
            values.append(self._parse_value())
            if self._at(","):
                self._advance()
        if self._at("]"):
            self._advance()
        return values

    def _skip_member(self):
        while self._current().type != "eof" and not self._at(",") and not self._at("}"):
            self._advance()
        if self._at(","):
            self._advance()


def _literal_aliases(source: str) -> list[AliasRule]:
    try:
        tokens = js_ast.Tokenizer(source).tokenize()
        tokens.append(js_ast.Token("eof", "", "", len(source), len(source)))
        objects = _StaticParser(tokens).parse_all_objects()
    except Exception:
        return []

    rules: list[AliasRule] = []
    for value in objects:
        resolve = value.get("resolve")
        if not isinstance(resolve, dict):
            continue
        alias = resolve.get("alias")
        if isinstance(alias, dict):
            for find, replacement in alias.items():
                if isinstance(find, str) and isinstance(replacement, (str, StaticPath)):
                    rules.append(AliasRule(find, replacement))
        elif isinstance(alias, list):
            for entry in alias:
                if not isinstance(entry, dict):
                    continue
                find = entry.get("find")
                replacement = entry.get("replacement")
                if isinstance(find, str) and isinstance(replacement, (str, StaticPath)):
                    rules.append(AliasRule(find, replacement))
    return rules


def _match(find: str, specifier: str) -> str | None:
    exact = find.endswith("$")
    pattern = find[:-1] if exact else find
    if "*" in pattern:
        prefix, suffix = pattern.split("*", 1)
        if not specifier.startswith(prefix) or not specifier.endswith(suffix):
            return None
        end = len(specifier) - len(suffix) if suffix else len(specifier)
        return specifier[len(prefix):end]
    if specifier == pattern:
        return ""
    if not exact and specifier.startswith(pattern + "/"):
        return specifier[len(pattern):]
    return None


def _rules_for_config(config_path: Path) -> list[AliasRule]:
    try:
        budgets.json_bytes_guard(config_path, budgets.MAX_FILE_BYTES)
        source = budgets.read_text_limited(config_path, budgets.MAX_FILE_BYTES)
    except (OSError, budgets.ScannerBudgetError):
        return []
    return _literal_aliases(source)


def aliases_for_file(repo_dir, file_path: Path, cache=None):
    """Return static alias rules from the nearest supported config files."""
    repo = Path(repo_dir).resolve()
    current = Path(file_path).resolve().parent
    configs: list[Path] = []
    while True:
        for name in _CONFIG_NAMES:
            candidate = current / name
            if candidate.is_file():
                configs.append(candidate)
        if current == repo or current.parent == current:
            break
        current = current.parent
    aliases = []
    for config in configs:
        if cache is not None and config not in cache:
            cache[config] = _rules_for_config(config)
        rules = cache[config] if cache is not None else _rules_for_config(config)
        aliases.extend((config, rule) for rule in rules)
    return aliases


def resolve_alias(repo_dir, file_path: Path, specifier: str, cache=None):
    """Return ``(kind, reason)`` for a matching static local alias."""
    unresolved = []
    for config_path, rule in aliases_for_file(repo_dir, file_path, cache=cache):
        match = _match(rule.find, specifier)
        if match is None:
            continue
        if isinstance(rule.replacement, StaticPath):
            parts = tuple(part.replace("*", match or "") for part in rule.replacement.parts)
            target = Path(config_path.parent, *parts).resolve()
            if match and "*" not in "".join(rule.replacement.parts):
                target = (target / match.lstrip("/")).resolve()
        else:
            replacement = rule.replacement.replace("*", match or "")
            if not replacement.startswith((".", "/")):
                continue
            target = (config_path.parent / replacement).resolve()
        try:
            target.relative_to(Path(repo_dir).resolve())
        except ValueError:
            unresolved.append(f"bundler alias {rule.find!r} escapes repository root")
            continue
        if target.is_file() or (not target.suffix and any((target.with_suffix(suffix)).is_file() for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))):
            return "local", ""
        if not target.suffix and any((target / name).is_file() for name in ("index.ts", "index.tsx", "index.js", "index.jsx")):
            return "local", ""
        unresolved.append(f"bundler alias {rule.find!r} has no existing local target")
    if unresolved:
        return "unresolved", unresolved[0]
    return None, ""
