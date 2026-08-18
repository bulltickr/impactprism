"""Verify local, pinned G2 snapshots without scanning or scoring them.

The frozen G2 manifest and repository corpus are supplied separately. This
tool is the offline boundary between a governed checkout phase and a future
benchmark runner: it verifies each local Git checkout, its pinned commit, a
clean worktree, a deterministic archive hash, and the declared scan inputs.
It never fetches, clones, runs ImpactPrism, or calculates benchmark metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.g2.validate import validate_preflight


@dataclass(frozen=True)
class SnapshotDiagnostic:
    repository_id: str
    message: str

    def render(self) -> str:
        return f"{self.repository_id}: {self.message}"


@dataclass
class SnapshotVerification:
    status: str
    manifest: str
    snapshot_root: str
    repositories_checked: int = 0
    diagnostics: list[SnapshotDiagnostic] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.status == "VERIFIED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "manifest": self.manifest,
            "snapshot_root": self.snapshot_root,
            "repositories_checked": self.repositories_checked,
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "network_accessed": False,
            "scans_run": False,
            "scores_calculated": False,
            "g2_passed": False,
        }


def _git(snapshot: Path, *arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(snapshot), *arguments],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout.strip() if text else result.stdout


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _verify_repository(
    result: SnapshotVerification,
    repository: Mapping[str, Any],
    snapshot_root: Path,
) -> None:
    repository_id = str(repository.get("id") or "unknown")
    snapshot = (snapshot_root / repository_id).resolve()
    result.repositories_checked += 1
    if not snapshot.is_dir():
        result.diagnostics.append(
            SnapshotDiagnostic(repository_id, f"snapshot directory not found: {snapshot}")
        )
        return

    expected_sha = repository.get("commit_sha")
    try:
        actual_sha = str(_git(snapshot, "rev-parse", "HEAD"))
    except (OSError, subprocess.CalledProcessError) as error:
        result.diagnostics.append(SnapshotDiagnostic(repository_id, f"cannot read Git HEAD: {error}"))
        return
    if actual_sha != expected_sha:
        result.diagnostics.append(
            SnapshotDiagnostic(
                repository_id,
                f"HEAD {actual_sha!r} does not match manifest commit {expected_sha!r}",
            )
        )

    try:
        branch = str(_git(snapshot, "symbolic-ref", "--quiet", "--short", "HEAD"))
    except (OSError, subprocess.CalledProcessError):
        branch = ""
    if branch:
        result.diagnostics.append(
            SnapshotDiagnostic(repository_id, f"checkout is not detached (branch: {branch})")
        )

    try:
        dirty = str(_git(snapshot, "status", "--porcelain", "--untracked-files=all"))
    except (OSError, subprocess.CalledProcessError) as error:
        result.diagnostics.append(SnapshotDiagnostic(repository_id, f"cannot inspect Git status: {error}"))
        dirty = ""
    if dirty:
        result.diagnostics.append(SnapshotDiagnostic(repository_id, "checkout is not clean"))

    try:
        archive = _git(snapshot, "archive", "--format=tar", "HEAD", text=False)
        archive_hash = hashlib.sha256(archive).hexdigest()
    except (OSError, subprocess.CalledProcessError) as error:
        result.diagnostics.append(SnapshotDiagnostic(repository_id, f"cannot create Git archive: {error}"))
        archive_hash = None
    if archive_hash != repository.get("source_snapshot_sha256"):
        result.diagnostics.append(
            SnapshotDiagnostic(
                repository_id,
                "git archive SHA-256 does not match source_snapshot_sha256",
            )
        )

    scan_subpath = repository.get("scan_subpath")
    scan_root = (snapshot / str(scan_subpath)).resolve()
    if not _inside(snapshot, scan_root) or not scan_root.is_dir():
        result.diagnostics.append(
            SnapshotDiagnostic(repository_id, f"scan_subpath is not a directory: {scan_subpath!r}")
        )
        return

    for field_name in ("manifest_paths", "lockfile_paths"):
        for relative_path in repository.get(field_name, []) or []:
            candidate = (scan_root / str(relative_path)).resolve()
            if not _inside(scan_root, candidate) or not candidate.is_file():
                result.diagnostics.append(
                    SnapshotDiagnostic(
                        repository_id,
                        f"{field_name} entry is missing from scan_subpath: {relative_path!r}",
                    )
                )


def verify_snapshots(
    manifest_path: str | Path,
    snapshot_root: str | Path,
) -> SnapshotVerification:
    """Verify the local snapshots referenced by a READY G2 manifest."""

    manifest = Path(manifest_path).resolve()
    root = Path(snapshot_root).resolve()
    result = SnapshotVerification("INCOMPLETE", str(manifest), str(root))
    preflight = validate_preflight(manifest)
    if not preflight.ready:
        result.diagnostics.extend(
            SnapshotDiagnostic("preflight", diagnostic) for diagnostic in preflight.errors
        )
        return result
    if not root.is_dir():
        result.diagnostics.append(SnapshotDiagnostic("snapshots", f"directory not found: {root}"))
        return result

    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for repository in document.get("repositories", []):
        _verify_repository(result, repository, root)
    if not result.diagnostics:
        result.status = "VERIFIED"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="frozen G2 manifest YAML")
    parser.add_argument("snapshot_root", help="directory containing <repository-id> Git checkouts")
    parser.add_argument("--json", action="store_true", help="emit machine-readable verification")
    args = parser.parse_args(argv)
    result = verify_snapshots(args.manifest, args.snapshot_root)
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"G2 SNAPSHOT VERIFICATION: {result.status}")
        print(f"Repositories checked: {result.repositories_checked}")
        for diagnostic in result.diagnostics:
            print("- " + diagnostic.render())
        print("No benchmark scores were calculated; VERIFIED is not a G2 pass.")
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
