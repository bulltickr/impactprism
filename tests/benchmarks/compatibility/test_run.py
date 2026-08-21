import json
from pathlib import Path

import pytest

from benchmarks.compatibility.run import _digest, _manifest_sha256, _validate_manifest


MANIFEST = Path("benchmarks/compatibility/manifest.json")


def test_public_manifest_is_valid_and_score_free():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))

    cases = _validate_manifest(document)

    assert len(cases) == 10
    assert document["accuracy_claim"] is False
    assert all(len(case["expected_digest"]) == 64 for case in cases)


def test_manifest_validation_rejects_unpinned_digest():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["cases"][0]["expected_digest"] = "TBD"

    with pytest.raises(ValueError, match="expected_digest"):
        _validate_manifest(document)


def test_manifest_validation_rejects_path_escape():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["cases"][0]["required_paths"] = ["../outside.txt"]

    with pytest.raises(ValueError, match="required_paths"):
        _validate_manifest(document)


def test_manifest_validation_rejects_accuracy_claims():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["accuracy_claim"] = True

    with pytest.raises(ValueError, match="accuracy_claim"):
        _validate_manifest(document)


def test_digest_is_canonical_for_normalized_rows():
    rows = [{"finding_type": "B", "line": 2}, {"finding_type": "A", "line": 1}]

    assert _digest(rows) == _digest(json.loads(json.dumps(rows)))


def test_manifest_hash_is_stable_across_checkout_line_endings(tmp_path):
    content = MANIFEST.read_bytes().replace(b"\r\n", b"\n")
    lf_manifest = tmp_path / "manifest-lf.json"
    crlf_manifest = tmp_path / "manifest-crlf.json"
    lf_manifest.write_bytes(content)
    crlf_manifest.write_bytes(content.replace(b"\n", b"\r\n"))

    assert _manifest_sha256(lf_manifest) == _manifest_sha256(crlf_manifest)


def test_manifest_records_real_repository_identity_and_evidence_contract():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for case in _validate_manifest(document):
        assert case["url"].startswith("https://github.com/")
        assert len(case["commit_sha"]) == 40
        assert len(case["source_tree_sha"]) == 40
        assert case["license_evidence_url"].endswith(case["license_path"])
        assert case["expected_result"] in {"clean", "findings"}


def test_public_workflow_keeps_network_and_offline_phases_explicit():
    workflow = Path(".github/workflows/compatibility.yml").read_text(encoding="utf-8")

    assert "Prepare pinned public repositories" in workflow
    assert "Run offline compatibility corpus" in workflow
    assert "--json" in workflow
    assert "actions/upload-artifact@" in workflow
