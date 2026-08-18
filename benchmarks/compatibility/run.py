"""Run the pinned public compatibility corpus against local Git checkouts.

This runner is intentionally a compatibility regression tool, not an
accuracy benchmark. It never fetches repositories, installs their
dependencies, executes repository code, or calculates precision/recall.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from impactprism.drift import analyze_repo


SHA40_LENGTH = 40
SHA256_LENGTH = 64
SUPPORTED_ECOSYSTEMS = {"npm", "python", "go"}
EXPECTED_RESULTS = {"clean", "findings"}


def _validate_relative_path(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must remain within the snapshot: {value!r}")


def _validate_manifest(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema_version") != 1:
        raise ValueError("compatibility manifest schema_version must be 1")
    if document.get("accuracy_claim") is not False:
        raise ValueError("compatibility manifest must set accuracy_claim to false")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("compatibility manifest must contain at least one case")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"
        if not isinstance(case, dict):
            raise ValueError(f"{prefix} must be an object")
        case_id = case.get("id")
        if (
            not isinstance(case_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", case_id)
            or case_id in seen_ids
        ):
            raise ValueError(f"{prefix}.id must be a safe, unique directory name")
        seen_ids.add(case_id)
        url = case.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"{prefix}.url must be an HTTPS URL")
        commit_sha = case.get("commit_sha")
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise ValueError(f"{prefix}.commit_sha must be a lowercase 40-character SHA")
        archive_sha = case.get("source_snapshot_sha256")
        if not isinstance(archive_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", archive_sha):
            raise ValueError(f"{prefix}.source_snapshot_sha256 must be a lowercase SHA-256")
        ecosystem = case.get("ecosystem")
        if ecosystem not in SUPPORTED_ECOSYSTEMS:
            raise ValueError(f"{prefix}.ecosystem is unsupported: {ecosystem!r}")
        expected_result = case.get("expected_result")
        if expected_result not in EXPECTED_RESULTS:
            raise ValueError(f"{prefix}.expected_result must be clean or findings")
        for field in ("scan_subpath", "license_path"):
            _validate_relative_path(case.get(field), f"{prefix}.{field}")
        for field in ("required_paths", "exclude"):
            values = case.get(field, [])
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                raise ValueError(f"{prefix}.{field} must be a list of strings")
            for item_index, value in enumerate(values):
                _validate_relative_path(value, f"{prefix}.{field}[{item_index}]")
        evidence_url = case.get("license_evidence_url")
        if not isinstance(evidence_url, str) or not evidence_url.startswith("https://"):
            raise ValueError(f"{prefix}.license_evidence_url must be an HTTPS URL")
        expected_counts = case.get("expected_counts")
        if not isinstance(expected_counts, dict) or any(
            not isinstance(key, str) or not isinstance(value, int) or value < 0
            for key, value in expected_counts.items()
        ):
            raise ValueError(f"{prefix}.expected_counts must map finding types to non-negative integers")
        expected_digest = case.get("expected_digest")
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise ValueError(f"{prefix}.expected_digest must be a lowercase SHA-256")
    return cases


def _git(snapshot: Path, *arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(snapshot), *arguments],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout.strip() if text else result.stdout


def _relative_path(value: str | None, repo_path: Path) -> str | None:
    if value is None:
        return None
    try:
        return Path(value).resolve().relative_to(repo_path.resolve()).as_posix()
    except (OSError, ValueError):
        return str(value).replace("\\", "/")


def _finding_snapshot(finding, repo_path: Path) -> dict[str, Any]:
    item = finding.as_dict()
    return {
        "finding_id": item["finding_id"],
        "finding_type": item["finding_type"],
        "package": item["package"],
        "file": _relative_path(item["file"], repo_path),
        "line": item["line"],
        "column": item["column"],
        "manifest": _relative_path(item["manifest"], repo_path),
        "lockfile": _relative_path(item["lockfile"], repo_path),
        "scope": item["scope"],
        "severity": item["severity"],
        "confidence": item["confidence"],
        "status": item["status"],
    }


def _digest(findings: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        findings, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _diagnostic(diagnostics: list[str], message: str) -> None:
    diagnostics.append(message)


def _verify_checkout(case: dict[str, Any], snapshot: Path) -> list[str]:
    diagnostics: list[str] = []
    if not snapshot.is_dir():
        return [f"snapshot directory not found: {snapshot}"]
    try:
        actual_sha = str(_git(snapshot, "rev-parse", "HEAD"))
    except (OSError, subprocess.CalledProcessError) as error:
        return [f"cannot read Git HEAD: {error}"]
    if actual_sha != case["commit_sha"]:
        _diagnostic(diagnostics, f"HEAD {actual_sha!r} != {case['commit_sha']!r}")
    try:
        branch = str(_git(snapshot, "symbolic-ref", "--quiet", "--short", "HEAD"))
    except (OSError, subprocess.CalledProcessError):
        branch = ""
    if branch:
        _diagnostic(diagnostics, f"checkout is not detached: {branch}")
    try:
        dirty = str(_git(snapshot, "status", "--porcelain", "--untracked-files=all"))
    except (OSError, subprocess.CalledProcessError) as error:
        _diagnostic(diagnostics, f"cannot inspect Git status: {error}")
        dirty = ""
    if dirty:
        _diagnostic(diagnostics, "checkout is not clean")
    try:
        archive = _git(snapshot, "archive", "--format=tar", "HEAD", text=False)
        archive_sha = hashlib.sha256(archive).hexdigest()
    except (OSError, subprocess.CalledProcessError) as error:
        _diagnostic(diagnostics, f"cannot create Git archive: {error}")
        archive_sha = ""
    if archive_sha != case["source_snapshot_sha256"]:
        _diagnostic(diagnostics, "git archive hash does not match manifest")

    scan_root = (snapshot / case["scan_subpath"]).resolve()
    if not scan_root.is_dir():
        _diagnostic(diagnostics, f"scan_subpath is not a directory: {case['scan_subpath']!r}")
        return diagnostics
    for relative_path in case["required_paths"]:
        candidate = (scan_root / relative_path).resolve()
        try:
            candidate.relative_to(scan_root)
        except ValueError:
            _diagnostic(diagnostics, f"required path escapes scan_subpath: {relative_path!r}")
            continue
        if not candidate.is_file():
            _diagnostic(diagnostics, f"required path is missing: {relative_path!r}")
    return diagnostics


def _run_case(case: dict[str, Any], snapshot_root: Path) -> dict[str, Any]:
    snapshot = (snapshot_root / case["id"]).resolve()
    diagnostics = _verify_checkout(case, snapshot)
    actual_findings: list[dict[str, Any]] = []
    actual_counts: dict[str, int] = {}
    actual_digest = None
    if not diagnostics:
        findings = analyze_repo(
            str(snapshot / case["scan_subpath"]),
            ecosystem=case["ecosystem"],
            exclude=set(case.get("exclude", [])),
        )
        actual_findings = [
            _finding_snapshot(finding, snapshot / case["scan_subpath"])
            for finding in findings
        ]
        actual_counts = dict(
            sorted(Counter(item["finding_type"] for item in actual_findings).items())
        )
        actual_digest = _digest(actual_findings)
        if any(item["finding_type"] == "SCANNER_ERROR" for item in actual_findings):
            _diagnostic(diagnostics, "scanner emitted SCANNER_ERROR")
    expected_counts = case["expected_counts"]
    passed = (
        not diagnostics
        and actual_counts == expected_counts
        and actual_digest == case["expected_digest"]
        and (case["expected_result"] == "clean") == (not actual_findings)
    )
    return {
        "id": case["id"],
        "url": case["url"],
        "commit_sha": case["commit_sha"],
        "ecosystem": case["ecosystem"],
        "expected_result": case["expected_result"],
        "expected_counts": expected_counts,
        "actual_counts": actual_counts,
        "expected_digest": case["expected_digest"],
        "actual_digest": actual_digest,
        "finding_count": len(actual_findings),
        "diagnostics": diagnostics,
        "actual_findings": actual_findings,
        "passed": passed,
    }


def run_corpus(manifest_path: str | Path, snapshot_root: str | Path) -> dict[str, Any]:
    manifest = Path(manifest_path).resolve()
    snapshots = Path(snapshot_root).resolve()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    cases = _validate_manifest(document)
    results = [_run_case(case, snapshots) for case in cases]
    return {
        "schema_version": 1,
        "runner": "impactprism-public-compatibility",
        "corpus_id": document.get("corpus_id"),
        "accuracy_claim": False,
        "network_accessed": False,
        "repository_code_executed": False,
        "dependency_installation_performed": False,
        "case_count": len(results),
        "passed": all(result["passed"] for result in results),
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("snapshot_root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = run_corpus(args.manifest, args.snapshot_root)
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Public compatibility corpus: {'PASS' if result['passed'] else 'FAIL'}")
        for case in result["cases"]:
            print(f"- {case['id']}: {'PASS' if case['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
