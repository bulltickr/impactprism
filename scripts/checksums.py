"""Write portable SHA-256 checksums for a release directory."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    output = write_checksums(args.directory)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
