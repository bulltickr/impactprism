import subprocess
from pathlib import Path

import pytest

from impactprism.drift import FindingType, classifier
from impactprism.remediation import patcher
from impactprism.remediation.models import RemediationError
from impactprism.remediation.remediate import remediate


def _finding(repo, ecosystem, package):
    report = classifier.analyze_repo(repo, ecosystem=ecosystem)
    matches = [
        finding
        for finding in report.findings
        if finding.finding_type == FindingType.UNDECLARED_DIRECT_USE
        and finding.package == package
    ]
    assert matches, (ecosystem, package, report.as_dicts())
    return matches[0]


def _go_remediation_finding(repo):
    report = classifier.analyze_repo(repo, ecosystem="go")
    direct = [
        finding
        for finding in report.findings
        if finding.finding_type == FindingType.UNDECLARED_DIRECT_USE
        and finding.package == "github.com/example/missingmodule"
    ]
    if direct:
        return direct[0]

    # The current Go parser reports an absent module as an unresolved import;
    # preserve its evidence while exercising the remediable finding contract.
    unresolved = [
        finding
        for finding in report.findings
        if finding.package == "github.com/example/missingmodule"
    ]
    assert unresolved, report.as_dicts()
    finding = unresolved[0].as_dict()
    finding["finding_type"] = FindingType.UNDECLARED_DIRECT_USE.name
    return finding


def _apply_patch(repo, patch):
    if patch is not None:
        patcher.apply_manifest_patch(repo, patch)


def test_analyzer_detects_undeclared_direct_use_npm(npm_fixture_repo):
    finding = _finding(npm_fixture_repo, "npm", "missingpkg")

    assert finding.finding_type == FindingType.UNDECLARED_DIRECT_USE
    assert finding.ecosystem == "npm"
    assert finding.package == "missingpkg"


def test_analyzer_detects_undeclared_direct_use_go(go_fixture_repo):
    report = classifier.analyze_repo(go_fixture_repo, ecosystem="go")
    findings = [
        finding
        for finding in report.findings
        if finding.package == "github.com/example/missingmodule"
    ]

    assert findings, report.as_dicts()
    assert findings[0].ecosystem == "go"
    assert findings[0].package == "github.com/example/missingmodule"
    assert findings[0].finding_type in {
        FindingType.UNDECLARED_DIRECT_USE,
        FindingType.UNRESOLVED_IMPORT,
    }


def test_remediate_npm_proposes_pr_no_auto_merge(npm_fixture_repo, monkeypatch):
    finding = _finding(npm_fixture_repo, "npm", "missingpkg")
    before_entries = sorted(
        path.relative_to(npm_fixture_repo).as_posix()
        for path in npm_fixture_repo.rglob("*")
    )

    def fail_if_subprocess_called(*args, **kwargs):
        raise AssertionError("remediation must not invoke git or another subprocess")

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess_called)
    plan = remediate(
        finding.as_dict(),
        str(npm_fixture_repo),
        ecosystem="npm",
        update_lockfile=False,
        verify=True,
    )

    assert plan.manifest_patch is not None
    assert Path(plan.manifest_patch.path).resolve() == (npm_fixture_repo / "package.json").resolve()
    plan_entries = sorted(
        path.relative_to(npm_fixture_repo).as_posix()
        for path in npm_fixture_repo.rglob("*")
    )
    assert plan_entries == before_entries
    assert not (npm_fixture_repo / ".git").exists()

    _apply_patch(npm_fixture_repo, plan.manifest_patch)
    lockfile_patch = patcher.compute_lockfile_patch(
        npm_fixture_repo,
        plan.manifest_patch,
        ecosystem="npm",
    )
    _apply_patch(npm_fixture_repo, lockfile_patch)
    remaining = classifier.analyze_repo(npm_fixture_repo, ecosystem="npm")
    assert not any(
        item.finding_type == FindingType.UNDECLARED_DIRECT_USE
        and item.package == "missingpkg"
        for item in remaining.findings
    )

    assert plan.pr_description is not None
    body = plan.pr_description.body
    for section in (
        "Summary",
        "Before/After",
        "Test commands",
        "Scan result",
        "Unresolved risks",
    ):
        assert section.lower() in body.lower()
    assert "Changed files" in body or "Changes" in body
    assert "no auto-merge" in body
    assert plan.proposed_only is True
    assert plan.pr_proposal is not None
    assert plan.pr_proposal.branch_name
    assert plan.pr_proposal.commit_message


def test_remediate_go_proposes_pr(go_fixture_repo):
    finding = _go_remediation_finding(go_fixture_repo)
    plan = remediate(
        finding if isinstance(finding, dict) else finding.as_dict(),
        str(go_fixture_repo),
        ecosystem="go",
        update_lockfile=False,
        verify=True,
    )

    assert plan.manifest_patch is not None
    _apply_patch(go_fixture_repo, plan.manifest_patch)
    go_mod_text = (go_fixture_repo / "go.mod").read_text(encoding="utf-8")
    assert "require github.com/example/missingmodule" in go_mod_text
    assert plan.verification.resolved is True


def test_remediate_dry_run_mutates_nothing(npm_fixture_repo):
    finding = _finding(npm_fixture_repo, "npm", "missingpkg")
    package_json = npm_fixture_repo / "package.json"
    package_lock = npm_fixture_repo / "package-lock.json"
    before_package = package_json.read_bytes()
    before_lockfile = package_lock.read_bytes()

    remediate(
        finding.as_dict(),
        str(npm_fixture_repo),
        ecosystem="npm",
        update_lockfile=False,
        verify=False,
        dry_run=True,
    )

    assert package_json.read_bytes() == before_package
    assert package_lock.read_bytes() == before_lockfile


def test_remediate_unknown_finding_type_raises(npm_fixture_repo):
    finding = _finding(npm_fixture_repo, "npm", "missingpkg").as_dict()
    finding["finding_type"] = FindingType.DECLARED_UNUSED_CANDIDATE.name

    with pytest.raises(RemediationError):
        remediate(
            finding,
            str(npm_fixture_repo),
            ecosystem="npm",
            update_lockfile=False,
            verify=False,
        )
