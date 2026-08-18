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
    _run("tests", "-m", "pytest", "-q")


def conformance() -> None:
    _run("conformance", "benchmarks/conformance/run.py", "--json")


def correctness() -> None:
    _run("correctness", "benchmarks/correctness/run.py", "--json")


def build() -> None:
    _run("build", "-m", "build", "--no-isolation")


def smoke() -> None:
    _run("clean-demo smoke", "-m", "impactprism", "scan", "demo/clean-app")


def verify() -> None:
    test()
    conformance()
    correctness()
    smoke()


COMMANDS = {
    "test": test,
    "conformance": conformance,
    "correctness": correctness,
    "build": build,
    "smoke": smoke,
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
