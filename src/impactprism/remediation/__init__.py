"""Offline remediation planning and patch generation."""

from .models import (
    DependencyGraph,
    LockfilePlan,
    LockfilePlanResult,
    PatchSpec,
    PatchTarget,
    PrDescription,
    PrProposal,
    RemediationError,
    RemediationPlan,
    VerificationResult,
)
from .patcher import apply_manifest_patch, build_manifest_patch, compute_lockfile_patch

__all__ = [
    "PatchTarget",
    "PatchSpec",
    "LockfilePlan",
    "LockfilePlanResult",
    "DependencyGraph",
    "VerificationResult",
    "PrDescription",
    "RemediationPlan",
    "PrProposal",
    "RemediationError",
    "build_manifest_patch",
    "apply_manifest_patch",
    "compute_lockfile_patch",
]
