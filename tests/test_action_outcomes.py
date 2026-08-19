import json
import sys
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from action.run import (
    Outcome,
    Policy,
    SEVERITY_ORDER,
    _evidence_markdown,
    classify_outcome,
    exit_code,
    main,
    _build_sbom,
    _package_identity,
    _resolve_ecosystem,
)


FAIL_ON_VALUES = ("never", "finding", "all")


def test_outcome_members_and_values():
    assert SEVERITY_ORDER == {
        "info": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }
    assert Outcome.CLEAN.value == "clean"
    assert Outcome.FINDING.value == "finding"
    assert Outcome.POLICY_FAILURE.value == "policy-failure"
    assert Outcome.UNSUPPORTED_ECOSYSTEM.value == "unsupported-ecosystem"
    assert Outcome.SCANNER_ERROR.value == "scanner-error"


def test_clean_empty_findings():
    assert classify_outcome([], policy=Policy()) is Outcome.CLEAN


def test_action_supports_python_ecosystem_and_artifacts(tmp_path):
    repo = tmp_path / "python-app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "python-app"\nversion = "1.0.0"\ndependencies = ["requests==2.31.0"]\n',
        encoding="utf-8",
    )
    (repo / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (repo / "app.py").write_text("import requests\n", encoding="utf-8")

    assert _resolve_ecosystem(repo, "auto") == "python"
    assert _resolve_ecosystem(repo, "python") == "python"
    assert _package_identity(repo, "python") == ("python-app", "1.0.0")
    assert _build_sbom(repo, "python")["specVersion"] == "1.6"


def test_clean_evidence_markdown_does_not_claim_compliance():
    markdown = _evidence_markdown(
        {
            "generator": "impactprism-evidence",
            "version": "0.1.0",
            "timestamp": "2026-01-01T00:00:00Z",
            "source_report": "findings.json",
            "repo": "repo",
            "commit_sha": "abc123",
            "package_name": "demo",
            "package_version": "1.0.0",
            "findings": [],
        }
    )

    assert "No supported dependency findings were detected; this is not a compliance determination." in markdown
    assert "evidence of compliant dependency management" not in markdown


@pytest.mark.parametrize("fail_on", FAIL_ON_VALUES)
def test_clean_exit_code_is_zero_for_every_policy(fail_on):
    policy = Policy(fail_on=fail_on)
    outcome = classify_outcome([], policy=policy)

    assert outcome is Outcome.CLEAN
    assert exit_code(outcome, policy) == 0


@pytest.mark.parametrize(
    "findings",
    [
        [{"severity": "low"}],
        [{"severity": "medium"}, {"severity": "low"}],
    ],
)
@pytest.mark.parametrize("fail_on", FAIL_ON_VALUES)
def test_findings_below_threshold_do_not_fail_policy(findings, fail_on):
    policy = Policy(fail_on=fail_on, severity_threshold="high")
    outcome = classify_outcome(findings, policy=policy)

    assert outcome is Outcome.FINDING
    assert exit_code(outcome, policy) == 0


@pytest.mark.parametrize("severity", ["medium", "high"])
@pytest.mark.parametrize("fail_on", FAIL_ON_VALUES)
def test_findings_at_or_above_threshold_are_policy_failures(severity, fail_on):
    policy = Policy(fail_on=fail_on, severity_threshold="medium")
    outcome = classify_outcome([{"severity": severity}], policy=policy)

    assert outcome is Outcome.POLICY_FAILURE
    assert exit_code(outcome, policy) == (0 if fail_on == "never" else 1)


def test_threshold_boundary_counts_as_failure():
    policy = Policy(severity_threshold="high")

    assert classify_outcome([{"severity": "high"}], policy=policy) is Outcome.POLICY_FAILURE


@pytest.mark.parametrize("severity", ["info", "low", "medium", "high", "critical"])
def test_info_threshold_makes_any_finding_a_policy_failure(severity):
    policy = Policy(severity_threshold="info")

    assert classify_outcome([{"severity": severity}], policy=policy) is Outcome.POLICY_FAILURE


@pytest.mark.parametrize(
    ("finding", "expected"),
    [
        ({"severity": "HIGH"}, Outcome.POLICY_FAILURE),
        ({"severity": "high"}, Outcome.POLICY_FAILURE),
        ({}, Outcome.FINDING),
        ({"severity": "bogus"}, Outcome.FINDING),
    ],
)
def test_severity_is_normalized_and_invalid_values_default_to_info(finding, expected):
    policy = Policy(severity_threshold="high")

    assert classify_outcome([finding], policy=policy) is expected


@pytest.mark.parametrize("threshold", list(SEVERITY_ORDER))
def test_each_valid_severity_threshold_is_respected(threshold):
    policy = Policy(severity_threshold=threshold)

    assert classify_outcome([{"severity": threshold}], policy=policy) is Outcome.POLICY_FAILURE


@pytest.mark.parametrize("fail_on", FAIL_ON_VALUES)
@pytest.mark.parametrize("outcome", [Outcome.CLEAN, Outcome.FINDING])
def test_clean_and_finding_exit_zero(outcome, fail_on):
    assert exit_code(outcome, Policy(fail_on=fail_on)) == 0


@pytest.mark.parametrize("fail_on", FAIL_ON_VALUES)
def test_unsupported_ecosystem_takes_precedence_and_has_policy_exit(fail_on):
    policy = Policy(fail_on=fail_on)

    for findings in ([], [{"severity": "critical"}]):
        outcome = classify_outcome(findings, error_kind="unsupported", policy=policy)
        assert outcome is Outcome.UNSUPPORTED_ECOSYSTEM
        assert exit_code(outcome, policy) == (1 if fail_on == "all" else 0)


@pytest.mark.parametrize("fail_on", FAIL_ON_VALUES)
def test_scanner_error_takes_precedence_and_has_policy_exit(fail_on):
    policy = Policy(fail_on=fail_on)

    for findings in ([], [{"severity": "critical"}]):
        outcome = classify_outcome(findings, error_kind="scanner_error", policy=policy)
        assert outcome is Outcome.SCANNER_ERROR
        assert exit_code(outcome, policy) == 2


@pytest.mark.parametrize(
    ("error_kind", "expected"),
    [
        ("scanner_error", Outcome.SCANNER_ERROR),
        ("unsupported", Outcome.UNSUPPORTED_ECOSYSTEM),
    ],
)
def test_errors_precede_high_severity_findings(error_kind, expected):
    outcome = classify_outcome(
        [{"severity": "high"}], error_kind=error_kind, policy=Policy()
    )

    assert outcome is expected


def test_policy_defaults():
    assert Policy() == Policy(fail_on="finding", severity_threshold="low")


def _write_npm_repo_without_lockfile(repo):
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "1.0.0",
                "dependencies": {"some-lib": "^1.0.0"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "src").mkdir()
    (repo / "src" / "app.js").write_text(
        'import someLib from "some-lib";\nexport default someLib;\n', encoding="utf-8"
    )
    return repo


def test_missing_lockfile_action_policy_thresholds(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    repo = _write_npm_repo_without_lockfile(workspace / "repo")

    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("INPUT_REPO_PATH", str(repo))
    monkeypatch.setenv("INPUT_ECOSYSTEM", "npm")
    monkeypatch.setenv("INPUT_OUTPUT_DIR", "impactprism-reports")
    monkeypatch.setenv("INPUT_ARTIFACT_NAME", "")
    monkeypatch.setenv("INPUT_FAIL_ON", "finding")
    monkeypatch.setenv("INPUT_SEVERITY_THRESHOLD", "low")

    assert main() == 1
    data = json.loads(
        (workspace / "impactprism-reports" / "findings.json").read_text(encoding="utf-8")
    )
    assert data["outcome"] == "policy-failure"
    missing = [f for f in data["findings"] if f["finding_type"] == "MISSING_LOCKFILE"]
    assert len(missing) == 1
    assert missing[0]["severity"].lower() == "medium"
    summary = (workspace / "impactprism-reports" / "summary.md").read_text(encoding="utf-8")
    assert "Uploaded as artifact:" not in summary

    monkeypatch.setenv("INPUT_SEVERITY_THRESHOLD", "high")
    assert main() == 0
    data = json.loads(
        (workspace / "impactprism-reports" / "findings.json").read_text(encoding="utf-8")
    )
    assert data["outcome"] == "finding"
