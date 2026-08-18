import json
from pathlib import Path

import pytest

from benchmarks.compatibility.run import _digest, _validate_manifest


MANIFEST = Path("benchmarks/compatibility/manifest.json")


def test_public_manifest_is_valid_and_score_free():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))

    cases = _validate_manifest(document)

    assert len(cases) == 7
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
