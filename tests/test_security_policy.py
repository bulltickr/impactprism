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

    assert "github/codeql-action/init@d6317709a54fd87078d323eeb0e48ec331c8e621" in raw
    assert "github/codeql-action/analyze@d6317709a54fd87078d323eeb0e48ec331c8e621" in raw
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
