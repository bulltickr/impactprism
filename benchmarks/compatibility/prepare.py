"""Fetch and pin the public compatibility corpus into a disposable directory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.compatibility.run import _validate_manifest


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def prepare(manifest_path: str | Path, snapshot_root: str | Path) -> None:
    manifest = Path(manifest_path).resolve()
    root = Path(snapshot_root).resolve()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    cases = _validate_manifest(document)
    root.mkdir(parents=True, exist_ok=True)
    for case in cases:
        destination = root / case["id"]
        if destination.exists():
            raise FileExistsError(f"refusing to reuse existing snapshot: {destination}")
        _run(["git", "clone", "--no-tags", "--filter=blob:none", "--no-checkout", case["url"], str(destination)])
        _run(["git", "fetch", "--no-tags", "--depth", "1", "origin", case["commit_sha"]], cwd=destination)
        _run(["git", "checkout", "--detach", case["commit_sha"]], cwd=destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("snapshot_root")
    args = parser.parse_args(argv)
    prepare(args.manifest, args.snapshot_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
