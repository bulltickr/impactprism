"""Validate a small, explicitly declared ImpactPrism reproduction bundle.

The validator is deliberately read-only. It checks the bundle's metadata,
declared files, paths, size, and basic repository hygiene; it does not execute
the reproduction, install dependencies, contact a registry, or claim to be a
secret scanner.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from impactprism.drift.models import FindingType


METADATA_NAME = "impactprism-reproduction.json"
MAX_FILES = 64
MAX_FILE_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 1024 * 1024
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?:--apply|\binstall\b|\bdeploy\b|\bmerge\b)", re.IGNORECASE
)
FORBIDDEN_PATH_PATTERN = re.compile(
    r"(?:^|/)(?:\.env(?:\.|$)|id_rsa(?:\.|$)|credentials(?:\.|$))"
    r"|\.(?:pem|key|p12|pfx)$",
    re.IGNORECASE,
)
FORBIDDEN_DIRECTORY_NAMES = {".git", "node_modules", "__pycache__", ".venv"}
ALLOWED_ECOSYSTEMS = {"npm", "python", "go", "multiple"}
ALLOWED_RESULTS = {"clean", "findings", "diagnostic"}
ALLOWED_ROLES = {"manifest", "lockfile", "source", "config", "other"}
REQUIRED_SANITIZATION_FLAGS = {
    "secrets_removed",
    "proprietary_source_removed",
    "private_urls_removed",
    "customer_identifiers_removed",
}


def display_bundle_path(bundle: Path) -> str:
    """Return a useful bundle label without disclosing the local path."""

    return bundle.name or "."


def redact_error_paths(errors: list[str], bundle: Path) -> list[str]:
    """Remove local bundle paths before errors are serialized publicly."""

    candidates = {str(bundle)}
    try:
        candidates.add(str(bundle.resolve()))
    except OSError:
        pass
    safe_candidates = sorted(
        (candidate for candidate in candidates if candidate not in {"", "."}),
        key=len,
        reverse=True,
    )
    redacted: list[str] = []
    for message in errors:
        for candidate in safe_candidates:
            message = message.replace(candidate, "<bundle>")
        redacted.append(message)
    return redacted


def _normalise_relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("\\", "/")
    parsed = PurePosixPath(candidate)
    if ABSOLUTE_PATH_PATTERN.match(candidate) or parsed.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in parsed.parts):
        return None
    return parsed.as_posix()


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_bundle(bundle_path: str | Path) -> list[str]:
    """Return deterministic validation errors for one reproduction bundle."""

    root = Path(bundle_path)
    errors: list[str] = []
    if not root.exists():
        return [f"bundle does not exist: {root}"]
    if not root.is_dir():
        return [f"bundle is not a directory: {root}"]
    if root.is_symlink():
        return ["bundle root must not be a symlink"]

    metadata_path = root / METADATA_NAME
    if not metadata_path.is_file() or metadata_path.is_symlink():
        return [f"missing required metadata file: {METADATA_NAME}"]
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"metadata is not valid UTF-8 JSON: {exc}"]
    if not isinstance(metadata, dict):
        return ["metadata root must be a JSON object"]

    if metadata.get("schema_version") != 1:
        _error(errors, "metadata.schema_version must be 1")

    bundle_id = metadata.get("id")
    if not isinstance(bundle_id, str) or not ID_PATTERN.fullmatch(bundle_id):
        _error(errors, "metadata.id must be a lowercase hyphenated slug of 3-64 characters")

    if metadata.get("provenance") not in {"synthetic", "sanitized-external"}:
        _error(errors, "metadata.provenance must be synthetic or sanitized-external")

    if metadata.get("ecosystem") not in ALLOWED_ECOSYSTEMS:
        _error(errors, "metadata.ecosystem must be npm, python, go, or multiple")

    package_manager = metadata.get("package_manager")
    if not isinstance(package_manager, str) or not package_manager.strip():
        _error(errors, "metadata.package_manager must be a non-empty string")

    scan = metadata.get("scan")
    if not isinstance(scan, dict):
        _error(errors, "metadata.scan must be an object")
    else:
        command = scan.get("command")
        if not isinstance(command, str) or not command.strip():
            _error(errors, "metadata.scan.command must be a non-empty string")
        elif FORBIDDEN_COMMAND_PATTERN.search(command):
            _error(errors, "metadata.scan.command must describe review-only scanning")
        expected_result = scan.get("expected_result")
        if expected_result not in ALLOWED_RESULTS:
            _error(errors, "metadata.scan.expected_result must be clean, findings, or diagnostic")
        finding_types = scan.get("expected_finding_types")
        valid_types = {item.name for item in FindingType}
        if not isinstance(finding_types, list) or any(
            not isinstance(item, str) or item not in valid_types for item in finding_types
        ):
            _error(errors, "metadata.scan.expected_finding_types must list known finding families")
        elif expected_result == "clean" and finding_types:
            _error(errors, "a clean reproduction must not list expected finding families")
        elif expected_result == "diagnostic" and finding_types != [FindingType.SCANNER_ERROR.name]:
            _error(errors, "a diagnostic reproduction must list only SCANNER_ERROR")
        elif expected_result == "findings" and not finding_types:
            _error(errors, "a findings reproduction must list at least one finding family")

    sanitization = metadata.get("sanitization")
    if not isinstance(sanitization, dict):
        _error(errors, "metadata.sanitization must be an object")
    else:
        missing_flags = REQUIRED_SANITIZATION_FLAGS.difference(sanitization)
        if missing_flags:
            _error(errors, "metadata.sanitization is missing: " + ", ".join(sorted(missing_flags)))
        for flag in REQUIRED_SANITIZATION_FLAGS:
            if sanitization.get(flag) is not True:
                _error(errors, f"metadata.sanitization.{flag} must be true")

    declared_files: dict[str, str] = {}
    files = metadata.get("files")
    if not isinstance(files, list) or not files:
        _error(errors, "metadata.files must be a non-empty list")
        files = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            _error(errors, f"metadata.files[{index}] must be an object")
            continue
        relative_path = _normalise_relative_path(item.get("path"))
        if relative_path is None:
            _error(errors, f"metadata.files[{index}].path must be a safe relative path")
            continue
        role = item.get("role")
        if role not in ALLOWED_ROLES:
            _error(errors, f"metadata.files[{index}].role must be a supported file role")
        if relative_path in declared_files:
            _error(errors, f"metadata.files contains a duplicate path: {relative_path}")
        declared_files[relative_path] = str(role)

    actual_files: set[str] = set()
    total_bytes = 0
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink():
            _error(errors, f"symlinks are not allowed: {relative}")
            continue
        if candidate.is_dir():
            if candidate.name in FORBIDDEN_DIRECTORY_NAMES:
                _error(errors, f"repository or generated directory is not allowed: {relative}")
            continue
        if not candidate.is_file():
            _error(errors, f"unsupported filesystem entry: {relative}")
            continue
        if relative == METADATA_NAME:
            continue
        actual_files.add(relative)
        size = candidate.stat().st_size
        total_bytes += size
        if size > MAX_FILE_BYTES:
            _error(errors, f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
        if FORBIDDEN_PATH_PATTERN.search(relative):
            _error(errors, f"sensitive-looking filename is not allowed: {relative}")

    if len(actual_files) > MAX_FILES:
        _error(errors, f"bundle contains more than {MAX_FILES} files")
    if total_bytes > MAX_BUNDLE_BYTES:
        _error(errors, f"bundle exceeds {MAX_BUNDLE_BYTES} total bytes")
    undeclared = sorted(actual_files.difference(declared_files))
    missing = sorted(set(declared_files).difference(actual_files))
    if undeclared:
        _error(errors, "files must be declared in metadata: " + ", ".join(undeclared))
    if missing:
        _error(errors, "declared files are missing: " + ", ".join(missing))

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="bundle directory, or parent directory containing bundles")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable result")
    args = parser.parse_args(argv)
    root = Path(args.path)
    bundles = [root] if (root / METADATA_NAME).is_file() else sorted(
        candidate for candidate in root.iterdir() if candidate.is_dir()
    )
    results = [
        {
            "path": display_bundle_path(bundle),
            "errors": redact_error_paths(validate_bundle(bundle), bundle),
        }
        for bundle in bundles
    ]
    passed = all(not result["errors"] for result in results)
    if args.json:
        json.dump({"passed": passed, "bundle_count": len(results), "bundles": results}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Reproduction bundles: {'PASS' if passed else 'FAIL'}")
        for result in results:
            status = "PASS" if not result["errors"] else "FAIL"
            print(f"- {result['path']}: {status}")
            for error in result["errors"]:
                print(f"  - {error}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
