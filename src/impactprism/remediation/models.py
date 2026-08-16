"""Data models for offline dependency remediation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

__all__ = [
    "PatchTarget",
    "PatchSpec",
    "LockfilePlan",
    "LockfilePlanResult",
    "DependencyGraph",
    "VerificationResult",
    "PrDescription",
    "PrProposal",
    "RemediationPlan",
    "RemediationError",
]


class PatchTarget(str, Enum):
    MANIFEST = "manifest"
    LOCKFILE = "lockfile"
    GO_SUM = "go.sum"


@dataclass(kw_only=True)
class PatchSpec:
    path: Path
    target: PatchTarget
    after: str
    before: str = ""
    package: str = ""
    version: str = ""
    kind: str = ""

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "target": self.target.value,
            "after": self.after,
            "before": self.before,
            "package": self.package,
            "version": self.version,
            "kind": self.kind,
        }


@dataclass(kw_only=True)
class LockfilePlan:
    command: str
    args: list[str]
    cwd: Path
    dry_run: bool = False
    fallback_patch: PatchSpec | None = None
    lockfile: str | None = None
    env: dict | None = None

    def as_dict(self) -> dict:
        return {
            "command": self.command,
            "args": list(self.args),
            "cwd": str(self.cwd),
            "dry_run": self.dry_run,
            "fallback_patch": self.fallback_patch.as_dict() if self.fallback_patch else None,
            "lockfile": self.lockfile,
            "env": dict(self.env) if self.env else None,
        }


@dataclass(kw_only=True)
class LockfilePlanResult:
    command: str
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    patched: bool
    applied: PatchSpec | None = None

    def as_dict(self) -> dict:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "patched": self.patched,
            "applied": self.applied.as_dict() if self.applied else None,
        }


@dataclass(kw_only=True)
class DependencyGraph:
    before: dict[str, str]
    after: dict[str, str]
    text_before: str
    text_after: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "before": dict(self.before),
            "after": dict(self.after),
            "text_before": self.text_before,
            "text_after": self.text_after,
            "added": list(self.added),
            "removed": list(self.removed),
        }


@dataclass(kw_only=True)
class VerificationResult:
    resolved: bool
    finding_type: str
    package: str
    scan_before: dict
    scan_after: dict
    remaining: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "resolved": self.resolved,
            "finding_type": self.finding_type,
            "package": self.package,
            "scan_before": _serialize_scan(self.scan_before),
            "scan_after": _serialize_scan(self.scan_after),
            "remaining": [dict(item) for item in self.remaining],
        }


def _serialize_scan(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return [dict(item) if isinstance(item, dict) else item for item in value]
    return value


@dataclass(kw_only=True)
class PrDescription:
    title: str
    body: str
    changed_files: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    scan_result: dict
    unresolved_risks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "changed_files": list(self.changed_files),
            "test_commands": list(self.test_commands),
            "scan_result": dict(self.scan_result),
            "unresolved_risks": list(self.unresolved_risks),
        }


@dataclass(kw_only=True)
class PrProposal:
    branch_name: str
    commit_message: str
    description: PrDescription

    def as_dict(self) -> dict:
        return {
            "branch_name": self.branch_name,
            "commit_message": self.commit_message,
            "description": self.description.as_dict(),
        }


@dataclass(kw_only=True)
class RemediationPlan:
    finding: dict
    manifest_patch: PatchSpec | None = None
    lockfile_plan: LockfilePlan | None = None
    verification: VerificationResult | None = None
    pr_description: PrDescription | None = None
    pr_proposal: PrProposal | None = None
    proposed_only: bool = True

    def __post_init__(self) -> None:
        self.proposed_only = True

    def as_dict(self) -> dict:
        return {
            "finding": dict(self.finding),
            "manifest_patch": self.manifest_patch.as_dict() if self.manifest_patch else None,
            "lockfile_plan": self.lockfile_plan.as_dict() if self.lockfile_plan else None,
            "verification": self.verification.as_dict() if self.verification else None,
            "pr_description": self.pr_description.as_dict() if self.pr_description else None,
            "pr_proposal": self.pr_proposal.as_dict() if self.pr_proposal else None,
            "proposed_only": True,
        }


class RemediationError(Exception):
    """Raised when a remediation patch cannot be safely applied."""

    def __init__(self, message: str):
        super().__init__(message)
