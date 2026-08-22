"""Review sanitized reproduction bundles without executing repository code.

The review command composes the read-only bundle validator with the local
static scanner. It emits a machine-readable record that a maintainer can use
to decide whether a report is a regression, a documented limitation, or an
unsupported shape. It never installs dependencies, contacts a registry, or
executes files from the submitted bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from impactprism import __version__
from impactprism.drift.classifier import analyze_repo
from impactprism.drift.models import FindingType
from scripts.validate_reproduction import METADATA_NAME, validate_bundle


SUPPORTED_ECOSYSTEMS = {"npm", "python", "go"}


def _relative_path(value: object, bundle: Path) -> str | None:
    if value is None:
        return None
    try:
        return Path(value).resolve().relative_to(bundle.resolve()).as_posix()
    except (OSError, ValueError):
        return str(value).replace("\\", "/")


def _finding_snapshot(finding, bundle: Path) -> dict:
    item = finding.as_dict()
    return {
        "finding_id": item["finding_id"],
        "finding_type": item["finding_type"],
        "package": item["package"],
        "file": _relative_path(item["file"], bundle),
        "line": item["line"],
        "column": item["column"],
        "manifest": _relative_path(item["manifest"], bundle),
        "lockfile": _relative_path(item["lockfile"], bundle),
        "scope": item["scope"],
        "severity": item["severity"],
        "confidence": item["confidence"],
        "status": item["status"],
    }


def _actual_result(findings) -> str:
    if any(finding.finding_type is FindingType.SCANNER_ERROR for finding in findings):
        return "diagnostic"
    return "findings" if findings else "clean"


def review_bundle(bundle_path: str | Path) -> dict:
    """Return a deterministic review record for one reproduction bundle."""

    bundle = Path(bundle_path)
    validation_errors = validate_bundle(bundle)
    result = {
        "schema_version": 1,
        "reviewer": "impactprism-reproduction-review",
        "scanner_version": __version__,
        "path": str(bundle),
        "validation_errors": validation_errors,
        "passed": False,
    }
    if validation_errors:
        return result

    try:
        metadata = json.loads(
            (bundle / METADATA_NAME).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result["validation_errors"] = [f"metadata could not be read: {exc}"]
        return result

    ecosystem = metadata["ecosystem"]
    result.update(
        {
            "bundle_id": metadata["id"],
            "provenance": metadata["provenance"],
            "ecosystem": ecosystem,
            "package_manager": metadata["package_manager"],
            "expected": metadata["scan"],
        }
    )
    if ecosystem not in SUPPORTED_ECOSYSTEMS:
        result["validation_errors"] = [
            "review requires one supported ecosystem: npm, python, or go"
        ]
        return result

    findings = analyze_repo(str(bundle), ecosystem=ecosystem)
    actual_types = sorted({finding.finding_type.value for finding in findings})
    actual_result = _actual_result(findings)
    expected = metadata["scan"]
    expected_types = sorted(set(expected["expected_finding_types"]))
    result["actual"] = {
        "result": actual_result,
        "finding_types": actual_types,
        "findings": [_finding_snapshot(finding, bundle) for finding in findings],
    }
    result["matches_expectation"] = (
        actual_result == expected["expected_result"]
        and actual_types == expected_types
    )
    result["passed"] = result["matches_expectation"]
    return result


def _bundles(root: Path) -> list[Path]:
    if (root / METADATA_NAME).is_file():
        return [root]
    return sorted(
        candidate
        for candidate in root.iterdir()
        if candidate.is_dir() and not candidate.is_symlink()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="bundle directory or parent containing bundles")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    root = Path(args.path)
    bundles = _bundles(root) if root.exists() and root.is_dir() else [root]
    records = [review_bundle(bundle) for bundle in bundles]
    output = {
        "schema_version": 1,
        "reviewer": "impactprism-reproduction-review",
        "scanner_version": __version__,
        "bundle_count": len(records),
        "passed": bool(records) and all(record["passed"] for record in records),
        "bundles": records,
    }
    if args.json:
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Reproduction review: {'PASS' if output['passed'] else 'REVIEW REQUIRED'}")
        for record in records:
            status = "PASS" if record["passed"] else "REVIEW REQUIRED"
            print(f"- {record['path']}: {status}")
            for error in record.get("validation_errors", []):
                print(f"  - {error}")
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
