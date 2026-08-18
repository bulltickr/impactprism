"""Run the small, deterministic fixture suite used by CI.

This is a regression/conformance suite for supported behavior. It is not the
20-repository G2 benchmark and must not be presented as external accuracy
evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from impactprism import __version__
from impactprism.drift.classifier import analyze_repo


CASES = (
    {
        "id": "npm-clean-demo",
        "path": "demo/clean-app",
        "ecosystem": "npm",
        "expected_counts": {},
    },
    {
        "id": "npm-finding-demo",
        "path": "demo/npm-app",
        "ecosystem": "npm",
        "expected_counts": {
            "DECLARED_UNUSED_CANDIDATE": 1,
            "MISSING_LOCKFILE": 1,
            "UNDECLARED_DIRECT_USE": 1,
        },
    },
    {
        "id": "python-clean-demo",
        "path": "demo/python-clean",
        "ecosystem": "python",
        "expected_counts": {},
    },
    {
        "id": "python-finding-fixture",
        "path": "tests/fixtures/python_repo",
        "ecosystem": "python",
        "expected_counts": {
            "DECLARED_UNUSED_CANDIDATE": 1,
            "SCOPE_MISMATCH": 2,
            "UNDECLARED_DIRECT_USE": 1,
            "UNRESOLVED_IMPORT": 1,
        },
    },
    {
        "id": "go-clean-demo",
        "path": "demo/go-clean",
        "ecosystem": "go",
        "expected_counts": {},
    },
    {
        "id": "go-finding-fixture",
        "path": "tests/fixtures/remediation/go_repo",
        "ecosystem": "go",
        "expected_counts": {"UNRESOLVED_IMPORT": 1},
    },
)


def run_cases() -> dict:
    results = []
    for case in CASES:
        findings = analyze_repo(
            str(REPOSITORY_ROOT / case["path"]), ecosystem=case["ecosystem"]
        )
        counts = dict(sorted(Counter(finding.finding_type.value for finding in findings).items()))
        expected = case["expected_counts"]
        results.append(
            {
                "id": case["id"],
                "path": case["path"],
                "ecosystem": case["ecosystem"],
                "expected_counts": expected,
                "actual_counts": counts,
                "passed": counts == expected,
            }
        )
    return {
        "schema_version": 1,
        "runner": "impactprism-local-conformance",
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
        print(f"Local conformance: {'PASS' if result['passed'] else 'FAIL'}")
        for case in result["cases"]:
            print(f"- {case['id']}: {'PASS' if case['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
