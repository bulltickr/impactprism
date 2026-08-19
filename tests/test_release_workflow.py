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
    assert "      id-token: write" in raw
    assert "      attestations: write" in raw
    assert "python -m build --no-isolation --sdist --wheel --outdir dist" in raw
    assert "python scripts/verify_release_artifacts.py dist" in raw
    assert "python scripts/checksums.py --strict dist" in raw
    assert "python -m pip install --no-index --no-deps --target .release-wheel dist/*.whl" in raw
    assert 'gh release upload "$RELEASE_TAG" dist/* --clobber' in raw
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in raw
    assert "subject-path: dist/*" in raw
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
    assert "python scripts/ci.py conformance" in raw[tests:build]
    assert "python scripts/ci.py correctness" in raw[tests:build]
    assert metadata < tests < build < checksums < upload


def test_action_manifest_keeps_ecosystem_input_nested():
    raw = ACTION_MANIFEST.read_text(encoding="utf-8")

    assert '  ecosystem:\n    description: "Ecosystem to scan. Valid values: auto|npm|python|go."' in raw
    assert "\n  description: \"Ecosystem to scan." not in raw


def test_action_manifest_exposes_explicit_bootstrap_modes():
    raw = ACTION_MANIFEST.read_text(encoding="utf-8")

    assert "  install-mode:" in raw
    assert "  python-command:" in raw
    assert "inputs.install-mode == 'managed'" in raw
    assert "inputs.install-mode == 'offline'" in raw
    assert "PIP_NO_INDEX=1" in raw
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in raw


def test_action_manifest_exposes_common_scan_controls_and_safe_upload_path():
    raw = ACTION_MANIFEST.read_text(encoding="utf-8")

    for name in ("exclude", "config-path", "baseline-path", "delta-path"):
        assert f"  {name}:" in raw
    assert "path: ${{ steps.run.outputs.output-dir }}" in raw
    assert "INPUT_BASELINE_PATH: ${{ inputs.baseline-path }}" in raw


def test_pypi_publishing_workflow_is_removed():
    assert not (ROOT / ".github" / "workflows" / "publish.yml").exists()
