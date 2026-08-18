"""Check release metadata that can be verified without publishing anything."""

from __future__ import annotations

import os
import re
import sys

from impactprism import __version__


SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def main() -> int:
    if not SEMVER.fullmatch(__version__):
        print(f"invalid package version: {__version__!r}", file=sys.stderr)
        return 1

    ref_type = os.environ.get("GITHUB_REF_TYPE")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_type == "tag" and ref_name != f"v{__version__}":
        print(
            f"release tag {ref_name!r} does not match package version v{__version__}",
            file=sys.stderr,
        )
        return 1

    print(f"Release metadata: PASS (version {__version__})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

