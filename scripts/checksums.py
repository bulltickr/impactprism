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
    return [checksum_line(path) for path in files]


def checksum_line(path: str | Path, display_name: str | None = None) -> str:
    """Return one portable checksum-manifest line for a file."""

    source = Path(path).resolve()
    name = display_name or source.name
    return f"{hashlib.sha256(source.read_bytes()).hexdigest()}  {name}"


def write_checksums(directory: str | Path) -> Path:
    root = Path(directory).resolve()
    output = root / "SHA256SUMS"
    output.write_text("\n".join(checksum_lines(root)) + "\n", encoding="utf-8")
    return output


def write_file_checksum(file_path: str | Path, output: str | Path | None = None) -> Path:
    """Write a checksum sidecar next to one file and return its path."""

    source = Path(file_path).resolve()
    target = (
        Path(output).resolve()
        if output is not None
        else source.with_name(source.name + ".sha256")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(checksum_line(source) + "\n", encoding="utf-8")
    return target


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
    parser.add_argument("directory", nargs="?")
    parser.add_argument("--file", dest="file_path", help="write a checksum sidecar for one file")
    parser.add_argument("--output", help="sidecar path when using --file")
    parser.add_argument("--strict", action="store_true", help="require the exact wheel and sdist release set")
    args = parser.parse_args(argv)
    if args.file_path:
        if args.directory or args.strict:
            parser.error("--file cannot be combined with a directory or --strict")
        output = write_file_checksum(args.file_path, args.output)
        print(f"Wrote {output}")
        return 0
    if not args.directory:
        parser.error("a directory is required unless --file is used")
    if args.output:
        parser.error("--output requires --file")
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
