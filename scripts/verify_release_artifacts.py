"""Verify that built distributions contain the intended public package."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path

from impactprism import __version__

try:
    from scripts.checksums import validate_release_directory
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.checksums import validate_release_directory


def _metadata_version(raw: bytes) -> str:
    match = re.search(rb"^Version:\s*(\S+)\s*$", raw, flags=re.MULTILINE)
    if match is None:
        raise ValueError("distribution metadata has no Version field")
    return match.group(1).decode("ascii")


def verify(directory: str | Path) -> None:
    root = Path(directory).resolve()
    files = validate_release_directory(root)
    wheel = next(path for path in files if path.suffix == ".whl")
    sdist = next(path for path in files if path.name.endswith(".tar.gz"))

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_name = next(
            (name for name in names if name.endswith(".dist-info/METADATA")), None
        )
        if metadata_name is None:
            raise ValueError("wheel has no dist-info/METADATA")
        if _metadata_version(archive.read(metadata_name)) != __version__:
            raise ValueError("wheel metadata version does not match runtime version")
        required = {
            "impactprism/__init__.py",
            "impactprism/cli.py",
            "impactprism/cra_clauses.yaml",
            "impactprism/resolution.py",
            "impactprism/static_config.py",
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError("wheel is missing package files: " + ", ".join(missing))
        if any("C:\\Users\\" in name or name.startswith("/") for name in names):
            raise ValueError("wheel contains an absolute workstation path")

    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        metadata_members = [name for name in names if name.endswith("/PKG-INFO")]
        if not metadata_members:
            raise ValueError("source archive has no PKG-INFO")
        if _metadata_version(archive.extractfile(metadata_members[0]).read()) != __version__:
            raise ValueError("source metadata version does not match runtime version")
        if not any(name.endswith("/src/impactprism/cra_clauses.yaml") for name in names):
            raise ValueError("source archive is missing cra_clauses.yaml")
        if any(name.startswith("/") or "\\Users\\" in name for name in names):
            raise ValueError("source archive contains an absolute workstation path")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    verify(args.directory)
    print("Release artifacts: PASS (version " + __version__ + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
