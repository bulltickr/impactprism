"""Canonical scan-report normalization and policy helpers.

All public output surfaces should consume the normalized representation from
this module.  The normalizer also accepts the legacy category-only report
shape so older report files remain readable during the schema transition.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .drift.models import FindingType

REPORT_SCHEMA_VERSION = 1

FINDING_CATEGORIES = {
    FindingType.UNDECLARED_DIRECT_USE.name: "undeclared",
    FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY.name: "undeclared",
    FindingType.DECLARED_UNUSED_CANDIDATE.name: "drift",
    FindingType.LOCKFILE_MANIFEST_MISMATCH.name: "integrity",
    FindingType.MISSING_LOCKFILE.name: "integrity",
    FindingType.SCOPE_MISMATCH.name: "scope-mismatch",
    FindingType.UNRESOLVED_IMPORT.name: "unresolved",
    FindingType.SCANNER_ERROR.name: "scanner-error",
}

_LEGACY_TYPES = {
    "undeclared": FindingType.UNDECLARED_DIRECT_USE.name,
    "drift": FindingType.DECLARED_UNUSED_CANDIDATE.name,
    "scope-mismatch": FindingType.SCOPE_MISMATCH.name,
    "integrity": FindingType.LOCKFILE_MANIFEST_MISMATCH.name,
    "unresolved": FindingType.UNRESOLVED_IMPORT.name,
}


def finding_category(finding_type: str | None) -> str:
    """Return the stable report category for a finding type."""

    return FINDING_CATEGORIES.get(str(finding_type or "UNKNOWN"), "other")


def _normalise_finding(value: dict, *, category: str | None = None) -> dict:
    finding = dict(value)
    finding_type = str(
        finding.get("finding_type")
        or _LEGACY_TYPES.get(category or "", "UNKNOWN")
    )
    finding["finding_type"] = finding_type
    finding["category"] = finding_category(finding_type)
    if finding.get("severity") is None:
        finding["severity"] = "info"
    if finding.get("confidence") is None:
        finding["confidence"] = "medium"
    if finding.get("package") is None and finding.get("name") is not None:
        finding["package"] = finding["name"]
    return finding


def findings_from_report(report: dict) -> list[dict]:
    """Return normalized findings from modern or legacy report JSON."""

    modern = report.get("findings")
    if isinstance(modern, list):
        return [
            _normalise_finding(item)
            for item in modern
            if isinstance(item, dict)
        ]

    findings = []
    for category in (
        "undeclared",
        "drift",
        "scope-mismatch",
        "integrity",
        "unresolved",
    ):
        values = report.get(category, []) or []
        if not isinstance(values, list):
            raise ValueError("scan report field " + category + " must be a list")
        for value in values:
            findings.append(
                _normalise_finding(
                    {"name": str(value), "package": str(value)},
                    category=category,
                )
            )
    return findings


def findings_by_type(findings: Iterable[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for finding in findings:
        finding_type = str(finding.get("finding_type") or "UNKNOWN")
        grouped.setdefault(finding_type, []).append(finding)
    return {key: grouped[key] for key in sorted(grouped)}


def build_scan_report(
    *,
    repo: str,
    ecosystem: str,
    findings: Iterable[dict],
    package_name: str = "unknown",
    package_version: str = "0.0.0",
    declared: Iterable[str] = (),
    imported: Iterable[str] = (),
    sbom: dict | None = None,
    diagnostics: Iterable[dict] = (),
) -> dict:
    """Build the canonical JSON report consumed by all output adapters."""

    normalized = sorted(
        [_normalise_finding(item) for item in findings],
        key=lambda item: (
            str(item.get("finding_type") or ""),
            str(item.get("package") or ""),
            str(item.get("file") or ""),
            int(item.get("line") or 0),
            str(item.get("finding_id") or ""),
        ),
    )
    by_type = findings_by_type(normalized)

    def packages(finding_type: str) -> list[str]:
        return sorted(
            {
                str(item["package"])
                for item in by_type.get(finding_type, [])
                if item.get("package") is not None
            }
        )

    severity_counts = Counter(str(item.get("severity") or "info").lower() for item in normalized)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generator": "impactprism",
        "repo": str(repo),
        "package_name": package_name or "unknown",
        "package_version": package_version or "0.0.0",
        "ecosystem": ecosystem,
        "declared": sorted({str(value) for value in declared}),
        "imported": sorted({str(value) for value in imported}),
        "drift": packages(FindingType.DECLARED_UNUSED_CANDIDATE.name),
        "undeclared": sorted(
            set(packages(FindingType.UNDECLARED_DIRECT_USE.name))
            | set(packages(FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY.name))
        ),
        "scope-mismatch": packages(FindingType.SCOPE_MISMATCH.name),
        "integrity": sorted(
            set(packages(FindingType.LOCKFILE_MANIFEST_MISMATCH.name))
            | set(packages(FindingType.MISSING_LOCKFILE.name))
        ),
        "unresolved": packages(FindingType.UNRESOLVED_IMPORT.name),
        "findings": normalized,
        "diagnostics": list(diagnostics),
        "counts": {
            "total": len(normalized),
            "by_type": {key: len(value) for key, value in by_type.items()},
            "by_severity": dict(sorted(severity_counts.items())),
        },
        "sbom": sbom,
    }


def scan_exit_code(report: dict, findings=None) -> int:
    """Return the stable CLI exit code for a canonical report."""

    findings = findings_from_report(report) if findings is None else list(findings)
    if any(item.get("finding_type") == FindingType.SCANNER_ERROR.name for item in findings):
        return 2
    return 1 if findings else 0
