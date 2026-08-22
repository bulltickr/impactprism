"""Shared, bounded scan-scope helpers.

The public ``exclude`` input historically accepted directory basenames. The
same input now also accepts repository-relative directory prefixes so a caller
can exclude one fixture tree without excluding every directory with the same
basename elsewhere in the repository.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

__all__ = ["normalize_excludes", "normalize_roots", "is_excluded_directory"]

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_excludes(values) -> frozenset[str]:
    """Return safe, deterministic directory-name/path-prefix exclusions."""

    normalized = set()
    for value in values or ():
        if not isinstance(value, str):
            raise ValueError("scan exclusions must be strings")
        item = value.strip().replace("\\", "/")
        while item.startswith("./"):
            item = item[2:]
        if not item or item == ".":
            raise ValueError("scan exclusions must be non-empty relative paths")
        if item.startswith("/") or ":" in item.split("/", 1)[0]:
            raise ValueError("scan exclusions must be relative paths: " + value)
        path = PurePosixPath(item)
        if any(part in ("", ".", "..") for part in path.parts):
            raise ValueError("scan exclusions cannot contain path traversal: " + value)
        normalized.add("/".join(path.parts))
    return frozenset(normalized)


def normalize_roots(values) -> tuple[str, ...]:
    """Normalize explicit repository-relative scan roots.

    Roots are directory paths, not globs. Keeping this contract narrow makes
    a report reproducible and prevents a path that escapes the repository from
    becoming an accidental scan boundary.
    """

    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise ValueError("scan roots must be a list of repository-relative paths")
    normalized = set()
    for raw in values:
        if not isinstance(raw, (str, os.PathLike)):
            raise ValueError("scan roots must contain only path strings")
        value = os.fspath(raw).strip().replace("\\", "/")
        if not value:
            raise ValueError("scan roots cannot contain an empty path")
        if value.startswith("/") or _WINDOWS_DRIVE.match(value):
            raise ValueError("scan roots must be repository-relative: " + value)
        while value.startswith("./"):
            value = value[2:]
        if value in ("", "."):
            normalized.add(".")
            continue
        parts = tuple(part for part in value.split("/") if part not in ("", "."))
        if not parts or any(part == ".." for part in parts):
            raise ValueError(
                "scan roots cannot contain parent-directory traversal: " + value
            )
        normalized.add("/".join(parts))
    if not normalized:
        raise ValueError("scan roots must contain at least one package path")
    ordered = tuple(sorted(normalized, key=lambda item: (item != ".", item)))
    for index, root in enumerate(ordered):
        if root == ".":
            if len(ordered) > 1:
                raise ValueError("scan root '.' cannot be combined with another root")
            continue
        root_parts = tuple(root.split("/"))
        for other in ordered[:index]:
            if other == ".":
                continue
            other_parts = tuple(other.split("/"))
            if root_parts[: len(other_parts)] == other_parts:
                raise ValueError("scan roots overlap: " + other + " and " + root)
    return ordered


def is_excluded_directory(repo_root, candidate, excludes) -> bool:
    """Check a directory against basename and relative-prefix exclusions."""

    excluded = excludes if isinstance(excludes, frozenset) else normalize_excludes(excludes)
    if not excluded:
        return False
    root = Path(repo_root).resolve()
    path = Path(candidate).resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    relative_parts = relative.parts
    relative_posix = "/".join(relative_parts)
    for item in excluded:
        if "/" not in item and item in relative_parts:
            return True
        if "/" in item and (
            relative_posix == item or relative_posix.startswith(item + "/")
        ):
            return True
    return False
