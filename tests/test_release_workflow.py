from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-artifacts.yml"
ACTION_MANIFEST = ROOT / "action" / "action.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_uses_explicit_github_release_artifacts():
    raw = _workflow_text()

    assert "on:\n  release:\n    types: [published]" in raw
    assert "permissions:\n  contents: read" in raw
    assert "    permissions:\n      contents: write" in raw
    assert "python -m build --sdist --wheel --outdir dist" in raw
    assert "sha256sum * > SHA256SUMS" in raw
    assert 'gh release upload "$RELEASE_TAG" dist/* --clobber' in raw
    assert "pypa/gh-action-pypi-publish" not in raw
    assert "PYPI_API_TOKEN" not in raw


def test_release_workflow_verifies_before_building_and_uploading():
    raw = _workflow_text()

    metadata = raw.index("- name: Verify release metadata")
    tests = raw.index("- name: Run release tests")
    build = raw.index("- name: Build release distributions")
    checksums = raw.index("- name: Generate SHA-256 checksums")
    upload = raw.index("- name: Upload artifacts to the GitHub Release")

    assert "GITHUB_REF_TYPE: tag" in raw[metadata:tests]
    assert "GITHUB_REF_NAME: ${{ github.event.release.tag_name }}" in raw[metadata:tests]
    assert "python scripts/check_release.py" in raw[metadata:tests]
    assert metadata < tests < build < checksums < upload


def test_action_manifest_keeps_ecosystem_input_nested():
    raw = ACTION_MANIFEST.read_text(encoding="utf-8")

    assert '  ecosystem:\n    description: "Ecosystem to scan. Valid values: auto|npm|python|go."' in raw
    assert "\n  description: \"Ecosystem to scan." not in raw


def test_pypi_publishing_workflow_is_removed():
    assert not (ROOT / ".github" / "workflows" / "publish.yml").exists()
