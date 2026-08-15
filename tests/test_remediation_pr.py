import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from impactprism.remediation import pr as pr_module
from impactprism.remediation.models import (
    PatchSpec,
    PatchTarget,
    PrDescription,
    PrProposal,
    RemediationPlan,
    VerificationResult,
)

FINDING = {
    "finding_type": "UNDECLARED_DIRECT_USE",
    "package": "leftpad",
    "ecosystem": "npm",
    "severity": "high",
    "file": "src/index.js",
    "line": 1,
}

MANIFEST_PATCH = PatchSpec(
    path="package.json",
    target=PatchTarget.MANIFEST,
    after='{"dependencies": {"leftpad": "^1.0.0"}}',
    before="{}",
    package="leftpad",
    version="^1.0.0",
    kind="dependencies",
)

VERIFICATION = VerificationResult(
    resolved=True,
    finding_type="UNDECLARED_DIRECT_USE",
    package="leftpad",
    scan_before={},
    scan_after={"leftpad": "1.3.0"},
    remaining=[],
)


def make_plan(**overrides):
    fields = dict(
        finding=FINDING,
        manifest_patch=MANIFEST_PATCH,
        verification=VERIFICATION,
        proposed_only=True,
    )
    fields.update(overrides)
    return RemediationPlan(**fields)


def test_description_sections(tmp_path):
    description = pr_module.build_pr_description(make_plan())

    assert isinstance(description, PrDescription)
    assert description.title == "chore(deps): remediate UNDECLARED_DIRECT_USE for leftpad"
    assert "## Summary" in description.body
    assert "## Changed files" in description.body
    assert "## Before/After" in description.body
    assert "## Test commands" in description.body
    assert "## Scan result" in description.body
    assert "## Unresolved risks" in description.body
    assert "PR is a proposal only; no auto-merge. Human approval required." in description.body
    assert "leftpad@1.3.0" in description.body
    assert "npm test" in description.body
    assert "python -m pytest tests -q" in description.body
    assert "package.json" in description.body
    assert "src/index.js:1" in description.body
    assert description.changed_files == ["package.json"]
    assert "npm test" in description.test_commands
    assert description.scan_result["resolved"] is True
    assert description.scan_result["finding_type"] == "UNDECLARED_DIRECT_USE"
    assert "resolved: True" in description.body


def test_go_ecosystem_commands(tmp_path):
    plan = make_plan(finding=dict(FINDING, ecosystem="go"))
    description = pr_module.build_pr_description(plan)

    assert "go test ./..." in description.body
    assert "python -m pytest tests -q" in description.body
    assert "npm test" not in description.body


def test_unresolved_risks_include_note(tmp_path):
    plan = make_plan(
        verification=VerificationResult(
            resolved=False,
            finding_type="UNDECLARED_DIRECT_USE",
            package="leftpad",
            scan_before={"leftpad": "0.1.0"},
            scan_after={"leftpad": "0.1.0"},
            remaining=[dict(FINDING)],
        )
    )
    description = pr_module.build_pr_description(plan)

    assert any("leftpad" in risk for risk in description.unresolved_risks)
    assert any(
        "PR is a proposal only; no auto-merge. Human approval required."
        in risk
        for risk in description.unresolved_risks
    )


def test_create_pr_proposal_never_invokes_subprocess(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("subprocess must never be invoked")

    monkeypatch.setattr(subprocess, "run", fail)

    proposal = pr_module.create_pr_proposal(str(tmp_path), make_plan())

    assert isinstance(proposal, PrProposal)
    assert isinstance(proposal.description, PrDescription)
    assert proposal.branch_name == "remediation/undeclared-direct-use/leftpad"
    assert proposal.commit_message == "remediation/undeclared-direct-use/leftpad: add leftpad to manifest"
    assert proposal.description.body


def test_create_pr_proposal_custom_branch(tmp_path):
    proposal = pr_module.create_pr_proposal(
        str(tmp_path), make_plan(), branch_name="custom/fix-leftpad"
    )

    assert proposal.branch_name == "custom/fix-leftpad"
    assert proposal.commit_message == "custom/fix-leftpad: add leftpad to manifest"


def test_branch_name_sanitized(tmp_path):
    plan = make_plan(
        finding=dict(FINDING, package="@scope/left pad"),
        manifest_patch=PatchSpec(
            path="package.json",
            target=PatchTarget.MANIFEST,
            after="{}",
            before="{}",
            package="@scope/left pad",
            version="1.0.0",
            kind="dependencies",
        ),
    )
    proposal = pr_module.create_pr_proposal(str(tmp_path), plan)

    assert proposal.branch_name == "remediation/undeclared-direct-use/scope-left-pad"
