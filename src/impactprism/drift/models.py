"""Data models for dependency drift findings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

__all__ = ["FindingType", "Severity", "Confidence", "Status", "Finding"]


class FindingType(str, Enum):
    UNDECLARED_DIRECT_USE = "UNDECLARED_DIRECT_USE"
    DECLARED_UNUSED_CANDIDATE = "DECLARED_UNUSED_CANDIDATE"
    DIRECT_DEPENDENCY_USED_TRANSITIVELY = "DIRECT_DEPENDENCY_USED_TRANSITIVELY"
    LOCKFILE_MANIFEST_MISMATCH = "LOCKFILE_MANIFEST_MISMATCH"
    MISSING_LOCKFILE = "MISSING_LOCKFILE"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    UNRESOLVED_IMPORT = "UNRESOLVED_IMPORT"
    SCANNER_ERROR = "SCANNER_ERROR"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(str, Enum):
    OPEN = "open"
    ADVISORY = "advisory"
    RESOLVED = "resolved"


@dataclass(kw_only=True)
class Finding:
    finding_type: FindingType
    finding_id: str = ""
    severity: Severity
    confidence: Confidence
    ecosystem: str
    package: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    manifest: str | None = None
    lockfile: str | None = None
    commit_sha: str | None = None
    scope: str | None = None
    explanation: str = ""
    status: Status = Status.OPEN

    def __post_init__(self) -> None:
        if not self.finding_id:
            self.finding_id = self._hash_identity(self._identity())

    @staticmethod
    def _hash_identity(identity: dict) -> str:
        serialized = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def _identity(self, repo_dir=None) -> dict:
        def stable_path(value):
            if value is None or repo_dir is None:
                return value
            try:
                return Path(value).resolve().relative_to(Path(repo_dir).resolve()).as_posix()
            except (OSError, ValueError):
                return str(value).replace("\\", "/")

        return {
            "finding_type": self.finding_type.name,
            "ecosystem": self.ecosystem,
            "package": self.package,
            "file": stable_path(self.file),
            "line": self.line,
            "column": self.column,
            "scope": self.scope,
            "manifest": stable_path(self.manifest),
            "lockfile": stable_path(self.lockfile),
        }

    def refresh_id(self, repo_dir) -> None:
        """Recompute the ID with repository-relative provenance paths."""

        self.finding_id = self._hash_identity(self._identity(repo_dir))

    def as_dict(self) -> dict:
        return {
            "finding_type": self.finding_type.name,
            "finding_id": self.finding_id,
            "severity": self.severity.name,
            "confidence": self.confidence.name,
            "ecosystem": self.ecosystem,
            "package": self.package,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "manifest": self.manifest,
            "lockfile": self.lockfile,
            "commit_sha": self.commit_sha,
            "scope": self.scope,
            "explanation": self.explanation,
            "status": self.status.name,
        }
