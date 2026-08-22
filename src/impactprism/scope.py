"""Shared, bounded scan-scope helpers.

The public ``exclude`` input historically accepted directory basenames. The
same input now also accepts repository-relative directory prefixes so a caller
can exclude one fixture tree without excluding every directory with the same
basename elsewhere in the repository.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

__all__ = ["normalize_excludes", "is_excluded_directory"]


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
