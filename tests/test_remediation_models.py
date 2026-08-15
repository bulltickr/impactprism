import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from impactprism.remediation.models import (
    DependencyGraph,
    LockfilePlan,
    LockfilePlanResult,
    PatchSpec,
    PatchTarget,
    PrDescription,
    PrProposal,
    RemediationError,
    RemediationPlan,
    VerificationResult,
)


def test_patch_target_values():
    assert PatchTarget.MANIFEST.value == "manifest"
    assert PatchTarget.LOCKFILE.value == "lockfile"
    assert PatchTarget.GO_SUM.value == "go.sum"


def test_models_as_dict_are_plain_and_nested(tmp_path):
    patch = PatchSpec(
        path=tmp_path / "package.json",
        target=PatchTarget.MANIFEST,
        before="{}\n",
        after='{"dependencies": {}}\n',
        package="pkg",
        version="1.0.0",
        kind="dependencies",
    )
    plan = LockfilePlan(command="npm", args=["install"], cwd=tmp_path, fallback_patch=patch)
    result = LockfilePlanResult(command="npm install", patched=True, applied=patch)
    graph = DependencyGraph(
        before={"a": "1"}, after={"a": "1", "b": "2"}, text_before="a", text_after="b", added=["b"]
    )
    verification = VerificationResult(
        resolved=True,
        finding_type="UNDECLARED_DIRECT_USE",
        package="pkg",
        scan_before={"count": 1},
        scan_after={"count": 0},
    )
    description = PrDescription(
        title="Remediate pkg",
        body="Add pkg",
        changed_files=["package.json"],
        test_commands=["pytest"],
        scan_result={"resolved": True},
    )
    proposal = PrProposal(branch_name="fix/pkg", commit_message="Add pkg", description=description)
    remediation = RemediationPlan(
        finding={"package": "pkg"},
        manifest_patch=patch,
        lockfile_plan=plan,
        verification=verification,
        pr_description=description,
        pr_proposal=proposal,
        proposed_only=False,
    )

    assert patch.as_dict()["path"] == str(tmp_path / "package.json")
    assert plan.as_dict()["fallback_patch"]["target"] == "manifest"
    assert result.as_dict()["applied"]["package"] == "pkg"
    assert graph.as_dict()["added"] == ["b"]
    assert verification.as_dict()["scan_after"] == {"count": 0}
    assert description.as_dict()["changed_files"] == ["package.json"]
    assert proposal.as_dict()["description"]["title"] == "Remediate pkg"
    assert remediation.proposed_only is True
    assert remediation.as_dict()["proposed_only"] is True


def test_remediation_error_raises():
    with pytest.raises(RemediationError, match="unsafe"):
        raise RemediationError("unsafe patch")
