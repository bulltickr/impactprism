"""ImpactPrism GitHub Action orchestrator.

Single-file runner for the reusable ImpactPrism action. Reads the inputs that
the composite action exposes as ``INPUT_*`` environment variables, runs the
dependency-drift analysis, applies the fail-on policy, and writes findings.json,
bom.json, impactprism.sarif, evidence.json, evidence.md and summary.md into the
configured output directory.

Fully offline: no network requests, no hosted account, no API keys. Only the
generated reports are ever uploaded; source file contents are never embedded.
"""

from __future__ import annotations

import json
import hashlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from impactprism import __version__

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

_SARIF_LEVELS = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}


class Outcome(str, Enum):
    CLEAN = "clean"
    FINDING = "finding"
    POLICY_FAILURE = "policy-failure"
    UNSUPPORTED_ECOSYSTEM = "unsupported-ecosystem"
    SCANNER_ERROR = "scanner-error"


@dataclass
class Policy:
    fail_on: str = "finding"
    severity_threshold: str = "low"


def _normalize_severity(value):
    severity = str(value).lower() if value is not None else "info"
    if severity not in SEVERITY_ORDER:
        return "info"
    return severity


def _normalize_threshold(value):
    threshold = str(value).lower() if value is not None else "low"
    if threshold not in SEVERITY_ORDER:
        return "low"
    return threshold


def classify_outcome(findings, error_kind="none", policy=None):
    """Classify the overall action outcome from findings and error state."""
    policy = policy if policy is not None else Policy()
    if error_kind == "scanner_error":
        return Outcome.SCANNER_ERROR
    if error_kind == "unsupported":
        return Outcome.UNSUPPORTED_ECOSYSTEM
    threshold = _normalize_threshold(policy.severity_threshold)
    threshold_rank = SEVERITY_ORDER[threshold]
    for finding in findings or []:
        if SEVERITY_ORDER[_normalize_severity(finding.get("severity"))] >= threshold_rank:
            return Outcome.POLICY_FAILURE
    if findings:
        return Outcome.FINDING
    return Outcome.CLEAN


def exit_code(outcome, policy):
    """Map an outcome to a process exit code under the given policy."""
    policy = policy if policy is not None else Policy()
    if outcome in (Outcome.CLEAN, Outcome.FINDING):
        return 0
    if outcome == Outcome.POLICY_FAILURE:
        return 0 if policy.fail_on == "never" else 1
    if outcome == Outcome.UNSUPPORTED_ECOSYSTEM:
        return 1 if policy.fail_on == "all" else 0
    if outcome == Outcome.SCANNER_ERROR:
        return 0 if policy.fail_on == "never" else 1
    return 0


def _env(name, default):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_import_paths():
    root = Path(__file__).resolve().parents[1]
    existing = {os.path.normcase(str(Path(entry).resolve())) for entry in sys.path}
    for candidate in (root, root / "src"):
        if not candidate.is_dir():
            continue
        value = str(candidate.resolve())
        if os.path.normcase(value) not in existing:
            sys.path.insert(0, value)


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _resolve_repo_path():
    raw = _env("INPUT_REPO_PATH", None) or _env("GITHUB_WORKSPACE", None)
    if not raw:
        raw = os.getcwd()
    return Path(raw).resolve()


def _read_policy():
    return Policy(
        fail_on=_env("INPUT_FAIL_ON", "finding"),
        severity_threshold=_env("INPUT_SEVERITY_THRESHOLD", "low"),
    )


def _resolve_ecosystem(repo_path, ecosystem):
    if ecosystem == "auto":
        if (repo_path / "package.json").is_file():
            return "npm"
        if (repo_path / "go.mod").is_file():
            return "go"
        _ensure_import_paths()
        from impactprism.python_manifest import is_python_repo

        if is_python_repo(repo_path):
            return "python"
        return None
    if ecosystem not in ("npm", "python", "go"):
        return None
    if ecosystem == "npm" and not (repo_path / "package.json").is_file():
        return None
    if ecosystem == "go" and not (repo_path / "go.mod").is_file():
        return None
    if ecosystem == "python":
        _ensure_import_paths()
        from impactprism.python_manifest import is_python_repo

        if not is_python_repo(repo_path):
            return None
    return ecosystem


def _run_analysis(repo_path, ecosystem, commit_sha):
    _ensure_import_paths()
    from impactprism.drift import analyze_repo

    report = analyze_repo(str(repo_path), ecosystem=ecosystem, commit_sha=commit_sha)
    return report.as_dicts()


def _build_sbom(repo_path, ecosystem):
    """Use the package's canonical SBOM service for Action output."""

    _ensure_import_paths()
    from impactprism.analysis import generate_sbom

    if ecosystem not in ("npm", "python", "go"):
        raise ValueError("unsupported ecosystem for bom: " + str(ecosystem))
    return generate_sbom(str(repo_path))


def _relative_file(repo_path, file_path):
    if not file_path:
        return None
    path = Path(file_path)
    if repo_path is not None:
        try:
            return path.resolve().relative_to(repo_path.resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return path.name or None


def _build_sarif(repo_path, findings, outcome, commit_sha, ecosystem, repository):
    driver = {"name": "ImpactPrism", "rules": []}
    if repository:
        driver["informationUri"] = "https://github.com/" + repository
    if findings:
        worst_by_type = {}
        for finding in findings:
            finding_type = finding.get("finding_type") or "UNKNOWN"
            severity = _normalize_severity(finding.get("severity"))
            if (
                worst_by_type.get(finding_type) is None
                or SEVERITY_ORDER[severity] > SEVERITY_ORDER[worst_by_type[finding_type]]
            ):
                worst_by_type[finding_type] = severity
        for finding_type in sorted(worst_by_type):
            driver["rules"].append(
                {
                    "id": finding_type,
                    "shortDescription": {"text": finding_type.replace("_", " ").lower()},
                    "defaultConfiguration": {"level": _SARIF_LEVELS[worst_by_type[finding_type]]},
                }
            )
    results = []
    for finding in findings:
        result = {
            "ruleId": finding.get("finding_type") or "UNKNOWN",
            "level": _SARIF_LEVELS[_normalize_severity(finding.get("severity"))],
            "message": {"text": finding.get("explanation") or ""},
            "properties": {"outcome": outcome, "commit_sha": commit_sha or ""},
        }
        relative = _relative_file(repo_path, finding.get("file"))
        if relative is not None:
            physical_location = {"artifactLocation": {"uri": relative}}
            region = {}
            line = finding.get("line")
            column = finding.get("column")
            if line is not None:
                region["startLine"] = line
            if column is not None:
                region["startColumn"] = column
            if region:
                physical_location["region"] = region
            result["locations"] = [{"physicalLocation": physical_location}]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": driver},
                "results": results,
                "properties": {
                    "outcome": outcome,
                    "commit_sha": commit_sha or "",
                    "ecosystem": ecosystem or "",
                },
            }
        ],
    }


def _package_identity(repo_path, ecosystem):
    _ensure_import_paths()
    try:
        if ecosystem == "npm":
            from impactprism.manifest import parse_manifest

            manifest = parse_manifest(str(repo_path))
            return manifest.name or "unknown", manifest.version or "unknown"
        if ecosystem == "go":
            from impactprism.go_manifest import parse_go_manifest

            manifest = parse_go_manifest(str(repo_path))
            return manifest.module_path or "unknown", ""
        if ecosystem == "python":
            from impactprism.python_manifest import parse_python_manifest

            manifest = parse_python_manifest(str(repo_path))
            return manifest.name or "unknown", manifest.version or "unknown"
    except Exception:
        pass
    return "unknown", "unknown"


def _build_evidence(
    repo_path,
    findings,
    package_name,
    package_version,
    commit_sha,
    source_report_sha256=None,
):
    _ensure_import_paths()
    import impactprism.evidence as evidence_module
    report = {
        "schema_version": 1,
        "generator": "impactprism-action",
        "repo": str(repo_path),
        "commit_sha": commit_sha,
        "package_name": package_name,
        "package_version": package_version,
        "findings": findings,
    }
    evidence = evidence_module.build_evidence(
        report,
        source_path="findings.json",
        source_report_sha256=source_report_sha256,
    )
    evidence["repo"] = str(repo_path)
    evidence["commit_sha"] = commit_sha
    return evidence


def _evidence_markdown(evidence):
    if "schema_version" in evidence and "legal_source" in evidence:
        _ensure_import_paths()
        import impactprism.evidence as evidence_module

        return evidence_module.render_evidence_markdown(evidence)
    lines = [
        "# ImpactPrism Evidence Pack",
        "",
        "- Generator: " + evidence["generator"],
        "- Version: " + evidence["version"],
        "- Timestamp: " + evidence["timestamp"],
        "- Source report: " + evidence["source_report"],
        "- Repo: " + str(evidence.get("repo") or ""),
        "- Commit: " + str(evidence.get("commit_sha") or ""),
        "- Package: " + evidence["package_name"] + "@" + evidence["package_version"],
        "",
        "## Findings",
        "",
    ]
    if not evidence["findings"]:
        lines.append(
            "No supported dependency findings were detected; this is not a compliance determination."
        )
        lines.append("")
    else:
        for finding in evidence["findings"]:
            lines.extend(
                [
                    "## " + finding["finding_type"] + ": " + str(finding.get("package") or ""),
                    "",
                    "CRA clauses: " + ", ".join(finding.get("clauses") or []),
                    "Rationale: " + (finding.get("rationale") or ""),
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
    for clause, description in (evidence.get("cra_references") or {}).items():
        lines.append("| " + clause + " | " + description + " |")
    return "\n".join(lines) + "\n"


def _counts(findings):
    by_severity = {}
    by_type = {}
    for finding in findings:
        severity = _normalize_severity(finding.get("severity"))
        finding_type = finding.get("finding_type") or "UNKNOWN"
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_type[finding_type] = by_type.get(finding_type, 0) + 1
    return {"total": len(findings), "by_severity": by_severity, "by_type": by_type}


def _short_sha(commit_sha):
    if not commit_sha:
        return "none"
    return commit_sha[:7] if len(commit_sha) > 7 else commit_sha


def _file_line(repo_path, finding):
    relative = _relative_file(repo_path, finding.get("file"))
    if relative is None:
        return "-"
    line = finding.get("line")
    if line is not None:
        return relative + ":" + str(line)
    return relative


def _sorted_findings(findings):
    return sorted(
        findings,
        key=lambda finding: (
            -SEVERITY_ORDER[_normalize_severity(finding.get("severity"))],
            finding.get("finding_type") or "",
            finding.get("package") or "",
            finding.get("file") or "",
        ),
    )


def _explanation(outcome, policy):
    if outcome == Outcome.CLEAN:
        return "No findings were produced, so the step succeeds (exit 0)."
    if outcome == Outcome.FINDING:
        return (
            "Findings were produced but none reach the severity threshold, "
            "so the step succeeds (exit 0)."
        )
    if outcome == Outcome.POLICY_FAILURE:
        if policy.fail_on == "never":
            return (
                'Findings reach the severity threshold but fail-on is "never", '
                "so the step succeeds (exit 0)."
            )
        return (
            'Findings reach the severity threshold and fail-on is "' + policy.fail_on + '", '
            "so the step fails (exit 1)."
        )
    if outcome == Outcome.UNSUPPORTED_ECOSYSTEM:
        if policy.fail_on == "all":
            return (
                'No supported ecosystem was detected and fail-on is "all", '
                "so the step fails (exit 1)."
            )
        return (
            'No supported ecosystem was detected and fail-on is "' + policy.fail_on + '", '
            "so the step succeeds (exit 0)."
        )
    if outcome == Outcome.SCANNER_ERROR:
        if policy.fail_on == "never":
            return (
                'The scanner errored but fail-on is "never", '
                "so the step succeeds (exit 0)."
            )
        return (
            'The scanner errored and fail-on is "' + policy.fail_on + '", '
            "so the step fails (exit 1)."
        )
    return ""


def _build_summary(
    policy,
    outcome,
    ecosystem,
    commit_sha,
    findings,
    error_message,
    code,
    counts,
    output_dir,
    artifact_name,
    repo_path,
):
    lines = [
        "## ImpactPrism outcome: " + outcome,
        "",
        "- Fail-on: " + policy.fail_on,
        "- Severity threshold: " + policy.severity_threshold,
        "- Ecosystem: " + str(ecosystem or "none"),
        "- Commit: " + _short_sha(commit_sha),
        "- Findings: " + str(counts["total"]),
        "- Exit code: " + str(code),
        "",
        "### Counts by severity",
        "",
        "| Severity | Count |",
        "| --- | --- |",
    ]
    for severity in sorted(SEVERITY_ORDER):
        lines.append("| " + severity + " | " + str(counts["by_severity"].get(severity, 0)) + " |")
    lines.extend(
        [
            "",
            "### Counts by type",
            "",
            "| Finding type | Count |",
            "| --- | --- |",
        ]
    )
    for finding_type in sorted(counts["by_type"]):
        lines.append("| " + finding_type + " | " + str(counts["by_type"][finding_type]) + " |")
    lines.extend(
        [
            "",
            "### Top findings",
            "",
            "| finding_type | package | severity | file:line |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in _sorted_findings(findings)[:25]:
        lines.append(
            "| " + str(finding.get("finding_type") or "")
            + " | " + str(finding.get("package") or "")
            + " | " + str(finding.get("severity") or "")
            + " | " + _file_line(repo_path, finding) + " |"
        )
    if error_message:
        lines.extend(["", "> Scanner detail: " + error_message])
    lines.extend(["", _explanation(outcome, policy), "", "### Artifacts", ""])
    for path in sorted(output_dir.iterdir()):
        lines.append("- " + str(path.resolve()))
    if artifact_name:
        lines.append("")
        lines.append("Uploaded as artifact: " + artifact_name)
    lines.extend(
        [
            "",
            "No hosted ImpactPrism account or API key is used; only generated "
            "reports are uploaded (never source).",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_github_output(outputs):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for name, value in outputs.items():
            handle.write(name + "=" + str(value) + "\n")


def _append_step_summary(markdown):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(markdown)


def _resolve_output_dir(workspace):
    workspace = workspace.resolve()
    raw_output_dir = _env("INPUT_OUTPUT_DIR", "impactprism-reports")
    if "\x00" in raw_output_dir:
        print(
            "warning: INPUT_OUTPUT_DIR contains a NUL byte; using "
            "impactprism-reports instead",
            file=sys.stderr,
        )
        return workspace / "impactprism-reports"
    candidate = (workspace / raw_output_dir).resolve()
    if not candidate.is_relative_to(workspace):
        print(
            "warning: INPUT_OUTPUT_DIR resolves outside the workspace; using "
            "impactprism-reports instead",
            file=sys.stderr,
        )
        return workspace / "impactprism-reports"
    return candidate


def main(argv=None) -> int:
    policy = _read_policy()
    ecosystem_input = _env("INPUT_ECOSYSTEM", "auto")
    # An explicitly empty artifact name disables upload; preserve that value
    # instead of treating it as an omitted input.
    artifact_name = os.environ.get("INPUT_ARTIFACT_NAME", "impactprism-reports")
    repo_path = _resolve_repo_path()
    commit_sha = os.environ.get("GITHUB_SHA") or None
    workspace = Path(_env("GITHUB_WORKSPACE", ".")).resolve()
    output_dir = _resolve_output_dir(workspace)
    output_dir.mkdir(parents=True, exist_ok=True)

    error_kind = "none"
    error_message = None
    findings = []
    resolved_ecosystem = None

    if not repo_path.is_dir():
        error_kind = "scanner_error"
        error_message = "repository directory not found: " + str(repo_path)
    else:
        resolved_ecosystem = _resolve_ecosystem(repo_path, ecosystem_input)
        if resolved_ecosystem is None:
            error_kind = "unsupported"
            error_message = "unsupported or missing ecosystem"
        else:
            try:
                findings = _run_analysis(repo_path, resolved_ecosystem, commit_sha)
            except ValueError as exc:
                if "unsupported" in str(exc).lower():
                    error_kind = "unsupported"
                else:
                    error_kind = "scanner_error"
                error_message = str(exc)
            except Exception as exc:
                error_kind = "scanner_error"
                error_message = str(exc)

    outcome = classify_outcome(findings, error_kind, policy)
    code = exit_code(outcome, policy)

    bom_path_str = ""
    bom_validated = True
    if error_kind == "none" and resolved_ecosystem is not None:
        try:
            bom = _build_sbom(repo_path, resolved_ecosystem)
            bom_path = output_dir / "bom.json"
            _write_json(bom_path, bom)
            bom_path_str = str(bom_path.resolve())
        except Exception:
            bom_path_str = ""

    counts = _counts(findings)
    findings_path = output_dir / "findings.json"
    _write_json(
        findings_path,
        {
            "schema_version": 1,
            "generator": "impactprism-action",
            "version": __version__,
            "timestamp": _utc_timestamp(),
            "repo": str(repo_path),
            "commit_sha": commit_sha,
            "ecosystem": resolved_ecosystem,
            "outcome": outcome.value,
            "policy": {"fail_on": policy.fail_on, "severity_threshold": policy.severity_threshold},
            "counts": counts,
            "findings": findings,
            "error": (
                None if error_kind == "none" else {"kind": error_kind, "message": error_message or ""}
            ),
            "bom_validated": bom_validated,
        },
    )

    repository = os.environ.get("GITHUB_REPOSITORY") or None
    sarif_path = output_dir / "impactprism.sarif"
    _write_json(
        sarif_path,
        _build_sarif(repo_path, findings, outcome.value, commit_sha, resolved_ecosystem, repository),
    )

    package_name, package_version = _package_identity(repo_path, resolved_ecosystem)
    source_report_sha256 = hashlib.sha256(findings_path.read_bytes()).hexdigest()
    evidence = _build_evidence(
        repo_path,
        findings,
        package_name,
        package_version,
        commit_sha,
        source_report_sha256=source_report_sha256,
    )
    evidence_path = output_dir / "evidence.json"
    _write_json(evidence_path, evidence)
    (output_dir / "evidence.md").write_text(_evidence_markdown(evidence), encoding="utf-8")

    summary_markdown = _build_summary(
        policy,
        outcome.value,
        resolved_ecosystem,
        commit_sha,
        findings,
        error_message,
        code,
        counts,
        output_dir,
        artifact_name,
        repo_path,
    )
    (output_dir / "summary.md").write_text(summary_markdown, encoding="utf-8")
    _append_step_summary(summary_markdown)

    _write_github_output(
        {
            "outcome": outcome.value,
            "findings-path": str(findings_path.resolve()),
            "bom-path": bom_path_str,
            "sarif-path": str(sarif_path.resolve()),
            "evidence-path": str(evidence_path.resolve()),
            "exit-code": str(code),
        }
    )

    print(
        "impactprism-action: outcome=" + outcome.value
        + " exit=" + str(code)
        + " findings=" + str(len(findings))
        + " error=" + str(error_kind)
        + " reports=" + str(output_dir)
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
