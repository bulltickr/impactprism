import json
import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from impactprism.manifest import parse_manifest
from impactprism.remediation.patcher import (
    apply_manifest_patch,
    build_manifest_patch,
    compute_lockfile_patch,
)
from impactprism.remediation.verify import verify_remediation

FINDING = {
    "finding_type": "UNDECLARED_DIRECT_USE",
    "package": "leftpad",
    "ecosystem": "npm",
    "severity": "high",
}


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_npm_repo(tmp_path):
    repo = tmp_path / "npm-repo"
    write_file(
        repo,
        "package.json",
        json.dumps({"name": "demo", "version": "1.0.0"}, indent=2),
    )
    write_file(
        repo,
        "src/index.js",
        'import leftpad from "leftpad";\n\nexport default leftpad;\n',
    )
    write_file(
        repo,
        "package-lock.json",
        json.dumps(
            {
                "name": "demo",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "packages": {"": {"name": "demo", "version": "1.0.0"}},
            },
            indent=2,
        ),
    )
    return repo


def test_unresolved_before_fix(tmp_path):
    repo = make_npm_repo(tmp_path)
    result = verify_remediation(str(repo), FINDING, ecosystem="npm")

    assert result.resolved is False
    assert result.finding_type == "UNDECLARED_DIRECT_USE"
    assert result.package == "leftpad"
    assert any(item.get("package") == "leftpad" for item in result.remaining)


def test_resolved_after_manifest_and_lockfile_patch(tmp_path):
    repo = make_npm_repo(tmp_path)
    manifest = parse_manifest(str(repo))
    patch = build_manifest_patch(FINDING, manifest)
    assert patch is not None

    apply_manifest_patch(str(repo), patch)

    lock_patch = compute_lockfile_patch(str(repo), patch, ecosystem="npm")
    assert lock_patch is not None
    Path(lock_patch.path).write_text(lock_patch.after, encoding="utf-8")

    result = verify_remediation(str(repo), FINDING, ecosystem="npm")

    assert result.resolved is True
    assert result.remaining == []


def test_provided_scan_before_is_preserved(tmp_path):
    repo = make_npm_repo(tmp_path)
    result = verify_remediation(str(repo), FINDING, ecosystem="npm")
    before = result.scan_before

    second = verify_remediation(str(repo), FINDING, ecosystem="npm", scan_before=before)

    assert second.scan_before is before
    assert second.resolved is False
