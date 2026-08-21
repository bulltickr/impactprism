import json
from pathlib import Path

from impactprism.drift.classifier import analyze_repo
from scripts.validate_reproduction import validate_bundle


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests" / "fixtures" / "reproduction_intake" / "npm-undeclared-direct-use"


def test_checked_in_reproduction_bundle_is_explicit_and_safe():
    assert validate_bundle(BUNDLE) == []


def test_reproduction_metadata_declares_the_review_contract():
    metadata = json.loads(
        (BUNDLE / "impactprism-reproduction.json").read_text(encoding="utf-8")
    )

    assert metadata["provenance"] == "synthetic"
    assert metadata["scan"]["expected_result"] == "findings"
    assert metadata["scan"]["expected_finding_types"] == ["UNDECLARED_DIRECT_USE"]


def test_checked_in_reproduction_matches_its_expected_finding_family():
    report = analyze_repo(str(BUNDLE), ecosystem="npm")

    assert [finding.finding_type.name for finding in report] == [
        "UNDECLARED_DIRECT_USE"
    ]
    assert report.findings[0].package == "missingpkg"


def test_validator_rejects_undeclared_files_and_non_review_commands(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    metadata = {
        "schema_version": 1,
        "id": "bad-bundle",
        "provenance": "synthetic",
        "ecosystem": "npm",
        "package_manager": "npm",
        "scan": {
            "command": "npm install && impactprism remediate --apply",
            "expected_result": "findings",
            "expected_finding_types": ["UNDECLARED_DIRECT_USE"],
        },
        "sanitization": {
            "secrets_removed": True,
            "proprietary_source_removed": True,
            "private_urls_removed": True,
            "customer_identifiers_removed": True,
        },
        "files": [{"path": "package.json", "role": "manifest"}],
    }
    (bundle / "impactprism-reproduction.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    (bundle / "package.json").write_text("{}", encoding="utf-8")
    (bundle / "private.txt").write_text("not declared", encoding="utf-8")

    errors = validate_bundle(bundle)

    assert any("review-only" in error for error in errors)
    assert any("files must be declared" in error for error in errors)


def test_validator_rejects_incomplete_sanitization_attestation(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    metadata = {
        "schema_version": 1,
        "id": "small-bundle",
        "provenance": "sanitized-external",
        "ecosystem": "python",
        "package_manager": "requirements",
        "scan": {
            "command": "impactprism scan . --json",
            "expected_result": "clean",
            "expected_finding_types": [],
        },
        "sanitization": {
            "secrets_removed": True,
            "proprietary_source_removed": False,
            "private_urls_removed": True,
            "customer_identifiers_removed": True,
        },
        "files": [{"path": "requirements.txt", "role": "manifest"}],
    }
    (bundle / "impactprism-reproduction.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    (bundle / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")

    errors = validate_bundle(bundle)

    assert any("proprietary_source_removed" in error for error in errors)


def test_validator_rejects_windows_absolute_metadata_paths(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    metadata = {
        "schema_version": 1,
        "id": "absolute-path-bundle",
        "provenance": "synthetic",
        "ecosystem": "go",
        "package_manager": "go modules",
        "scan": {
            "command": "impactprism scan . --json",
            "expected_result": "clean",
            "expected_finding_types": [],
        },
        "sanitization": {
            "secrets_removed": True,
            "proprietary_source_removed": True,
            "private_urls_removed": True,
            "customer_identifiers_removed": True,
        },
        "files": [{"path": "C:/private/go.mod", "role": "manifest"}],
    }
    (bundle / "impactprism-reproduction.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    errors = validate_bundle(bundle)

    assert any("safe relative path" in error for error in errors)
