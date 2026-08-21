from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-artifacts.yml"
ACTION_MANIFEST = ROOT / "action" / "action.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_uses_explicit_github_release_artifacts():
    raw = _workflow_text()

    assert "on:\n  workflow_dispatch:" in raw
    assert "release-tag:" in raw
    assert "type: string" in raw
    assert "permissions:\n  contents: read" in raw
    assert "    permissions:\n      contents: write" in raw
    assert "      id-token: write" in raw
    assert "      attestations: write" in raw
    assert "python -m build --no-isolation --sdist --wheel --outdir dist" in raw
    assert "python scripts/verify_release_artifacts.py dist" in raw
    assert "python scripts/checksums.py --strict dist" in raw
    assert "python -m pip install --no-index --no-deps --target .release-wheel dist/*.whl" in raw
    assert "benchmarks/compatibility/prepare.py" in raw
    assert "benchmarks/compatibility/run.py" in raw
    assert '"$RUNNER_TEMP/compatibility-result.json"' in raw
    assert "--file \"$RUNNER_TEMP/compatibility-result.json\"" in raw
    assert '"$RUNNER_TEMP/compatibility-result.json.sha256"' in raw
    assert 'gh release upload "$RELEASE_TAG" dist/*' in raw
    assert '--clobber' not in raw
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in raw
    assert "subject-path: dist/*" in raw
    assert "pypa/gh-action-pypi-publish" not in raw
    assert "PYPI_API_TOKEN" not in raw


def test_release_workflow_verifies_before_building_and_uploading():
    raw = _workflow_text()

    metadata = raw.index("- name: Verify release metadata")
    tests = raw.index("- name: Run release tests")
    build = raw.index("- name: Build release distributions")
    compatibility = raw.index("- name: Run release compatibility corpus")
    checksums = raw.index("- name: Generate SHA-256 checksums")
    upload = raw.index("- name: Upload artifacts to the GitHub Release")

    assert "GITHUB_REF_TYPE: tag" in raw[metadata:tests]
    assert "GITHUB_REF_NAME: ${{ inputs.release-tag }}" in raw[metadata:tests]
    assert "python scripts/check_release.py" in raw[metadata:tests]
    assert "python scripts/ci.py conformance" in raw[tests:build]
    assert "python scripts/ci.py correctness" in raw[tests:build]
    assert metadata < tests < build < compatibility < checksums < upload


def test_release_workflow_is_draft_first_and_refuses_published_release_mutation():
    raw = _workflow_text()

    prepare = raw.index("- name: Prepare draft GitHub Release")
    upload = raw.index("- name: Upload artifacts to the GitHub Release")
    publish = raw.index("- name: Publish completed GitHub Release")

    assert 'gh release create "$RELEASE_TAG"' in raw[prepare:upload]
    assert "--draft" in raw[prepare:upload]
    assert "--verify-tag" in raw[prepare:upload]
    assert "isDraft" in raw[prepare:upload]
    assert "already published; immutable releases cannot be modified" in raw[prepare:upload]
    assert 'gh release upload "$RELEASE_TAG" dist/*' in raw[upload:publish]
    assert '"$RUNNER_TEMP/compatibility-result.json.sha256"' in raw[upload:publish]
    assert 'gh release edit "$RELEASE_TAG" --draft=false' in raw[publish:]
    assert prepare < upload < publish
    assert "types: [published]" not in raw


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
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0" in raw
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1" in raw


def test_action_readme_tracks_pinned_public_examples():
    raw = (ROOT / "action" / "README.md").read_text(encoding="utf-8")

    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1" in raw
    assert "github/codeql-action/upload-sarif@ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd # v4" in raw


def test_action_manifest_exposes_common_scan_controls_and_safe_upload_path():
    raw = ACTION_MANIFEST.read_text(encoding="utf-8")

    for name in ("exclude", "config-path", "baseline-path", "delta-path"):
        assert f"  {name}:" in raw
    assert "path: ${{ steps.run.outputs.output-dir }}" in raw
    assert "INPUT_BASELINE_PATH: ${{ inputs.baseline-path }}" in raw


def test_pypi_publishing_workflow_is_removed():
    assert not (ROOT / ".github" / "workflows" / "publish.yml").exists()
