"""Offline environment and repository diagnostics for first-run support."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from . import __version__
from .python_manifest import is_python_repo


DOCTOR_SCHEMA_VERSION = 1


def _check(check_id, status, message, **details):
    value = {"id": check_id, "status": status, "message": message}
    if details:
        value["details"] = details
    return value


def _detect_ecosystem(repo_path):
    if (repo_path / "package.json").is_file():
        return "npm"
    if (repo_path / "go.mod").is_file():
        return "go"
    if is_python_repo(repo_path):
        return "python"
    return None


def _manifest_details(repo_path, ecosystem):
    names = {
        "npm": (
            "package.json",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "yarn.lock",
            "pnpm-lock.yaml",
        ),
        "python": (
            "pyproject.toml",
            "Pipfile",
            "requirements.txt",
            "poetry.lock",
            "Pipfile.lock",
            "uv.lock",
        ),
        "go": ("go.mod", "go.work", "go.sum", "vendor"),
    }.get(ecosystem, ())
    present = [name for name in names if (repo_path / name).exists()]
    lockfiles = {
        "npm": {"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml"},
        "python": {"poetry.lock", "Pipfile.lock", "uv.lock"},
        "go": {"go.sum", "vendor"},
    }.get(ecosystem, set())
    return present, [name for name in present if name in lockfiles]


def diagnose(repo="."):
    """Return a JSON-serializable, offline diagnostic report."""

    repo_path = Path(repo).expanduser().resolve()
    checks = []
    version = tuple(sys.version_info[:2])
    if version >= (3, 10):
        checks.append(
            _check("python-version", "pass", "Python version is supported", version=f"{version[0]}.{version[1]}")
        )
    else:
        checks.append(
            _check("python-version", "fail", "ImpactPrism requires Python 3.10 or newer", version=f"{version[0]}.{version[1]}")
        )

    for module_name in ("yaml", "cyclonedx"):
        try:
            importlib.import_module(module_name)
        except ImportError:
            checks.append(
                _check(
                    "dependency-" + module_name,
                    "fail",
                    f"Required runtime dependency is unavailable: {module_name}",
                )
            )
        else:
            checks.append(
                _check(
                    "dependency-" + module_name,
                    "pass",
                    f"Required runtime dependency is available: {module_name}",
                )
            )

    if not repo_path.is_dir():
        checks.append(
            _check("repository", "fail", "Repository directory was not found", path=str(repo_path))
        )
        return _build_report(repo_path, None, checks)

    checks.append(_check("repository", "pass", "Repository directory is readable", path=str(repo_path)))
    ecosystem = _detect_ecosystem(repo_path)
    if ecosystem is None:
        checks.append(
            _check(
                "ecosystem",
                "fail",
                "No supported npm, Python, or Go manifest was detected",
                supported=["npm", "python", "go"],
            )
        )
        return _build_report(repo_path, None, checks)

    present, lockfiles = _manifest_details(repo_path, ecosystem)
    checks.append(
        _check(
            "ecosystem",
            "pass",
            f"Detected supported {ecosystem} repository",
            ecosystem=ecosystem,
        )
    )
    checks.append(
        _check(
            "inputs",
            "pass" if present else "fail",
            "Supported scan inputs detected" if present else "No supported scan inputs detected",
            files=present,
        )
    )
    if lockfiles:
        checks.append(_check("lockfile", "pass", "A supported lockfile or vendored dependency tree is present", files=lockfiles))
    else:
        checks.append(
            _check(
                "lockfile",
                "warn",
                "No supported lockfile was detected; the scan may emit MISSING_LOCKFILE",
            )
        )
    return _build_report(repo_path, ecosystem, checks)


def _build_report(repo_path, ecosystem, checks):
    failures = sum(check["status"] == "fail" for check in checks)
    warnings = sum(check["status"] == "warn" for check in checks)
    status = "fail" if failures else ("warn" if warnings else "pass")
    return {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "generator": "impactprism-doctor",
        "version": __version__,
        "target": str(repo_path),
        "ecosystem": ecosystem,
        "status": status,
        "summary": {"checks": len(checks), "failures": failures, "warnings": warnings},
        "checks": checks,
    }


def render(report):
    lines = [
        "ImpactPrism doctor",
        f"Target: {report['target']}",
        f"Ecosystem: {report['ecosystem'] or 'not detected'}",
        f"Status: {report['status']}",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"[{check['status'].upper()}] {check['message']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check ImpactPrism and repository readiness without network access.")
    parser.add_argument("repo", nargs="?", default=".", help="repository directory (default: current directory)")
    parser.add_argument("--json", action="store_true", help="write the diagnostic report as JSON")
    args = parser.parse_args(argv)
    report = diagnose(args.repo)
    if args.json:
        import json

        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        sys.stdout.write(render(report))
    return 1 if report["status"] == "fail" else 0
