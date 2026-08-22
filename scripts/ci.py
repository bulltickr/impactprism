"""Provider-neutral verification entry points for ImpactPrism.

These commands are intentionally independent of GitHub Actions. Any CI
provider, local checkout, or self-hosted runner can invoke the same contract.
The public compatibility corpus is separate because its preparation step is
the explicit network boundary.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run(label: str, *arguments: str) -> None:
    command = [PYTHON, *arguments]
    print(f"==> {label}: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def test() -> None:
    _run("tests", "-m", "pytest", "-p", "no:cacheprovider", "-q")


def conformance() -> None:
    _run("conformance", "benchmarks/conformance/run.py", "--json")


def correctness() -> None:
    _run("correctness", "benchmarks/correctness/run.py", "--json")


def build() -> None:
    _run("build", "-m", "build", "--no-isolation")


def smoke() -> None:
    _run("clean-demo smoke", "-m", "impactprism", "scan", "demo/clean-app")


def validate_demos() -> None:
    _run("public demo matrix", "scripts/validate_demos.py")


def action_smoke() -> None:
    _run("provider-neutral Action smoke", "scripts/action_smoke.py")


def validate_ci_examples() -> None:
    _run("provider-neutral CI examples", "scripts/validate_ci_examples.py")


def validate_reproductions() -> None:
    _run(
        "sanitized reproduction bundles",
        "scripts/validate_reproduction.py",
        "tests/fixtures/reproduction_intake",
    )


def review_reproductions() -> None:
    _run(
        "sanitized reproduction review",
        "scripts/review_reproduction.py",
        "tests/fixtures/reproduction_intake",
    )


def verify() -> None:
    test()
    conformance()
    correctness()
    smoke()
    validate_demos()
    action_smoke()
    validate_ci_examples()
    validate_reproductions()
    review_reproductions()


COMMANDS = {
    "test": test,
    "conformance": conformance,
    "correctness": correctness,
    "build": build,
    "smoke": smoke,
    "validate-demos": validate_demos,
    "action-smoke": action_smoke,
    "validate-ci-examples": validate_ci_examples,
    "validate-reproductions": validate_reproductions,
    "review-reproductions": review_reproductions,
    "verify": verify,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    COMMANDS[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
