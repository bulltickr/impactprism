from pathlib import Path

import hashlib
import subprocess

from benchmarks.g2.verify_snapshots import (
    SnapshotVerification,
    _verify_repository,
    verify_snapshots,
)


def test_snapshot_verification_requires_ready_manifest(tmp_path: Path):
    result = verify_snapshots(tmp_path / "manifest.yaml", tmp_path / "snapshots")

    assert result.status == "INCOMPLETE"
    assert result.verified is False
    assert result.as_dict()["network_accessed"] is False
    assert result.as_dict()["scans_run"] is False
    assert result.as_dict()["scores_calculated"] is False
    assert any("missing frozen manifest" in item.render() for item in result.diagnostics)


def test_snapshot_verification_checks_detached_commit_archive_and_inputs(
    tmp_path: Path, monkeypatch
):
    snapshot = tmp_path / "r01"
    snapshot.mkdir()
    (snapshot / "package.json").write_text("{}\n", encoding="utf-8")
    (snapshot / "package-lock.json").write_text("{}\n", encoding="utf-8")
    commit_sha = "a" * 40
    archive = b"deterministic archive"

    def fake_git(_snapshot, *arguments, text=True):
        if arguments == ("rev-parse", "HEAD"):
            return commit_sha
        if arguments == ("symbolic-ref", "--quiet", "--short", "HEAD"):
            raise subprocess.CalledProcessError(1, "git")
        if arguments == ("status", "--porcelain", "--untracked-files=all"):
            return ""
        if arguments == ("archive", "--format=tar", "HEAD"):
            return archive
        raise AssertionError(arguments)

    monkeypatch.setattr("benchmarks.g2.verify_snapshots._git", fake_git)
    result = SnapshotVerification("INCOMPLETE", "manifest.yaml", str(tmp_path))
    _verify_repository(
        result,
        {
            "id": "r01",
            "commit_sha": commit_sha,
            "source_snapshot_sha256": hashlib.sha256(archive).hexdigest(),
            "scan_subpath": ".",
            "manifest_paths": ["package.json"],
            "lockfile_paths": ["package-lock.json"],
        },
        tmp_path,
    )

    assert result.repositories_checked == 1
    assert result.diagnostics == []
