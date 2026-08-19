"""Validate the checked-in provider-neutral CI examples.

The examples are documentation, but they are executable configuration. Keep
their validation small and dependency-light so ordinary verification catches
drift in the commands that users are expected to copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "ci"
REQUIRED_COMMANDS = (
    "scripts/ci.py verify",
    "scripts/ci.py build",
    "scripts/checksums.py dist --strict",
)


def _read(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def _require_commands(name: str, content: str, errors: list[str]) -> None:
    for command in REQUIRED_COMMANDS:
        if command not in content:
            errors.append(f"{name} is missing required command: {command}")


def _load_yaml(name: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = yaml.safe_load(_read(name))
    except yaml.YAMLError as exc:
        errors.append(f"{name} is not valid YAML: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{name} must contain a YAML mapping")
        return None
    return value


def _validate_gitlab(errors: list[str]) -> None:
    name = "gitlab-ci.yml"
    content = _read(name)
    _require_commands(name, content, errors)
    config = _load_yaml(name, errors)
    if config is None:
        return
    if config.get("image") != "python:3.12":
        errors.append(f"{name} must pin the documented Python image")
    if config.get("stages") != ["verify"]:
        errors.append(f"{name} must define the verify stage")
    job = config.get("impactprism-verify")
    if not isinstance(job, dict):
        errors.append(f"{name} must define the impactprism-verify job")
        return
    if job.get("stage") != "verify":
        errors.append(f"{name} job must run in the verify stage")
    if not isinstance(job.get("script"), list):
        errors.append(f"{name} job must use a script list")


def _validate_azure(errors: list[str]) -> None:
    name = "azure-pipelines.yml"
    content = _read(name)
    _require_commands(name, content, errors)
    config = _load_yaml(name, errors)
    if config is None:
        return
    jobs = config.get("jobs")
    if not isinstance(jobs, list) or not jobs or not isinstance(jobs[0], dict):
        errors.append(f"{name} must define a job list")
        return
    job = jobs[0]
    if job.get("job") != "impactprism_verify":
        errors.append(f"{name} must define the impactprism_verify job")
    matrix = job.get("strategy", {}).get("matrix") if isinstance(job.get("strategy"), dict) else None
    if not isinstance(matrix, dict) or set(matrix) != {"Python310", "Python311", "Python312"}:
        errors.append(f"{name} must retain the Python 3.10-3.12 matrix")
    steps = job.get("steps", [])
    if not isinstance(steps, list) or not any(
        isinstance(step, dict) and step.get("task") == "UsePythonVersion@0" for step in steps
    ):
        errors.append(f"{name} must use UsePythonVersion@0")


def _validate_jenkins(errors: list[str]) -> None:
    name = "Jenkinsfile"
    content = _read(name)
    _require_commands(name, content, errors)
    for marker in ("pipeline {", "agent any", "stage('Verify')", "sh '''", "set -eu"):
        if marker not in content:
            errors.append(f"{name} is missing Jenkins marker: {marker}")


def _validate_posix(errors: list[str]) -> None:
    name = "self-hosted-runner.sh"
    content = _read(name)
    _require_commands(name, content, errors)
    for marker in ("#!/usr/bin/env bash", "set -euo pipefail", "mktemp", "trap cleanup EXIT"):
        if marker not in content:
            errors.append(f"{name} is missing shell marker: {marker}")
    if "gh " in content or "actions/" in content:
        errors.append(f"{name} must not depend on GitHub-specific commands")


def _validate_windows(errors: list[str]) -> None:
    name = "self-hosted-runner.ps1"
    content = _read(name)
    _require_commands(name, content, errors)
    for marker in ("$ErrorActionPreference = \"Stop\"", "try {", "finally {", "Remove-Item -LiteralPath"):
        if marker not in content:
            errors.append(f"{name} is missing PowerShell marker: {marker}")


def validate_examples() -> list[str]:
    """Return all validation errors for the checked-in examples."""

    errors: list[str] = []
    for name in (
        "gitlab-ci.yml",
        "azure-pipelines.yml",
        "Jenkinsfile",
        "self-hosted-runner.sh",
        "self-hosted-runner.ps1",
    ):
        if not (EXAMPLES / name).is_file():
            errors.append(f"missing CI example: {name}")
    if errors:
        return errors
    _validate_gitlab(errors)
    _validate_azure(errors)
    _validate_jenkins(errors)
    _validate_posix(errors)
    _validate_windows(errors)
    return errors


def main() -> int:
    errors = validate_examples()
    if errors:
        for error in errors:
            print(f"CI examples: FAIL: {error}")
        return 1
    print("CI examples: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
