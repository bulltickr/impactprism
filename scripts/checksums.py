"""Write portable SHA-256 checksums for a release directory."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


_WHEEL = re.compile(r"^impactprism-(?P<version>[^-]+)-[^/]+\.whl$")
_SDIST = re.compile(r"^impactprism-(?P<version>[^-]+)\.tar\.gz$")


def checksum_lines(directory: str | Path) -> list[str]:
    root = Path(directory).resolve()
    files = sorted(
        path for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    return [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in files
    ]


def write_checksums(directory: str | Path) -> Path:
    root = Path(directory).resolve()
    output = root / "SHA256SUMS"
    output.write_text("\n".join(checksum_lines(root)) + "\n", encoding="utf-8")
    return output


def validate_release_directory(directory: str | Path) -> list[Path]:
    """Require exactly one wheel and one matching source archive."""

    root = Path(directory).resolve()
    files = sorted(path for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    wheels = [path for path in files if _WHEEL.fullmatch(path.name)]
    sdists = [path for path in files if _SDIST.fullmatch(path.name)]
    unexpected = [path for path in files if path not in wheels and path not in sdists]
    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        names = ", ".join(path.name for path in files) or "(empty)"
        raise ValueError(
            "release directory must contain exactly one ImpactPrism wheel and "
            "one matching source archive; found: " + names
        )
    wheel_version = _WHEEL.fullmatch(wheels[0].name).group("version")
    sdist_version = _SDIST.fullmatch(sdists[0].name).group("version")
    if wheel_version != sdist_version:
        raise ValueError("wheel and source archive versions do not match")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--strict", action="store_true", help="require the exact wheel and sdist release set")
    args = parser.parse_args(argv)
    if args.strict:
        try:
            validate_release_directory(args.directory)
        except ValueError as error:
            parser.error(str(error))
    output = write_checksums(args.directory)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
