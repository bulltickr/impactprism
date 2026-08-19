"""Shared repository-scan service used by the CLI and GitHub Action.

The public surfaces have different presentation needs, but they should not
silently disagree about what a repository scan means.  This module owns the
small amount of orchestration around the classifier: ecosystem resolution,
the legacy metadata adapter, canonical report construction, and SBOM output.
It deliberately has no provider-specific behavior.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import go_imports
from .analysis import generate_sbom, main as analysis_main
from .drift import FindingType, analyze_repo
from .python_manifest import is_python_repo
from .reporting import build_scan_report


DEFAULT_SCAN_EXCLUDES = frozenset(
    {
        "tests",
        "fixtures",
        "demo",
        "node_modules",
        "build",
        "dist",
        ".git",
        ".cache",
        "coverage",
        "public",
    }
)


@dataclass(frozen=True)
class ScanResult:
    """The provider-neutral result of one repository scan."""

    report: dict
    ecosystem: str
    findings: list[dict]
    sbom: dict | None

    @property
    def scanner_error(self) -> bool:
        return any(
            finding.get("finding_type") == FindingType.SCANNER_ERROR.name
            for finding in self.findings
        )

    @property
    def scanner_error_message(self) -> str | None:
        for finding in self.findings:
            if finding.get("finding_type") == FindingType.SCANNER_ERROR.name:
                return finding.get("explanation") or "dependency scan failed"
        return None


def detect_ecosystem(repo_path: Path) -> str | None:
    """Detect the supported ecosystem represented by ``repo_path``."""

    if (repo_path / "package.json").is_file():
        return "npm"
    if (repo_path / "go.mod").is_file():
        return "go"
    if is_python_repo(repo_path):
        return "python"
    return None


def resolve_ecosystem(repo_path: Path, requested: str = "auto") -> str | None:
    """Resolve an explicit or automatic ecosystem request."""

    if requested == "auto":
        return detect_ecosystem(repo_path)
    if requested not in ("npm", "python", "go"):
        return None
    if requested == "npm" and not (repo_path / "package.json").is_file():
        return None
    if requested == "go" and not (repo_path / "go.mod").is_file():
        return None
    if requested == "python" and not is_python_repo(repo_path):
        return None
    return requested


def _legacy_metadata(repo_path: Path, ecosystem: str, excludes: set[str]) -> dict:
    """Read package metadata from the established analysis adapter.

    The dependency-drift classifier is authoritative for findings.  The
    existing analysis command remains the compatibility source for declared,
    imported, and package identity fields until those manifest adapters are
    fully moved into the classifier model.
    """

    if ecosystem == "python":
        from .analysis import scan_imports
        from .python_manifest import canonical_name, parse_python_manifest

        manifest = parse_python_manifest(repo_path)
        return {
            "package_name": manifest.name or "unknown",
            "package_version": manifest.version or "0.0.0",
            "declared": sorted(
                {canonical_name(dependency.name) for dependency in manifest.dependencies}
            ),
            "imported": sorted(
                scan_imports(str(repo_path), excludes=excludes, ecosystem="python")
            ),
        }
    if ecosystem != "npm":
        return {}
    fd, report_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        arguments = [str(repo_path), "--report", report_path]
        for name in sorted(excludes):
            arguments.extend(["--exclude", name])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            return_code = analysis_main(arguments)
        if return_code == 2 or not Path(report_path).is_file():
            return {}
        import json

        value = json.loads(Path(report_path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}
    finally:
        try:
            os.remove(report_path)
        except OSError:
            pass


def _go_metadata(repo_path: Path, excludes: set[str]) -> dict:
    graph = go_imports.build_import_graph(repo_path, exclude=excludes)
    main_module = getattr(graph.manifest, "main_module", None)
    declared = sorted(
        {
            entry.module_path
            for entry in getattr(graph.manifest, "modules", [])
            if entry.module_path != main_module
            and getattr(entry, "source", None) in (None, "go.mod", "go.work")
        }
    )
    imported = sorted(
        {
            module_path
            for module_path, usage in (getattr(graph, "module_usage", {}) or {}).items()
            if getattr(usage, "used", False)
        }
    )
    return {
        "package_name": main_module or "unknown",
        "package_version": "0.0.0",
        "declared": declared,
        "imported": imported,
    }


def scan_repository(
    repo_path: str | os.PathLike[str],
    *,
    ecosystem: str = "auto",
    excludes: set[str] | None = None,
    commit_sha: str | None = None,
) -> ScanResult:
    """Run the canonical offline scan used by every integration surface."""

    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ValueError("repository directory not found: " + str(repo))
    resolved = resolve_ecosystem(repo, ecosystem)
    if resolved is None:
        raise ValueError("unsupported or missing ecosystem")

    selected_excludes = set(excludes or ())
    classifier = analyze_repo(
        str(repo), ecosystem=resolved, commit_sha=commit_sha, exclude=selected_excludes
    )
    findings = classifier.as_dicts()
    scanner_error = any(
        finding.get("finding_type") == FindingType.SCANNER_ERROR.name
        for finding in findings
    )
    sbom = None if scanner_error else generate_sbom(str(repo), ecosystem=resolved)

    if resolved == "go" and not scanner_error:
        metadata = _go_metadata(repo, selected_excludes)
    else:
        metadata = _legacy_metadata(repo, resolved, selected_excludes)

    report = build_scan_report(
        repo=str(repo),
        ecosystem=resolved,
        findings=findings,
        package_name=metadata.get("package_name", "unknown"),
        package_version=metadata.get("package_version", "0.0.0"),
        declared=metadata.get("declared", []),
        imported=metadata.get("imported", []),
        sbom=sbom,
    )
    return ScanResult(report=report, ecosystem=resolved, findings=findings, sbom=sbom)
