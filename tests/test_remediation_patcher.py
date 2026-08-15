import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from impactprism.go_manifest import parse_go_manifest
from impactprism.manifest import parse_manifest
from impactprism.remediation.models import PatchSpec, PatchTarget, RemediationError
from impactprism.remediation.patcher import (
    apply_manifest_patch,
    build_manifest_patch,
    compute_lockfile_patch,
)


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, package=None, lockfile=None):
    repo = tmp_path / "repo"
    if package is not None:
        write_file(repo, "package.json", json.dumps(package, indent=2) + "\n")
    if lockfile is not None:
        write_file(repo, "package-lock.json", lockfile)
    return repo


def test_build_manifest_patch_filters_and_patches_npm(tmp_path):
    package = {"name": "demo", "version": "1.0.0", "dependencies": {"known": "^1.0.0"}}
    repo = make_repo(tmp_path, package)
    manifest = parse_manifest(repo)

    assert build_manifest_patch({"finding_type": "OTHER", "package": "new", "ecosystem": "npm"}, manifest) is None
    assert (
        build_manifest_patch(
            {"finding_type": "UNDECLARED_DIRECT_USE", "package": "known", "ecosystem": "npm"}, manifest
        )
        is None
    )
    finding = {"finding_type": "UNDECLARED_DIRECT_USE", "package": "new", "ecosystem": "npm", "file": "src/app.js"}
    patch = build_manifest_patch(finding, manifest)
    assert patch is not None
    assert patch.kind == "dependencies"
    assert json.loads(patch.after)["dependencies"]["new"] == "*"

    dev_patch = build_manifest_patch(finding, manifest, prefer_kind="devDependencies")
    assert dev_patch is not None
    assert dev_patch.kind == "devDependencies"
    assert "new" in json.loads(dev_patch.after)["devDependencies"]


def test_build_manifest_patch_go_appends_require_line(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo, "go.mod", "module example.com/demo\n\ngo 1.22\n")
    manifest = parse_go_manifest(repo)
    finding = {"finding_type": "UNDECLARED_DIRECT_USE", "package": "example.com/lib@v1.2.3", "ecosystem": "go"}

    patch = build_manifest_patch(finding, manifest)

    assert patch is not None
    assert patch.kind == "require"
    assert "require example.com/lib v1.2.3" in patch.after


def test_apply_manifest_patch_and_reject_escape(tmp_path):
    repo = make_repo(tmp_path, {"name": "demo"})
    path = repo / "package.json"
    patch = PatchSpec(path=path, target=PatchTarget.MANIFEST, before="", after="{\n}\n")

    assert apply_manifest_patch(repo, patch) == path.resolve()
    assert path.read_text(encoding="utf-8") == "{\n}\n"

    escaping = PatchSpec(path=repo / ".." / "outside.json", target=PatchTarget.MANIFEST, after="{}\n")
    with pytest.raises(RemediationError):
        apply_manifest_patch(repo, escaping)


def test_compute_npm_lockfile_patch(tmp_path):
    lock = {"lockfileVersion": 3, "packages": {"": {"name": "demo"}}, "dependencies": {"new": {"version": "0.1.0"}}}
    repo = make_repo(tmp_path, {"name": "demo"}, json.dumps(lock, indent=2) + "\n")
    manifest_patch = PatchSpec(
        path=repo / "package.json",
        target=PatchTarget.MANIFEST,
        after="{}\n",
        package="new",
        version="1.2.3",
    )

    patch = compute_lockfile_patch(repo, manifest_patch, ecosystem="npm")

    assert patch is not None
    data = json.loads(patch.after)
    assert data["packages"]["node_modules/new"]["version"] == "1.2.3"
    assert "new" not in data["dependencies"]


@pytest.mark.parametrize("lockfile", ["package-lock.json", "yarn.lock"])
def test_compute_lockfile_patch_uses_selected_authoritative_lockfile(tmp_path, lockfile):
    lock = {"lockfileVersion": 3, "packages": {"": {"name": "demo"}}}
    repo = make_repo(tmp_path, {"name": "demo"}, json.dumps(lock, indent=2) + "\n")
    write_file(repo, "yarn.lock", "# yarn lockfile v1\n")
    manifest_patch = PatchSpec(
        path=repo / "package.json",
        target=PatchTarget.MANIFEST,
        after="{}\n",
        package="new",
        version="1.2.3",
    )

    patch = compute_lockfile_patch(repo, manifest_patch, ecosystem="npm", lockfile=lockfile)

    assert patch is not None
    assert patch.path == repo / lockfile


def test_selected_yarn_lockfile_does_not_patch_package_lock(tmp_path):
    lock = {"lockfileVersion": 3, "packages": {"": {"name": "demo"}}}
    package_lock = json.dumps(lock, indent=2) + "\n"
    repo = make_repo(tmp_path, {"name": "demo"}, package_lock)
    write_file(repo, "yarn.lock", "# yarn lockfile v1\n")
    manifest_patch = PatchSpec(
        path=repo / "package.json",
        target=PatchTarget.MANIFEST,
        after="{}\n",
        package="new",
        version="1.2.3",
    )

    patch = compute_lockfile_patch(repo, manifest_patch, ecosystem="npm", lockfile="yarn.lock")

    assert patch is not None
    assert patch.path == repo / "yarn.lock"
    assert '"new@1.2.3":' in patch.after
    assert (repo / "package-lock.json").read_text(encoding="utf-8") == package_lock


def test_compute_yarn_lockfile_patch_appends_descriptor(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo, "yarn.lock", '# yarn lockfile v1\n\nexisting@^1.0.0:\n  version "1.0.0"\n')
    manifest_patch = PatchSpec(
        path=repo / "package.json",
        target=PatchTarget.MANIFEST,
        after="{}\n",
        package="leftpad",
        version="1.3.0",
    )

    patch = compute_lockfile_patch(repo, manifest_patch, ecosystem="npm", lockfile="yarn.lock")

    assert patch is not None
    assert patch.path == repo / "yarn.lock"
    assert patch.target == PatchTarget.LOCKFILE
    assert "leftpad" in patch.after


def test_compute_pnpm_lockfile_patch_appends_package_entry(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo, "pnpm-lock.yaml", "lockfileVersion: '6.0'\n\npackages:\n")
    manifest_patch = PatchSpec(
        path=repo / "package.json",
        target=PatchTarget.MANIFEST,
        after="{}\n",
        package="leftpad",
        version="1.3.0",
    )

    patch = compute_lockfile_patch(repo, manifest_patch, ecosystem="npm", lockfile="pnpm-lock.yaml")

    assert patch is not None
    assert patch.path == repo / "pnpm-lock.yaml"
    assert patch.target == PatchTarget.LOCKFILE
    assert "leftpad" in patch.after


def test_unparseable_yarn_lockfile_returns_none(tmp_path):
    repo = tmp_path / "repo"
    path = repo / "yarn.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe\x00garbage")
    manifest_patch = PatchSpec(
        path=repo / "package.json",
        target=PatchTarget.MANIFEST,
        after="{}\n",
        package="leftpad",
        version="1.3.0",
    )

    assert compute_lockfile_patch(repo, manifest_patch, ecosystem="npm", lockfile="yarn.lock") is None


def test_compute_go_sum_patch_and_missing_lockfiles(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest_patch = PatchSpec(
        path=repo / "go.mod", target=PatchTarget.MANIFEST, after="", package="example.com/lib", version="v1.2.3"
    )
    assert compute_lockfile_patch(repo, manifest_patch, ecosystem="npm") is None
    assert compute_lockfile_patch(repo, manifest_patch, ecosystem="go") is None

    write_file(repo, "go.sum", "example.com/other v1.0.0 h1:abc\n")
    patch = compute_lockfile_patch(repo, manifest_patch, ecosystem="go")
    assert patch is not None
    assert "example.com/lib v1.2.3 h1:0000000000000000000000000000000000000000=" in patch.after
