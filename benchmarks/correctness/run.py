"""Run governed correctness fixtures for supported manifest formats.

These fixtures are versioned regression cases. They are intended to expose
format-specific behavior and false-positive regressions; they are not a
representative external accuracy benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).with_name("cases.json")
EXPECTED_PATH = Path(__file__).with_name("expected.json")
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from impactprism import __version__
from impactprism.drift.classifier import analyze_repo


def _relative_path(value, repo_path):
    if value is None:
        return None
    try:
        return Path(value).resolve().relative_to(repo_path.resolve()).as_posix()
    except (OSError, ValueError):
        return str(value).replace("\\", "/")


def _finding_snapshot(finding, repo_path):
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


def run_cases() -> dict:
    definition = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    expected_cases = expected.get("cases", {})
    results = []
    for case in definition["cases"]:
        repo_path = REPOSITORY_ROOT / case["path"]
        analysis_options = {"ecosystem": case["ecosystem"]}
        if "roots" in case:
            analysis_options["roots"] = case["roots"]
        findings = analyze_repo(str(repo_path), **analysis_options)
        counts = dict(
            sorted(Counter(finding.finding_type.value for finding in findings).items())
        )
        actual_findings = [
            _finding_snapshot(finding, repo_path) for finding in findings
        ]
        expected_case = expected_cases.get(case["id"], {})
        expected_findings = expected_case.get("findings", [])
        expected_counts = case["expected_counts"]
        result = {
            "id": case["id"],
            "path": case["path"],
            "ecosystem": case["ecosystem"],
            "expected_counts": expected_counts,
            "actual_counts": counts,
            "expected_findings": expected_findings,
            "actual_findings": actual_findings,
            "passed": counts == expected_counts
            and actual_findings == expected_findings,
        }
        if "roots" in case:
            result["roots"] = case["roots"]
        results.append(result)
    return {
        "schema_version": 1,
        "runner": "impactprism-governed-correctness",
        "package_version": __version__,
        "case_count": len(results),
        "passed": all(result["passed"] for result in results),
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = parser.parse_args(argv)
    result = run_cases()
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Governed correctness: {'PASS' if result['passed'] else 'FAIL'}")
        for case in result["cases"]:
            print(f"- {case['id']}: {'PASS' if case['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
