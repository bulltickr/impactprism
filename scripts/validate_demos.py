"""Run the checked-in demo repositories through the installed CLI.

This is intentionally provider-neutral.  It gives a new contributor one small
command that exercises the public CLI against every supported ecosystem and
keeps the expected finding-bearing example separate from clean examples.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


DEMOS = (
    (
        "npm-findings",
        Path("demo/npm-app"),
        1,
        {
            "DECLARED_UNUSED_CANDIDATE",
            "MISSING_LOCKFILE",
            "UNDECLARED_DIRECT_USE",
        },
    ),
    ("npm-clean", Path("demo/clean-app"), 0, set()),
    ("python-clean", Path("demo/python-clean"), 0, set()),
    ("go-clean", Path("demo/go-clean"), 0, set()),
)


def _scan_demo(
    name: str,
    repo: Path,
    expected_exit: int,
    expected_types: set[str],
    output_dir: Path,
) -> str | None:
    report_path = output_dir / f"{name}-report.json"
    evidence_path = output_dir / f"{name}-evidence.json"
    command = [
        sys.executable,
        "-m",
        "impactprism",
        "scan",
        str(repo),
        "--report",
        str(report_path),
        "--evidence",
        str(evidence_path),
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expected_exit:
        return (
            f"{name}: expected exit {expected_exit}, got {completed.returncode}; "
            f"stderr={completed.stderr.strip()!r}"
        )
    if not report_path.is_file() or not evidence_path.is_file():
        return f"{name}: scan did not write both report and evidence outputs"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return f"{name}: report is not valid JSON: {error}"

    observed_types = {finding["finding_type"] for finding in report.get("findings", [])}
    if observed_types != expected_types:
        return f"{name}: expected finding types {sorted(expected_types)}, got {sorted(observed_types)}"
    if expected_exit == 0 and report.get("counts", {}).get("total") != 0:
        return f"{name}: clean demo reported findings: {report.get('counts')}"
    return None


def validate_demos() -> list[str]:
    """Return validation errors for the public demo matrix."""

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="impactprism-demos-") as temporary:
        output_dir = Path(temporary)
        for name, repo, expected_exit, expected_types in DEMOS:
            error = _scan_demo(name, repo, expected_exit, expected_types, output_dir)
            if error:
                errors.append(error)
    return errors


def main() -> int:
    errors = validate_demos()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(DEMOS)} demo repositories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
