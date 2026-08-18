from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_publish_workflow_uses_explicit_release_and_trusted_publishing():
    raw = _workflow_text()

    assert "on:\n  release:\n    types: [published]" in raw
    assert "environment: pypi" in raw
    assert "id-token: write" in raw
    assert "contents: read" in raw
    assert "uses: pypa/gh-action-pypi-publish@release/v1" in raw


def test_publish_workflow_has_no_long_lived_registry_token():
    raw = _workflow_text().lower()

    forbidden = ("pypi_api_token", "twine_password", "__token__", "password:")
    assert not any(token in raw for token in forbidden)


def test_publish_workflow_verifies_the_release_tag_before_building():
    raw = _workflow_text()

    checkout = raw.index("- name: Checkout release tag")
    metadata = raw.index("- name: Verify release metadata")
    tests = raw.index("- name: Run release tests")
    build = raw.index("- name: Build distributions")
    publish = raw.index("- name: Publish distributions to PyPI")

    assert "ref: ${{ github.event.release.tag_name }}" in raw[checkout:metadata]
    assert "GITHUB_REF_TYPE: tag" in raw[metadata:tests]
    assert "GITHUB_REF_NAME: ${{ github.event.release.tag_name }}" in raw[metadata:tests]
    assert "python scripts/check_release.py" in raw[metadata:tests]
    assert metadata < tests < build < publish
