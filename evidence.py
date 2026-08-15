import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


CLAUSE_MAP = {
    "undeclared": ["Art 13(1)(b)", "Art 14(1)", "Annex I Part II", "Annex VII"],
    "drift": ["Art 13(1)(a)", "Annex I Part I"],
}
RATIONALES = {
    "undeclared": (
        "Undeclared dependencies fall outside the SBOM/component transparency "
        "required by Art 13(1)(b) and evade the vulnerability-handling "
        "obligations of Art 14(1)/Annex VII."
    ),
    "drift": (
        "Unnecessary installed components expand the attack surface contrary "
        "to the secure-by-default and minimisation requirements."
    ),
}
CRA_REFERENCES = {
    "Art 13(1)(a)": "Secure-by-default products should minimise unnecessary components and attack surface.",
    "Art 13(1)(b)": "Products should provide transparency about included software components.",
    "Art 14(1)": "Manufacturers must address and remediate product vulnerabilities.",
    "Annex I Part I": "Essential cybersecurity requirements cover secure configuration and minimisation.",
    "Annex I Part II": "The technical documentation and component information must support transparency.",
    "Annex VII": "The vulnerability-handling process requires relevant component and vulnerability information.",
}


def _load_json(path):
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError as error:
        raise ValueError("unable to read scan report: " + str(error))
    except json.JSONDecodeError as error:
        raise ValueError("invalid JSON in scan report: " + str(error))
    if not isinstance(value, dict):
        raise ValueError("scan report must contain a JSON object")
    return value


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


def _build_findings(report):
    findings = []
    for category in ("undeclared", "drift"):
        for name in _report_entries(report, category):
            findings.append(
                {
                    "category": category,
                    "name": name,
                    "clauses": CLAUSE_MAP[category],
                    "rationale": RATIONALES[category],
                }
            )
    return findings


def _build_evidence(report, source_path):
    findings = _build_findings(report)
    undeclared_count = sum(1 for finding in findings if finding["category"] == "undeclared")
    drift_count = sum(1 for finding in findings if finding["category"] == "drift")
    return {
        "generator": "impactprism-evidence",
        "version": "0.1.0",
        "timestamp": _utc_timestamp(),
        "source_report": str(source_path),
        "package_name": _package_name(report),
        "package_version": _package_version(report),
        "clause_map": CLAUSE_MAP,
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "undeclared_count": undeclared_count,
            "drift_count": drift_count,
            "clean": not findings,
        },
    }


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
        "- Timestamp: " + evidence["timestamp"],
        "- Source report: " + evidence["source_report"],
        "- Package: " + evidence["package_name"] + "@" + evidence["package_version"],
        "",
        "## Findings",
        "",
    ]
    if not evidence["findings"]:
        lines.append("No findings; evidence of compliant dependency management.")
    else:
        for finding in evidence["findings"]:
            lines.extend(
                [
                    "### " + finding["category"] + ": " + finding["name"],
                    "",
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
        report = _load_json(source_path)
        evidence = _build_evidence(report, source_path)
        markdown = _markdown(evidence)
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
