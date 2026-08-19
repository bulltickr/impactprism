import json
from pathlib import Path

from jsonschema import validate

from impactprism.evidence import _build_findings
from impactprism.analysis import generate_sbom
from impactprism.reporting import (
    build_scan_report,
    findings_from_report,
    scan_exit_code,
)


def _finding(finding_type, package, severity="medium"):
    return {
        "finding_type": finding_type,
        "finding_id": finding_type.lower() + "-id",
        "severity": severity,
        "confidence": "high",
        "ecosystem": "npm",
        "package": package,
        "file": "src/app.js",
        "line": 4,
        "explanation": "test finding",
    }


def test_canonical_report_preserves_every_finding_type_and_exit_policy():
    findings = [
        _finding("UNDECLARED_DIRECT_USE", "lodash"),
        _finding("DIRECT_DEPENDENCY_USED_TRANSITIVELY", "axios"),
        _finding("DECLARED_UNUSED_CANDIDATE", "react", "low"),
        _finding("LOCKFILE_MANIFEST_MISMATCH", "vite"),
        _finding("MISSING_LOCKFILE", "package.json"),
        _finding("SCOPE_MISMATCH", "jest", "low"),
        _finding("UNRESOLVED_IMPORT", "missing", "high"),
    ]

    report = build_scan_report(
        repo="repo",
        ecosystem="npm",
        findings=findings,
        package_name="demo",
        package_version="1.0.0",
        declared=["react", "jest"],
        imported=["lodash", "axios"],
    )

    assert len(report["findings"]) == len(findings)
    assert report["undeclared"] == ["axios", "lodash"]
    assert report["drift"] == ["react"]
    assert report["scope-mismatch"] == ["jest"]
    assert report["integrity"] == ["package.json", "vite"]
    assert report["unresolved"] == ["missing"]
    assert report["counts"]["total"] == len(findings)
    assert scan_exit_code(report) == 1


def test_evidence_adapter_includes_modern_finding_types():
    report = build_scan_report(
        repo="repo",
        ecosystem="npm",
        findings=[
            _finding("MISSING_LOCKFILE", "package.json"),
            _finding("SCOPE_MISMATCH", "jest", "low"),
            _finding("UNRESOLVED_IMPORT", "missing", "high"),
        ],
    )

    evidence = _build_findings(report)
    assert {item["finding_type"] for item in evidence} == {
        "MISSING_LOCKFILE",
        "SCOPE_MISMATCH",
        "UNRESOLVED_IMPORT",
    }
    assert all(item["clauses"] for item in evidence)
    assert all(item["status"] == "REVIEW_REQUIRED" for item in evidence)


def test_legacy_category_report_remains_readable():
    report = {"undeclared": ["lodash"], "drift": ["react"]}

    findings = findings_from_report(report)

    assert [item["finding_type"] for item in findings] == [
        "UNDECLARED_DIRECT_USE",
        "DECLARED_UNUSED_CANDIDATE",
    ]
    assert scan_exit_code(report) == 1


def test_scanner_error_is_not_a_clean_result():
    report = build_scan_report(
        repo="repo",
        ecosystem="npm",
        findings=[_finding("SCANNER_ERROR", None, "critical")],
    )

    assert scan_exit_code(report) == 2


def test_go_sbom_is_available_through_the_canonical_analysis_service(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\ngo 1.22\n\n"
        "require github.com/example/direct v1.2.3\n"
        "require github.com/example/indirect v2.0.0 // indirect\n",
        encoding="utf-8",
    )

    sbom = generate_sbom(str(tmp_path))

    assert sbom["specVersion"] == "1.6"
    components = {
        (item.get("group", "") + "/" if item.get("group") else "") + item["name"]: item
        for item in sbom["components"]
    }
    assert components["github.com/example/direct"]["version"] == "v1.2.3"
    assert components["github.com/example/indirect"]["version"] == "v2.0.0"


def test_canonical_report_matches_published_schema():
    report = build_scan_report(
        repo="repo",
        ecosystem="npm",
        findings=[_finding("UNDECLARED_DIRECT_USE", "lodash")],
    )
    schema_path = Path(__file__).parents[1] / "docs" / "schemas" / "scan-report.schema.json"
    validate(report, json.loads(schema_path.read_text(encoding="utf-8")))


def test_evidence_matches_published_schema(tmp_path):
    from impactprism.evidence import build_evidence

    report = build_scan_report(
        repo="repo",
        ecosystem="npm",
        findings=[_finding("UNDECLARED_DIRECT_USE", "lodash")],
    )
    evidence = build_evidence(report, source_path=tmp_path / "report.json", source_report_sha256="a" * 64)
    schema_path = Path(__file__).parents[1] / "docs" / "schemas" / "evidence-pack.schema.json"
    validate(evidence, json.loads(schema_path.read_text(encoding="utf-8")))
    assert evidence["output_schema_version"] == 1
    assert evidence["findings"][0]["finding_id"] == "undeclared_direct_use-id"
