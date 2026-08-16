import json
from pathlib import Path

import yaml

from benchmarks.g2.validate import validate_preflight


def _valid_manifest(tmp_path: Path, *, count: int = 20, missing_label: str | None = None) -> Path:
    ground_truth = tmp_path / "ground-truth"
    ground_truth.mkdir()
    ecosystems = (["javascript"] * 6) + (["python"] * 7) + (["go"] * 7)
    repositories = []
    for index in range(count):
        repository_id = f"r{index + 1:02d}"
        ecosystem = ecosystems[index % len(ecosystems)]
        is_monorepo = index < 5
        is_dynamic = index < 4
        label_ref = f"ground-truth/{repository_id}.json"
        repositories.append(
            {
                "id": repository_id,
                "url": f"https://example.test/impactprism/{repository_id}",
                "default_branch": "main",
                "commit_sha": f"{index + 1:040x}",
                "license_spdx": ["MIT"],
                "license_evidence_url": f"https://example.test/impactprism/{repository_id}/blob/{index + 1:040x}/LICENSE",
                "license_verified_at_utc": "2026-08-16T00:00:00Z",
                "primary_ecosystem": ecosystem,
                "secondary_ecosystems": [],
                "scan_subpath": ".",
                "manifest_paths": ["package.json" if ecosystem == "javascript" else "pyproject.toml" if ecosystem == "python" else "go.mod"],
                "lockfile_paths": ["package-lock.json" if ecosystem == "javascript" else "poetry.lock" if ecosystem == "python" else "go.sum"],
                "selection_rationale": "synthetic fixture for validator tests",
                "is_monorepo": is_monorepo,
                "monorepo_evidence": {
                    "markers": ["workspace"] if is_monorepo else [],
                    "paths": ["packages"] if is_monorepo else [],
                },
                "has_dynamic_or_generated_code": is_dynamic,
                "dynamic_generated_evidence": {
                    "categories": ["dynamic-import"] if is_dynamic else [],
                    "paths": ["src/index.js"] if is_dynamic else [],
                    "lines": ["10"] if is_dynamic else [],
                },
                "source_snapshot_sha256": f"{index + 1:064x}",
                "ground_truth_ref": label_ref,
            }
        )
        if repository_id == missing_label:
            continue
        label = {
            "repository_id": repository_id,
            "commit_sha": f"{index + 1:040x}",
            "label_schema_version": "1.0",
            "labels": [
                {
                    "label_id": f"{repository_id}-l0001",
                    "repository_id": repository_id,
                    "commit_sha": f"{index + 1:040x}",
                    "finding_type": "UNDECLARED_DIRECT_USE",
                    "package": "example-package",
                    "status": "present",
                    "ecosystem": ecosystem,
                    "source_file": "src/index.js",
                    "line": 10,
                    "column": 1,
                    "manifest": repositories[-1]["manifest_paths"][0],
                    "lockfile": repositories[-1]["lockfile_paths"][0],
                    "rationale": "synthetic evidence row",
                    "evidence_sha256": f"{index + 1:064x}",
                }
            ],
        }
        (ground_truth / f"{repository_id}.json").write_text(
            json.dumps(label), encoding="utf-8"
        )

    manifest = {
        "schema_version": "1.0",
        "benchmark_id": "g2-2026-08-16-r1",
        "status": "complete",
        "created_at_utc": "2026-08-16T00:00:00Z",
        "owner": "impactprism-test",
        "scanner": {
            "repository": "https://example.test/impactprism",
            "commit_sha": "a" * 40,
            "requirements_lock": "requirements-lock.txt",
            "environment_ref": "environment.json",
        },
        "adjudication": {
            "status": "frozen",
            "labeler_a": "labeler-a.json",
            "labeler_b": "labeler-b.json",
            "decisions": "adjudication.json",
            "sign_off": "sign-off.json",
        },
        "outputs": {
            "status": "not_run",
            "report": "outputs/report.json",
            "bom": "outputs/bom.json",
            "evidence": "outputs/evidence.json",
            "normalized_predictions": "outputs/predictions.json",
            "hashes": "outputs/hashes.json",
        },
        "repositories": repositories,
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def test_valid_frozen_manifest_is_ready(tmp_path):
    result = validate_preflight(_valid_manifest(tmp_path))

    assert result.ready
    assert result.status == "READY"
    assert result.repositories_found == 20
    assert result.labels_found == 20
    assert result.quota_counts == {
        "javascript": 6,
        "python": 7,
        "go": 7,
        "monorepo": 5,
        "dynamic_or_generated": 4,
    }
    assert result.as_dict()["scores_calculated"] is False
    assert result.as_dict()["g2_passed"] is False


def test_missing_manifest_is_incomplete(tmp_path):
    result = validate_preflight(tmp_path / "manifest.yaml")

    assert result.status == "INCOMPLETE"
    assert any("missing frozen manifest" in error for error in result.errors)


def test_wrong_repository_count_is_incomplete(tmp_path):
    result = validate_preflight(_valid_manifest(tmp_path, count=19))

    assert not result.ready
    assert result.repositories_found == 19
    assert any("expected exactly 20 repositories, found 19" in error for error in result.errors)


def test_missing_ground_truth_label_is_incomplete(tmp_path):
    result = validate_preflight(_valid_manifest(tmp_path, missing_label="r03"))

    assert not result.ready
    assert result.labels_found == 19
    assert any("r03.json" in error and "label file not found" in error for error in result.errors)


def test_malformed_ground_truth_label_is_incomplete(tmp_path):
    manifest = _valid_manifest(tmp_path)
    label_path = tmp_path / "ground-truth" / "r01.json"
    label = json.loads(label_path.read_text(encoding="utf-8"))
    label["labels"][0]["finding_type"] = "NOT_A_REAL_FINDING"
    label_path.write_text(json.dumps(label), encoding="utf-8")

    result = validate_preflight(manifest)

    assert not result.ready
    assert any("finding_type" in error and "documented finding vocabulary" in error for error in result.errors)
