"""Baseline comparison for incremental dependency-integrity scans."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .reporting import findings_from_report


DELTA_SCHEMA_VERSION = 1


def _identity(finding):
    identity = {
        key: finding.get(key)
        for key in (
            "finding_type",
            "ecosystem",
            "package",
            "file",
            "line",
            "column",
            "scope",
            "manifest",
            "lockfile",
        )
    }
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def finding_key(finding):
    """Return the stable comparison key for a canonical or legacy finding."""

    finding_id = finding.get("finding_id")
    if finding_id:
        return str(finding_id)
    return hashlib.sha256(_identity(finding).encode("utf-8")).hexdigest()[:16]


def _indexed(findings):
    indexed = {}
    for finding in findings:
        indexed.setdefault(finding_key(finding), finding)
    return indexed


def compare_reports(current, baseline, *, baseline_path=None):
    """Compare two reports without treating severity changes as new findings."""

    current_index = _indexed(findings_from_report(current))
    baseline_index = _indexed(findings_from_report(baseline))
    new_keys = sorted(set(current_index) - set(baseline_index))
    existing_keys = sorted(set(current_index) & set(baseline_index))
    resolved_keys = sorted(set(baseline_index) - set(current_index))

    return {
        "schema_version": DELTA_SCHEMA_VERSION,
        "generator": "impactprism-baseline",
        "baseline_report": str(baseline_path) if baseline_path is not None else None,
        "baseline_schema_version": baseline.get("schema_version"),
        "current_schema_version": current.get("schema_version"),
        "new_findings": [current_index[key] for key in new_keys],
        "existing_findings": [current_index[key] for key in existing_keys],
        "resolved_findings": [baseline_index[key] for key in resolved_keys],
        "counts": {
            "current": len(current_index),
            "baseline": len(baseline_index),
            "new": len(new_keys),
            "existing": len(existing_keys),
            "resolved": len(resolved_keys),
        },
    }


def load_report(path):
    report_path = Path(path)
    try:
        value = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError("unable to read baseline report: " + str(error)) from error
    except json.JSONDecodeError as error:
        raise ValueError("invalid JSON in baseline report: " + str(error)) from error
    if not isinstance(value, dict):
        raise ValueError("baseline report must contain a JSON object")
    return value


def delta_exit_code(report, delta):
    """Return the incremental gate code while preserving scanner-error semantics."""

    if any(item.get("finding_type") == "SCANNER_ERROR" for item in findings_from_report(report)):
        return 2
    return 1 if delta["new_findings"] else 0
