from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow_files():
    return sorted(WORKFLOWS.glob("*.yml"))


def test_workflows_do_not_contain_registry_publishing_configuration():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _workflow_files())

    assert "pypa/gh-action-pypi-publish" not in combined
    assert "PYPI_API_TOKEN" not in combined
    assert "twine_password" not in combined.lower()


def test_codeql_has_minimal_security_permissions():
    raw = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")

    assert "github/codeql-action/init@ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd # v4" in raw
    assert "github/codeql-action/analyze@ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd # v4" in raw
    assert "languages: python" in raw
    assert "security-events: write" in raw
    assert "contents: write" not in raw


def test_dependabot_covers_python_and_github_actions():
    raw = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "package-ecosystem: pip" in raw
    assert "package-ecosystem: github-actions" in raw
    assert raw.count("interval: weekly") == 2


def test_contents_write_is_reserved_for_release_artifacts():
    for path in _workflow_files():
        raw = path.read_text(encoding="utf-8")
        if path.name == "release-artifacts.yml":
            assert "contents: write" in raw
        else:
            assert "contents: write" not in raw, path.name


def test_all_workflow_checkouts_disable_persisted_credentials():
    for path in _workflow_files():
        raw = path.read_text(encoding="utf-8")
        checkout_blocks = re.findall(
            r"(?ms)^\s*- name: Checkout[^\n]*\n.*?(?=^\s*- name:|\Z)", raw
        )
        for block in checkout_blocks:
            if "uses: actions/checkout@" in block:
                assert "persist-credentials: false" in block, path.name


def test_third_party_workflow_actions_are_pinned_to_full_shas():
    for path in _workflow_files():
        raw = path.read_text(encoding="utf-8")
        for reference in re.findall(r"^\s*uses:\s+([^\s]+)", raw, re.MULTILINE):
            if reference.startswith("./"):
                continue
            owner_repo, separator, revision = reference.partition("@")
            assert separator and re.fullmatch(r"[0-9a-f]{40}", revision), (
                f"{path.name} uses an unpinned third-party Action: {reference}"
            )


def test_action_smoke_covers_provider_neutral_and_composite_boundaries():
    raw = (WORKFLOWS / "action-smoke.yml").read_text(encoding="utf-8")

    assert "os: [ubuntu-latest, macos-latest, windows-latest]" in raw
    assert raw.count("os: [ubuntu-latest, macos-latest, windows-latest]") >= 2
    assert "python scripts/ci.py action-smoke" in raw
    assert "uses: ./action" in raw
    assert "shell: pwsh" in raw


def test_public_action_manifest_uses_current_pinned_runtime_majors():
    raw = (ROOT / "action" / "action.yml").read_text(encoding="utf-8")

    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0" in raw
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1" in raw
