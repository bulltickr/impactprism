from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple, Union

__all__ = ["npm_satisfies", "valid_range"]

_ANY_COMPARATOR = "any"


@dataclass(frozen=True)
class _Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple = ()


@dataclass(frozen=True)
class _Comparator:
    op: str
    version: Optional[_Version]


_PROTOCOL = object()

_PROTOCOL_RE = re.compile(
    r"^(?:workspace|file|link|git|github|gitlab|bitbucket|https?|git\+https?|git\+ssh|tag):"
)

_RAW_VERSION_RE = re.compile(
    r"^(?:v|V)?(\d+)\.(\d+)\.(\d+)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

_LOOSE_RE = re.compile(
    r"^(?:v|V)?"
    r"(\d+|\*|x|X)"
    r"(?:\.(\d+|\*|x|X)"
    r"(?:\.(\d+|\*|x|X)"
    r"(?:\.(\d+|\*|x|X))?)?)?"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

_HYPHEN_RE = re.compile(r"^\s*(.+?)\s+-\s+(.+?)\s*$")

_WILDCARD_TOKENS = {"*", "latest", "x", "X"}


def _parse_prerelease(text: str) -> tuple:
    identifiers = []
    for ident in text.split("."):
        if not ident:
            return ()
        if re.fullmatch(r"\d+", ident):
            identifiers.append((0, int(ident)))
        else:
            identifiers.append((1, ident))
    return tuple(identifiers)


def _parse_version(text: str) -> Optional[_Version]:
    stripped = text.strip()
    match = _RAW_VERSION_RE.match(stripped)
    if not match:
        return None
    prerelease = _parse_prerelease(match.group(4)) if match.group(4) else ()
    return _Version(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)


def _parse_loose(text: str) -> Optional[Tuple[list, tuple]]:
    match = _LOOSE_RE.match(text.strip())
    if not match:
        return None
    parts = []
    for group in (match.group(1), match.group(2), match.group(3), match.group(4)):
        if group is None:
            break
        if group in ("*", "x", "X"):
            parts.append(None)
        else:
            parts.append(int(group))
    if not parts:
        return None
    if all(part is None for part in parts):
        return [], ()
    if len(parts) >= 4 and parts[3] is not None:
        return None
    prerelease = _parse_prerelease(match.group(5)) if match.group(5) else ()
    return parts, prerelease


def _lower_from_parts(parts: list, prerelease: tuple) -> _Version:
    values = [part if part is not None else 0 for part in parts[:3]]
    values += [0] * (3 - len(values))
    return _Version(values[0], values[1], values[2], prerelease)


def _upper_bound(parts: list) -> _Version:
    values = [part if part is not None else 0 for part in parts[:3]]
    values += [0] * (3 - len(values))
    index = 0
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] is not None:
            index = min(i, 2)
            break
    values[index] += 1
    for i in range(index + 1, 3):
        values[i] = 0
    return _Version(values[0], values[1], values[2], ())


def _parse_caret(text: str) -> Optional[list]:
    parsed = _parse_loose(text)
    if parsed is None:
        return None
    parts, prerelease = parsed
    if not parts:
        return [_Comparator(_ANY_COMPARATOR, None)]
    major = parts[0] if len(parts) > 0 and parts[0] is not None else 0
    minor = parts[1] if len(parts) > 1 and parts[1] is not None else None
    patch = parts[2] if len(parts) > 2 and parts[2] is not None else None
    lower = _lower_from_parts(parts, prerelease)
    if major > 0:
        upper_values = [major + 1, 0, 0]
    elif minor is not None:
        if minor > 0:
            upper_values = [0, minor + 1, 0]
        elif patch is not None:
            upper_values = [0, 0, patch + 1]
        else:
            upper_values = [0, 1, 0]
    else:
        upper_values = [1, 0, 0]
    upper = _Version(upper_values[0], upper_values[1], upper_values[2], ())
    return [_Comparator("gte", lower), _Comparator("lt", upper)]


def _parse_tilde(text: str) -> Optional[list]:
    parsed = _parse_loose(text)
    if parsed is None:
        return None
    parts, prerelease = parsed
    if not parts:
        return [_Comparator(_ANY_COMPARATOR, None)]
    major = parts[0] if len(parts) > 0 and parts[0] is not None else 0
    minor = parts[1] if len(parts) > 1 and parts[1] is not None else None
    lower = _lower_from_parts(parts, prerelease)
    if minor is not None:
        upper_values = [major, minor + 1, 0]
    else:
        upper_values = [major + 1, 0, 0]
    upper = _Version(upper_values[0], upper_values[1], upper_values[2], ())
    return [_Comparator("gte", lower), _Comparator("lt", upper)]


def _parse_op(op: str, text: str) -> Optional[list]:
    parsed = _parse_loose(text)
    if parsed is None:
        return None
    parts, prerelease = parsed
    if not parts:
        return None
    op_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "eq"}
    full = len(parts) == 3 and all(part is not None for part in parts)
    if full:
        version = _Version(parts[0], parts[1], parts[2], prerelease)
        return [_Comparator(op_map[op], version)]
    lower = _lower_from_parts(parts, prerelease)
    if op == ">=":
        return [_Comparator("gte", lower)]
    if op == "<":
        return [_Comparator("lt", lower)]
    if op == ">":
        return [_Comparator("gte", _upper_bound(parts))]
    if op == "<=":
        return [_Comparator("lt", _upper_bound(parts))]
    return [_Comparator("gte", lower), _Comparator("lt", _upper_bound(parts))]


def _parse_exact_or_x(text: str) -> Optional[list]:
    parsed = _parse_loose(text)
    if parsed is None:
        return None
    parts, prerelease = parsed
    if not parts:
        return [_Comparator(_ANY_COMPARATOR, None)]
    if len(parts) == 3 and all(part is not None for part in parts):
        version = _Version(parts[0], parts[1], parts[2], prerelease)
        return [_Comparator("gte", version), _Comparator("lte", version)]
    lower = _lower_from_parts(parts, prerelease)
    return [_Comparator("gte", lower), _Comparator("lt", _upper_bound(parts))]


def _parse_token(token: str) -> Optional[list]:
    if token in _WILDCARD_TOKENS:
        return [_Comparator(_ANY_COMPARATOR, None)]
    if token.startswith("^"):
        if len(token) < 2:
            return None
        return _parse_caret(token[1:])
    if token.startswith("~>"):
        if len(token) < 3:
            return None
        return _parse_tilde(token[2:])
    if token.startswith("~"):
        if len(token) < 2:
            return None
        return _parse_tilde(token[1:])
    for op in (">=", "<=", ">", "<", "="):
        if token.startswith(op):
            if len(token) <= len(op):
                return None
            return _parse_op(op, token[len(op):])
    return _parse_exact_or_x(token)


def _parse_hyphen(left: str, right: str) -> Optional[list]:
    left_parsed = _parse_loose(left)
    if left_parsed is None:
        return None
    left_parts, left_pre = left_parsed
    comparators = []
    if not left_parts:
        comparators.append(_Comparator("gte", _Version(0, 0, 0, ())))
    else:
        comparators.append(_Comparator("gte", _lower_from_parts(left_parts, left_pre)))
    right_parsed = _parse_loose(right)
    if right_parsed is None:
        return None
    right_parts, right_pre = right_parsed
    if not right_parts:
        return None
    if len(right_parts) == 3 and all(part is not None for part in right_parts):
        comparators.append(
            _Comparator("lte", _Version(right_parts[0], right_parts[1], right_parts[2], right_pre))
        )
    else:
        comparators.append(_Comparator("lt", _upper_bound(right_parts)))
    return comparators


def _parse_alternative(alternative: str) -> Optional[list]:
    stripped = alternative.strip()
    if not stripped:
        return None
    hyphen = _HYPHEN_RE.match(stripped)
    if hyphen:
        return _parse_hyphen(hyphen.group(1), hyphen.group(2))
    comparators = []
    for token in stripped.split():
        parsed = _parse_token(token)
        if parsed is None:
            return None
        comparators.extend(parsed)
    return comparators


def _parse_alias(text: str) -> Optional[list]:
    rest = text[len("npm:"):]
    if not rest:
        return None
    if "@" in rest:
        candidate = rest.rsplit("@", 1)[1]
        parsed = _parse_range(candidate)
        if parsed is not None:
            return parsed
        range_part = rest
    else:
        range_part = rest
    return _parse_range(range_part)


def _parse_range(text: str):
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("npm:"):
        return _parse_alias(stripped)
    if ":" in stripped:
        if _PROTOCOL_RE.match(stripped):
            return _PROTOCOL
        return None
    alternatives = []
    for alternative in stripped.split("||"):
        parsed = _parse_alternative(alternative)
        if parsed is None:
            return None
        alternatives.append(parsed)
    return alternatives


def _compare(a: _Version, b: _Version) -> int:
    for left, right in ((a.major, b.major), (a.minor, b.minor), (a.patch, b.patch)):
        if left != right:
            return -1 if left < right else 1
    if a.prerelease == b.prerelease:
        return 0
    if not a.prerelease:
        return 1
    if not b.prerelease:
        return -1
    return -1 if a.prerelease < b.prerelease else 1


def _comparator_matches(comparator: _Comparator, version: _Version) -> bool:
    if comparator.op == _ANY_COMPARATOR:
        return True
    result = _compare(version, comparator.version)
    if comparator.op == "gt":
        return result > 0
    if comparator.op == "gte":
        return result >= 0
    if comparator.op == "lt":
        return result < 0
    if comparator.op == "lte":
        return result <= 0
    return result == 0


def _range_set_matches(comparators: list, version: _Version) -> bool:
    for comparator in comparators:
        if not _comparator_matches(comparator, version):
            return False
    if version.prerelease:
        allowed = False
        for comparator in comparators:
            if comparator.op == _ANY_COMPARATOR:
                allowed = True
                break
            comparator_version = comparator.version
            if comparator_version is not None and comparator_version.prerelease:
                if (
                    comparator_version.major == version.major
                    and comparator_version.minor == version.minor
                    and comparator_version.patch == version.patch
                ):
                    allowed = True
                    break
        if not allowed:
            return False
    return True


def valid_range(specifier: str) -> bool:
    """Return True iff the specifier parses as a recognizable npm specifier."""
    return _parse_range(specifier) is not None


def npm_satisfies(specifier: str, version: str) -> bool:
    """Return True iff the npm specifier is satisfied by the given version."""
    parsed = _parse_range(specifier)
    if parsed is _PROTOCOL:
        return True
    if parsed is None:
        return False
    candidate = _parse_version(version)
    if candidate is None:
        return False
    return any(_range_set_matches(alternative, candidate) for alternative in parsed)
