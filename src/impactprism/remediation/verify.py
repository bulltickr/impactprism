from __future__ import annotations

from ..drift import analyze_repo
from .models import VerificationResult

__all__ = ["verify_remediation"]


def verify_remediation(
    repo_dir: str,
    finding: dict,
    *,
    ecosystem: str = "auto",
    commit_sha: str | None = None,
    scan_before: list | None = None,
) -> VerificationResult:
    """Re-run the analyzer after a remediation to confirm a finding is gone.

    ``scan_before`` optionally carries the pre-patch findings (a list of dicts
    from ``DriftReport.as_dicts``). When it is ``None`` the analyzer is invoked
    once and that snapshot is treated as both the before and after scan.
    """
    finding_type = finding.get("finding_type")
    package = finding.get("package")

    def failure():
        return VerificationResult(
            resolved=False,
            finding_type=finding_type,
            package=package,
            scan_before={},
            scan_after={},
            remaining=[],
        )

    if scan_before is None:
        try:
            snapshot = analyze_repo(
                repo_dir, ecosystem=ecosystem, commit_sha=commit_sha
            ).as_dicts()
        except Exception:
            return failure()
        before = snapshot
        after = snapshot
    else:
        before = scan_before
        try:
            after = analyze_repo(
                repo_dir, ecosystem=ecosystem, commit_sha=commit_sha
            ).as_dicts()
        except Exception:
            return failure()

    remaining = [
        item
        for item in after
        if item.get("finding_type") == finding_type and item.get("package") == package
    ]
    return VerificationResult(
        resolved=not remaining,
        finding_type=finding_type,
        package=package,
        scan_before=before,
        scan_after=after,
        remaining=remaining,
    )
