import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .cra_clauses import load_cra_clauses
from .reporting import findings_from_report
from .version import __version__


EVIDENCE_STATUSES = ("PASS", "FAIL", "EVIDENCE_GAP", "NOT_ASSESSED", "REVIEW_REQUIRED")

_CLAUSE_MAP_DATA = load_cra_clauses()


def _derive_clause_map():
    return {
        category: list(entry["clauses"])
        for category, entry in _CLAUSE_MAP_DATA.get("categories", {}).items()
    }


CLAUSE_MAP = _derive_clause_map()
RATIONALES = {
    "undeclared": (
        "Undeclared dependencies fall outside the SBOM/component transparency "
        "expected under Article 13(1)(b) and may expand the attack surface; "
        "this warrants manual review against Article 13(1)(b), Article 14(1) "
        "and Annex VII to determine whether any obligation applies."
    ),
    "drift": (
        "Unnecessary installed components may expand the attack surface and "
        "warrants review against Article 13(1)(a) and Annex I Part I to "
        "confirm whether secure-by-default or minimisation expectations apply."
    ),
}
_FINDING_TYPE_TO_CATEGORY = {
    "UNDECLARED_DIRECT_USE": "undeclared",
    "DIRECT_DEPENDENCY_USED_TRANSITIVELY": "undeclared",
    "LOCKFILE_MANIFEST_MISMATCH": "undeclared",
    "MISSING_LOCKFILE": "undeclared",
    "DECLARED_UNUSED_CANDIDATE": "drift",
    "SCOPE_MISMATCH": "drift",
    "UNRESOLVED_IMPORT": "undeclared",
    "SCANNER_ERROR": "undeclared",
}
CRA_REFERENCES = {
    clause_id: clause["title"]
    for clause_id, clause in _CLAUSE_MAP_DATA["clauses"].items()
}


def _load_json(path):
    try:
        source_bytes = path.read_bytes()
        value = json.loads(source_bytes.decode("utf-8"))
    except OSError as error:
        raise ValueError("unable to read scan report: " + str(error))
    except json.JSONDecodeError as error:
        raise ValueError("invalid JSON in scan report: " + str(error))
    if not isinstance(value, dict):
        raise ValueError("scan report must contain a JSON object")
    return value, hashlib.sha256(source_bytes).hexdigest()


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _package_name(report):
    value = report.get("package_name")
    return str(value) if value else "unknown"


def _package_version(report):
    value = report.get("package_version")
    return str(value) if value else "0.0.0"


def _report_entries(report, category):
    values = report.get(category, [])
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("scan report field " + category + " must be a list")
    return sorted(str(value) for value in values)


def _classify_status(category):
    if category in ("drift", "undeclared"):
        return "REVIEW_REQUIRED"
    return "NOT_ASSESSED"


def _build_findings(report):
    findings = []
    for item in findings_from_report(report):
        finding_type = item.get("finding_type") or "UNKNOWN"
        category = _FINDING_TYPE_TO_CATEGORY.get(finding_type)
        if category is None:
            category = "undeclared" if item.get("category") == "undeclared" else "drift"
        name = str(item.get("package") or item.get("name") or "unknown")
        rationale = RATIONALES.get(category, "The finding requires review against the supported evidence controls.")
        findings.append(
            {
                "finding_type": finding_type,
                "category": category,
                "name": name,
                "package": item.get("package"),
                "file": item.get("file"),
                "line": item.get("line"),
                "column": item.get("column"),
                "severity": str(item.get("severity") or "info").lower(),
                "confidence": str(item.get("confidence") or "medium").lower(),
                "explanation": item.get("explanation") or "",
                "clauses": CLAUSE_MAP.get(category, []),
                "rationale": rationale,
                "status": _classify_status(category),
            }
        )
    return findings


def _build_evidence(report, source_path, source_report_sha256):
    findings = _build_findings(report)
    undeclared_count = sum(1 for finding in findings if finding["category"] == "undeclared")
    drift_count = sum(1 for finding in findings if finding["category"] == "drift")
    status_counts = {status: 0 for status in EVIDENCE_STATUSES}
    for finding in findings:
        status_counts[finding["status"]] += 1
    return {
        "generator": "impactprism-evidence",
        "version": __version__,
        "timestamp": _utc_timestamp(),
        "schema_version": _CLAUSE_MAP_DATA["schema_version"],
        "map_version": _CLAUSE_MAP_DATA["map_version"],
        "legal_source": _CLAUSE_MAP_DATA["legal_source"],
        "source_report": str(source_path),
        "source_report_sha256": source_report_sha256,
        "package_name": _package_name(report),
        "package_version": _package_version(report),
        "clause_map": CLAUSE_MAP,
        "statuses": list(EVIDENCE_STATUSES),
        "overall_status": "PASS" if not findings else "REVIEW_REQUIRED",
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "undeclared_count": undeclared_count,
            "drift_count": drift_count,
            "clean": not findings,
            "status_counts": status_counts,
        },
    }


def build_evidence(report, source_path="findings.json", source_report_sha256=None):
    """Build an evidence pack from an already-loaded canonical report.

    This is the shared adapter used by the CLI and the GitHub Action.  The
    optional digest is accepted so callers that already loaded a report do not
    need to serialize it a second time merely to calculate provenance.
    """

    if source_report_sha256 is None:
        source_report_sha256 = hashlib.sha256(
            json.dumps(report, sort_keys=True, indent=2).encode("utf-8")
        ).hexdigest()
    return _build_evidence(report, source_path, source_report_sha256)


def render_evidence_markdown(evidence):
    """Render an evidence pack using the canonical Markdown adapter."""

    return _markdown(evidence)


def _write_json(path, value):
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def _markdown(evidence):
    lines = [
        "# ImpactPrism Evidence Pack",
        "",
        "- Generator: " + evidence["generator"],
        "- Version: " + evidence["version"],
        "- Schema version: " + str(evidence["schema_version"]),
        "- Map version: " + evidence["map_version"],
        "- Legal source: " + evidence["legal_source"],
        "- Overall status: " + evidence["overall_status"],
        "- Timestamp: " + evidence["timestamp"],
        "- Source report: " + evidence["source_report"],
        "- Source report SHA-256: " + evidence["source_report_sha256"],
        "- Package: " + evidence["package_name"] + "@" + evidence["package_version"],
        "",
        "## Findings",
        "",
    ]
    if not evidence["findings"]:
        lines.append(
            "No supported dependency findings were detected; this is not a compliance determination."
        )
    else:
        for finding in evidence["findings"]:
            lines.extend(
                [
                    "### " + finding["category"] + ": " + finding["name"],
                    "",
                    "Status: " + finding["status"],
                    "CRA clauses: " + ", ".join(finding["clauses"]),
                    "Rationale: " + finding["rationale"],
                    "",
                ]
            )
    lines.extend(
        [
            "## CRA references",
            "",
            "| Clause | Description |",
            "| --- | --- |",
        ]
    )
    for clause, description in CRA_REFERENCES.items():
        lines.append("| " + clause + " | " + description + " |")
    return "\n".join(lines) + "\n"


def _write_markdown(path, evidence):
    Path(path).write_text(_markdown(evidence), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a CRA clause-grounded evidence pack.")
    parser.add_argument("scan_report")
    parser.add_argument("--markdown", metavar="PATH", default="evidence.md")
    parser.add_argument("--json", metavar="PATH", default="evidence.json")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)

    source_path = Path(args.scan_report).resolve()
    if not source_path.is_file():
        print("error: scan report not found: " + str(source_path), file=sys.stderr)
        return 2

    try:
        report, source_report_sha256 = _load_json(source_path)
        evidence = build_evidence(report, source_path, source_report_sha256)
        markdown = render_evidence_markdown(evidence)
        if args.stdout:
            _write_markdown(args.markdown, evidence)
            json.dump(evidence, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            _write_markdown(args.markdown, evidence)
            _write_json(args.json, evidence)
    except Exception as error:
        print("error: " + str(error), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
