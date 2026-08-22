from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISHED_COMPATIBILITY_VERSION = "0.4.8"


def test_compatibility_report_tracks_the_published_release_baseline():
    raw = (ROOT / "docs" / "COMPATIBILITY_REPORT.md").read_text(encoding="utf-8")

    # This report is durable evidence from the published v0.4.8 release. Keep
    # its release identity synchronized with the uploaded result asset.
    assert f"| Scanner version | `{PUBLISHED_COMPATIBILITY_VERSION}` |" in raw
    assert "| Cases | 10 |" in raw
    assert "| Result | 10/10 passed |" in raw
    assert "Network during scan | No" in raw
    assert "Repository code executed | No" in raw
    assert "Repository dependencies installed | No" in raw
    assert "releases/download/v0.4.8/compatibility-result.json" in raw
    assert "releases/download/v0.4.8/compatibility-result.json.sha256" in raw
    assert "Run 32556871118" in raw
    assert "releases/download/v0.4.7/compatibility-result.json" in raw
    assert "releases/download/v0.4.6/compatibility-result.json" in raw
    assert "releases/download/v0.4.4/compatibility-result.json" in raw
    assert "releases/download/v0.4.3/compatibility-result.json" in raw
    assert "releases/download/v0.4.2/compatibility-result.json" in raw
    assert "releases/download/v0.4.1/compatibility-result.json" in raw
    assert "0.4.0" not in raw
    assert "not yet attached to a versioned" not in raw


def test_action_readme_tracks_the_current_published_release():
    raw = (ROOT / "action" / "README.md").read_text(encoding="utf-8")

    assert "bulltickr/impactprism@v0.4.8" in raw
    assert "current synchronized release is `v0.4.8`" in raw
    assert "bulltickr/impactprism@v0.4.7" not in raw
    assert "current synchronized release is `v0.4.7`" not in raw


def test_contributor_path_is_public_and_actionable():
    raw = (ROOT / "docs" / "CONTRIBUTOR_QUICKSTART.md").read_text(
        encoding="utf-8"
    )
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    pr_template = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(
        encoding="utf-8"
    )

    assert "python -m pip install -e \".[test]\"" in raw
    assert "python scripts/ci.py verify" in raw
    assert "docs/ADDING_FIXTURES.md" in raw
    assert "docs/REPRODUCTION_INTAKE.md" in raw
    assert "docs/CI_PORTABILITY.md" in raw
    assert "Security concerns belong in the private security-reporting path" in raw
    assert "docs/CONTRIBUTOR_QUICKSTART.md" in contributing
    assert "Public-data review completed" in pr_template
    assert "Compatibility, limitation, and migration impact" in pr_template


def test_expanded_compatibility_coverage_links_the_durable_release_result():
    raw = (ROOT / "docs" / "COMPATIBILITY_COVERAGE.md").read_text(encoding="utf-8")

    assert "10/10 passed" in raw
    assert "d409c105766d18207a7affa9eda93e049f6a3538d3c8efe02f41e175084ce459" in raw
    assert "releases/download/v0.4.8/compatibility-result.json" in raw
    assert "releases/download/v0.4.8/compatibility-result.json.sha256" in raw
    assert "releases/download/v0.4.7/compatibility-result.json" not in raw
    assert "not a release asset" not in raw
    assert "npm-chalk" in raw
    assert "python-httpx" in raw
    assert "go-chi" in raw


def test_compatibility_artifact_retention_is_longer_than_default_short_lived_runs():
    raw = (WORKFLOWS / "compatibility.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in raw
    assert "contents: read" in raw
    assert "contents: write" not in raw
    assert "retention-days: 90" in raw


def test_dependency_review_is_read_only_and_immutably_pinned():
    raw = (WORKFLOWS / "dependency-review.yml").read_text(encoding="utf-8")

    assert "pull_request:" in raw
    assert "contents: read" in raw
    assert "contents: write" not in raw
    assert "actions/dependency-review-action@2031cfc080254a8a887f58cffee85186f0e49e48 # v4.9.0" in raw
    assert "fail-on-severity: high" in raw


def test_scorecard_publishes_sarif_with_minimal_explicit_permissions():
    raw = (WORKFLOWS / "scorecard.yml").read_text(encoding="utf-8")

    assert "permissions: read-all" in raw
    assert "ossf/scorecard-action@2d1146689b8cda280b9bc96326124645441f03bc # v2.4.4" in raw
    assert "github/codeql-action/upload-sarif@ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd # v4" in raw
    assert "publish_results: true" in raw
    assert "id-token: write" in raw
    assert "security-events: write" in raw
    assert "contents: write" not in raw


def test_feedback_routes_do_not_point_to_disabled_discussions():
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    config = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(
        encoding="utf-8"
    )

    assert "/discussions" not in support
    assert "/discussions" not in config
    assert "usage_question.yml" in support
    assert "compatibility_report.yml" in support


def test_compatibility_intake_routes_external_reports_through_the_review_contract():
    raw = (ROOT / ".github" / "ISSUE_TEMPLATE" / "compatibility_report.yml").read_text(
        encoding="utf-8"
    )

    assert "REPRODUCTION_INTAKE.md" in raw
    assert "sanitized-external" in raw
    assert "Review-only scan command" in raw
    assert "not an accuracy score or compliance claim" in raw
