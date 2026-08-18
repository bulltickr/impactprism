"""Dependency-drift classification for npm, Go, and Python repositories.

Combines manifest, lockfile and source-import evidence to emit ``Finding``
objects describing dependency drift: undeclared direct use, direct
dependencies used only transitively, scope mismatches, declared-unused
candidates, manifest/lockfile disagreement and unresolved imports. Malformed
input never raises; whatever could be parsed is classified.
"""

from __future__ import annotations

from pathlib import Path

from .. import go_imports, go_manifest as go_manifest_module, python_imports
from ..python_manifest import canonical_name, is_python_repo
from .. import imports, manifest as manifest_module
from ..npm_semver import npm_satisfies, valid_range
from .models import Confidence, Finding, FindingType, Severity, Status

__all__ = [
    "DriftReport",
    "analyze_repo",
    "classify_drift",
    "classify_npm",
    "classify_go",
    "classify_python",
]

_NODE_BUILTINS = {
    "assert",
    "async_hooks",
    "buffer",
    "child_process",
    "cluster",
    "console",
    "constants",
    "crypto",
    "dgram",
    "diagnostics_channel",
    "dns",
    "domain",
    "events",
    "fs",
    "http",
    "http2",
    "https",
    "inspector",
    "module",
    "net",
    "os",
    "path",
    "perf_hooks",
    "process",
    "punycode",
    "querystring",
    "readline",
    "repl",
    "stream",
    "string_decoder",
    "sys",
    "timers",
    "timers/promises",
    "tls",
    "trace_events",
    "tty",
    "url",
    "util",
    "util/types",
    "v8",
    "vm",
    "wasi",
    "worker_threads",
    "zlib",
}

_NPM_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_LOCKFILE_NAMES = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")
_TEST_SEGMENTS = {"test", "tests", "__tests__", "__mocks__", "spec"}
_PYTHON_IMPORT_ALIASES = {
    "beautifulsoup4": {"bs4"},
    "scikit-learn": {"sklearn"},
    "python-dateutil": {"dateutil"},
    "pyyaml": {"yaml"},
    "pillow": {"pil"},
    "opencv-python": {"cv2"},
    "attrs": {"attr"},
}


class DriftReport:
    """A collection of drift findings for one repository."""

    def __init__(self, findings):
        self.findings = list(findings)

    def by_type(self) -> dict:
        """Return findings grouped by type, keys ordered by ``FindingType``."""
        grouped = {}
        for finding_type in FindingType:
            grouped[finding_type] = [
                finding
                for finding in self.findings
                if finding.finding_type == finding_type
            ]
        return grouped

    def as_dicts(self) -> list:
        """Return the findings as a list of dictionaries."""
        return [finding.as_dict() for finding in self.findings]

    def __len__(self) -> int:
        return len(self.findings)

    def __iter__(self):
        return iter(self.findings)


def analyze_repo(
    repo_dir: str,
    ecosystem: str = "auto",
    commit_sha: str | None = None,
    exclude: set[str] | None = None,
) -> DriftReport:
    """Classify dependency drift for a whole repository.

    The ecosystem is auto-detected from ``package.json`` (npm), ``go.mod``
    (Go), or a supported Python manifest
    (go) unless given explicitly; a missing ecosystem raises ``ValueError``.
    ``commit_sha`` is stamped onto every finding.
    """
    repo = Path(repo_dir)
    if ecosystem == "auto":
        if (repo / "package.json").is_file():
            ecosystem = "npm"
        elif (repo / "go.mod").is_file():
            ecosystem = "go"
        elif is_python_repo(repo):
            ecosystem = "python"
        else:
            raise ValueError("unsupported or missing ecosystem")

    if ecosystem == "npm":
        try:
            manifests = manifest_module.parse_manifests(repo_dir)
        except Exception as exc:
            findings = [_finding_for_manifest_parse_error(repo_dir, "npm", exc, commit_sha=commit_sha)]
            return _finalize_report(findings, repo, commit_sha)
        try:
            imported = imports.scan_imports(repo_dir, exclude=exclude)
        except Exception:
            imported = {}
        findings = _classify_npm_manifests(
            manifests, imported, repo_dir=repo_dir, commit_sha=commit_sha
        )
    elif ecosystem == "go":
        try:
            graph = go_imports.build_import_graph(repo_dir, exclude=exclude)
        except Exception as exc:
            findings = [_finding_for_manifest_parse_error(repo_dir, "go", exc, commit_sha=commit_sha)]
            return _finalize_report(findings, repo, commit_sha)
        try:
            go_sum = go_manifest_module.parse_go_sum(repo_dir)
        except Exception:
            go_sum = []
        findings = classify_go(
            graph,
            repo_dir=repo_dir,
            go_sum=go_sum,
            commit_sha=commit_sha,
        )
    elif ecosystem == "python":
        try:
            manifest = manifest_module.parse_python_manifest(repo_dir)
        except Exception as exc:
            findings = [_finding_for_manifest_parse_error(repo_dir, "python", exc, commit_sha=commit_sha)]
            return _finalize_report(findings, repo, commit_sha)
        try:
            imported = python_imports.scan_imports(repo_dir, exclude=exclude)
        except Exception:
            imported = {}
        try:
            lockfile = manifest_module.parse_python_lockfile(repo_dir)
        except manifest_module.LockfileParseError:
            lockfile = None
        findings = classify_python(
            manifest, imported, repo_dir=repo_dir, lockfile=lockfile, commit_sha=commit_sha
        )
    else:
        raise ValueError(f"unsupported ecosystem: {ecosystem!r}")

    return _finalize_report(findings, repo, commit_sha)


def _finalize_report(findings, repo, commit_sha):
    for finding in findings:
        finding.commit_sha = commit_sha
        finding.refresh_id(repo)
    return DriftReport(sorted(findings, key=_sort_key))


def _finding_for_manifest_parse_error(repo_dir, ecosystem, exc, *, commit_sha=None):
    repo = Path(repo_dir)
    if ecosystem == "npm":
        manifest = repo / "package.json"
    elif ecosystem == "go":
        manifest = repo / "go.mod"
    else:
        manifest = next(
            (repo / name for name in ("pyproject.toml", "Pipfile", "requirements.txt")
             if (repo / name).is_file()),
            repo,
        )
    manifest_str = str(manifest) if manifest.is_file() else str(repo)
    return Finding(
        finding_type=FindingType.SCANNER_ERROR,
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        status=Status.OPEN,
        ecosystem=ecosystem,
        package=None,
        file=None,
        line=None,
        column=None,
        lockfile=None,
        scope=None,
        commit_sha=commit_sha,
        manifest=manifest_str,
        explanation=(
            f"Manifest for {ecosystem} repository at {repo_dir!r} failed to parse: "
            f"{exc}. Findings would be unreliable, so this is reported as a scanner error."
        ),
    )


def _classify_npm_manifests(manifests, imported, *, repo_dir, commit_sha):
    repo = Path(repo_dir)
    partitions = {str(manifest.package_path): (manifest, {}) for manifest in manifests}
    for path, records in imported.items():
        owner = manifest_module._manifest_for_path(manifests, path)
        key = str(owner.package_path)
        partitions[key][1][path] = records

    findings = []
    for manifest, partition_imports in partitions.values():
        lockfile_parse_error = False
        try:
            lockfile = manifest_module._lockfile_for_manifest(repo, manifest)
        except manifest_module.LockfileParseError as exc:
            lockfile_parse_error = True
            findings.extend(
                _findings_for_unparseable_lockfile(manifest, exc, commit_sha=commit_sha)
            )
            lockfile = None
        except Exception:
            lockfile = None
        if (
            lockfile is None
            and not lockfile_parse_error
            and getattr(manifest, "dependencies", [])
        ):
            findings.append(_finding_for_missing_lockfile(manifest, commit_sha=commit_sha))
        findings.extend(
            classify_npm(
                manifest,
                partition_imports,
                repo_dir=repo_dir,
                lockfile=lockfile,
                commit_sha=commit_sha,
            )
        )

    return _postprocess_npm_findings(
        findings,
        declared_anywhere=_declared_packages(manifests),
        imported_anywhere=_imported_packages(imported),
    )


def _findings_for_unparseable_lockfile(manifest, exc, *, commit_sha=None):
    package_path = getattr(manifest, "package_path", None)
    manifest_str = str(Path(package_path).resolve()) if package_path is not None else None
    lockfile_path = getattr(exc, "lockfile_path", None)
    lockfile_str = str(lockfile_path) if lockfile_path is not None else None
    cause = getattr(exc, "cause", None)
    cause_text = str(cause) if cause is not None else str(exc)
    findings = []
    for dependency in getattr(manifest, "dependencies", []) or []:
        findings.append(
            Finding(
                finding_type=FindingType.LOCKFILE_MANIFEST_MISMATCH,
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                status=Status.OPEN,
                ecosystem="npm",
                package=dependency.name,
                manifest=manifest_str,
                lockfile=lockfile_str,
                commit_sha=commit_sha,
                scope=getattr(dependency, "kind", "dependencies"),
                explanation=(
                    f"Lockfile {lockfile_str!r} failed to parse ({cause_text}); "
                    f"declared dependency {dependency.name!r} cannot be verified "
                    "against a lockfile."
                ),
            )
        )
    return findings


def _finding_for_missing_lockfile(manifest, *, commit_sha=None):
    package_path = getattr(manifest, "package_path", None)
    manifest_str = str(Path(package_path).resolve()) if package_path is not None else None
    return Finding(
        finding_type=FindingType.MISSING_LOCKFILE,
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        status=Status.OPEN,
        ecosystem="npm",
        package=None,
        manifest=manifest_str,
        lockfile=None,
        commit_sha=commit_sha,
        scope="dependencies",
        explanation=(
            f"Manifest {manifest_str} declares dependencies but no recognized lockfile "
            "(package-lock.json, npm-shrinkwrap.json, yarn.lock, pnpm-lock.yaml) was found, "
            "so declared and used dependencies cannot be verified for reproducibility."
        ),
    )


def _declared_packages(manifests):
    declared = set()
    for manifest in manifests:
        declared.update(manifest.dependency_names())
    return declared


def _imported_packages(imported):
    packages = set()
    for records in imported.values():
        for record in records:
            specifier = getattr(record, "specifier", None)
            if not isinstance(specifier, str) or not specifier:
                continue
            if _is_node_builtin(specifier) or _is_relative(specifier):
                continue
            package = _extract_package(specifier)
            if package is not None:
                packages.add(package)
    return packages


def _postprocess_npm_findings(findings, *, declared_anywhere, imported_anywhere):
    deduplicated = []
    seen = set()
    for finding in findings:
        if finding.finding_id in seen:
            continue
        seen.add(finding.finding_id)
        deduplicated.append(finding)

    filtered = []
    for finding in deduplicated:
        if (
            finding.finding_type == FindingType.LOCKFILE_MANIFEST_MISMATCH
            and finding.severity == Severity.LOW
            and finding.package is not None
            and (finding.package in declared_anywhere or finding.package in imported_anywhere)
        ):
            continue
        filtered.append(finding)
    return filtered


def classify_drift(
    declared,
    imported,
    *,
    ecosystem: str,
    repo_dir: str | None = None,
    lockfile=None,
    commit_sha: str | None = None,
) -> list:
    """Dispatch drift classification to the ecosystem-specific classifier."""
    if ecosystem == "npm":
        findings = classify_npm(
            declared,
            imported,
            repo_dir=repo_dir,
            lockfile=lockfile,
            commit_sha=commit_sha,
        )
    elif ecosystem == "go":
        go_sum = None
        if repo_dir is not None:
            try:
                go_sum = go_manifest_module.parse_go_sum(repo_dir)
            except Exception:
                go_sum = None
        findings = classify_go(
            imported,
            repo_dir=repo_dir,
            go_manifest=None,
            go_sum=go_sum,
            commit_sha=commit_sha,
        )
    elif ecosystem == "python":
        findings = classify_python(
            declared,
            imported,
            repo_dir=repo_dir,
            lockfile=lockfile,
            commit_sha=commit_sha,
        )
    else:
        raise ValueError(f"unsupported ecosystem: {ecosystem!r}")
    return sorted(findings, key=_sort_key)


def classify_npm(
    manifest,
    imports_by_file,
    *,
    repo_dir: str | None = None,
    lockfile=None,
    commit_sha: str | None = None,
) -> list:
    """Classify npm dependency drift.

    ``manifest`` is a ``manifest.Manifest``, ``imports_by_file`` maps source
    paths to lists of ``ImportRecord``, and ``lockfile`` is a
    ``manifest.Lockfile`` or ``None``.
    """
    findings = []

    declared_names = set(manifest.dependency_names())
    lockfile_resolved = lockfile.resolved_versions if lockfile is not None else {}
    if not isinstance(lockfile_resolved, dict):
        lockfile_resolved = {}

    repo = Path(repo_dir).resolve() if repo_dir is not None else None
    manifest_path = None
    package_path = getattr(manifest, "package_path", None)
    if package_path is not None:
        manifest_path = Path(package_path).resolve()
    elif repo is not None:
        manifest_path = repo / "package.json"
    lockfile_path = _find_lockfile(repo) if repo is not None else None

    bare_sites = {}
    relative_sites = {}

    for path in sorted(imports_by_file.keys(), key=lambda item: str(item)):
        records = imports_by_file[path]
        if not records:
            continue
        file_path = Path(path).resolve()
        source = _read_source(file_path)
        is_test = _is_test_path(file_path, repo)
        for record in records:
            if record is None:
                continue
            specifier = getattr(record, "specifier", None)
            if not isinstance(specifier, str) or not specifier:
                continue
            start = getattr(record, "start", 0)
            if not isinstance(start, int):
                start = 0
            line, column = _line_column(source, start)
            if _is_relative(specifier):
                if not _resolves_relative(repo, file_path, specifier):
                    relative_sites.setdefault(
                        specifier, (specifier, str(file_path), line, column)
                    )
                continue
            if _is_node_builtin(specifier):
                continue
            package = _extract_package(specifier)
            if package is None:
                continue
            bare_sites.setdefault(package, []).append(
                (specifier, str(file_path), line, column, is_test)
            )

    for package in sorted(bare_sites):
        sites = bare_sites[package]
        first = min(sites, key=lambda site: (site[1], site[2], site[3]))
        specifier, file_str, line, column, _ = first
        if package in declared_names:
            continue
        if package in lockfile_resolved:
            findings.append(
                Finding(
                    finding_type=FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY,
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    status=Status.OPEN,
                    ecosystem="npm",
                    package=package,
                    file=file_str,
                    line=line,
                    column=column,
                    commit_sha=commit_sha,
                    scope="dependencies",
                    explanation=(
                        f"Package {package!r} (from import {specifier!r}) is present in "
                        "the lockfile but not declared in package.json."
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    finding_type=FindingType.UNDECLARED_DIRECT_USE,
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    status=Status.OPEN,
                    ecosystem="npm",
                    package=package,
                    file=file_str,
                    line=line,
                    column=column,
                    commit_sha=commit_sha,
                    scope="dependencies",
                    explanation=(
                        f"Package {package!r} (from import {specifier!r}) is neither "
                        "declared in package.json nor present in the lockfile."
                    ),
                )
            )

    dependencies = getattr(manifest, "dependencies", []) or []
    by_kind = {}
    for dependency in dependencies:
        by_kind.setdefault(getattr(dependency, "kind", "dependencies"), []).append(dependency)

    for dependency in by_kind.get("devDependencies", []):
        package = dependency.name
        sites = bare_sites.get(package)
        if not sites:
            continue
        non_test = [site for site in sites if not site[4]]
        if not non_test:
            continue
        first = min(non_test, key=lambda site: (site[1], site[2], site[3]))
        findings.append(
            Finding(
                finding_type=FindingType.SCOPE_MISMATCH,
                severity=Severity.LOW,
                confidence=Confidence.MEDIUM,
                status=Status.OPEN,
                ecosystem="npm",
                package=package,
                file=first[1],
                line=first[2],
                column=first[3],
                commit_sha=commit_sha,
                scope=dependency.kind,
                explanation=(
                    f"Dev-only dependency {package!r} is imported in non-test code "
                    f"({first[1]})."
                ),
            )
        )

    for dependency in by_kind.get("dependencies", []):
        package = dependency.name
        sites = bare_sites.get(package)
        if not sites:
            continue
        if not all(site[4] for site in sites):
            continue
        first = min(sites, key=lambda site: (site[1], site[2], site[3]))
        findings.append(
            Finding(
                finding_type=FindingType.SCOPE_MISMATCH,
                severity=Severity.LOW,
                confidence=Confidence.MEDIUM,
                status=Status.OPEN,
                ecosystem="npm",
                package=package,
                file=first[1],
                line=first[2],
                column=first[3],
                commit_sha=commit_sha,
                scope=dependency.kind,
                explanation=(
                    f"Production dependency {package!r} is imported only in test code "
                    f"({first[1]})."
                ),
            )
        )

    for dependency in dependencies:
        package = dependency.name
        if package in bare_sites:
            continue
        findings.append(
            Finding(
                finding_type=FindingType.DECLARED_UNUSED_CANDIDATE,
                severity=Severity.LOW,
                confidence=Confidence.MEDIUM,
                status=Status.ADVISORY,
                ecosystem="npm",
                package=package,
                commit_sha=commit_sha,
                scope=dependency.kind,
                explanation=(
                    f"Declared dependency {package!r} is never imported by any "
                    "scanned file."
                ),
            )
        )

    if lockfile is not None:
        for dependency in dependencies:
            if dependency.locked_version is not None:
                # A lockfile can contain a version that is present but outside
                # the range declared in package.json.  Treat only recognizable
                # npm ranges as comparable; protocols and aliases are handled
                # by npm_satisfies, while malformed specs retain the existing
                # best-effort behavior.
                if valid_range(dependency.version) and not npm_satisfies(
                    dependency.version, dependency.locked_version
                ):
                    findings.append(
                        Finding(
                            finding_type=FindingType.LOCKFILE_MANIFEST_MISMATCH,
                            severity=Severity.MEDIUM,
                            confidence=Confidence.HIGH,
                            status=Status.OPEN,
                            ecosystem="npm",
                            package=dependency.name,
                            manifest=str(manifest_path) if manifest_path is not None else None,
                            lockfile=str(lockfile_path) if lockfile_path is not None else None,
                            commit_sha=commit_sha,
                            scope=dependency.kind,
                            explanation=(
                                f"Locked version {dependency.locked_version!r} for "
                                f"{dependency.name!r} does not satisfy the declared "
                                f"npm range {dependency.version!r}."
                            ),
                        )
                    )
                continue
            findings.append(
                Finding(
                    finding_type=FindingType.LOCKFILE_MANIFEST_MISMATCH,
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    status=Status.OPEN,
                    ecosystem="npm",
                    package=dependency.name,
                    manifest=str(manifest_path) if manifest_path is not None else None,
                    lockfile=str(lockfile_path) if lockfile_path is not None else None,
                    commit_sha=commit_sha,
                    scope=dependency.kind,
                    explanation=(
                        f"Declared dependency {dependency.name!r} has no locked "
                        "version in the lockfile."
                    ),
                )
            )
        for package in sorted(lockfile_resolved):
            if package in declared_names or package in bare_sites:
                continue
            findings.append(
                Finding(
                    finding_type=FindingType.LOCKFILE_MANIFEST_MISMATCH,
                    severity=Severity.LOW,
                    confidence=Confidence.MEDIUM,
                    status=Status.OPEN,
                    ecosystem="npm",
                    package=package,
                    commit_sha=commit_sha,
                    scope="dependencies",
                    explanation=(
                        f"Lockfile package {package!r} is neither declared in "
                        "package.json nor imported anywhere."
                    ),
                )
            )

    for specifier in sorted(relative_sites):
        _, file_str, line, column = relative_sites[specifier]
        findings.append(
            Finding(
                finding_type=FindingType.UNRESOLVED_IMPORT,
                severity=Severity.HIGH,
                confidence=Confidence.MEDIUM,
                status=Status.OPEN,
                ecosystem="npm",
                package=specifier,
                file=file_str,
                line=line,
                column=column,
                commit_sha=commit_sha,
                scope="dependencies",
                explanation=(
                    f"Relative import {specifier!r} does not resolve to an existing "
                    "file."
                ),
            )
        )

    return findings


def classify_python(
    manifest,
    imports_by_file,
    *,
    repo_dir: str | None = None,
    lockfile=None,
    commit_sha: str | None = None,
) -> list:
    """Classify Python imports against PEP 621/Poetry/Pipenv requirements.

    Import records carry source offsets, so every source-derived finding keeps
    the originating file, line, column, and dynamic/static provenance in its
    explanation. Relative imports are checked as source paths and are never
    mistaken for third-party packages.
    """
    findings = []
    repo = Path(repo_dir).resolve() if repo_dir is not None else None
    dependencies = getattr(manifest, "dependencies", None)
    if dependencies is None and isinstance(manifest, (set, list, tuple)):
        dependencies = [
            type("DependencyView", (), {
                "name": name, "kind": "dependencies", "locked_version": None,
            })()
            for name in manifest
        ]
    dependencies = list(dependencies or [])
    declared_by_name = {}
    for dependency in dependencies:
        declared_name = canonical_name(dependency.name)
        declared_by_name[declared_name] = dependency
        for alias in _PYTHON_IMPORT_ALIASES.get(declared_name, set()):
            declared_by_name[alias] = dependency
    lockfile_resolved = getattr(lockfile, "resolved_versions", {}) if lockfile is not None else {}
    lockfile_resolved = {
        canonical_name(name): version for name, version in (lockfile_resolved or {}).items()
    }
    for distribution, aliases in _PYTHON_IMPORT_ALIASES.items():
        if distribution in lockfile_resolved:
            for alias in aliases:
                lockfile_resolved.setdefault(alias, lockfile_resolved[distribution])
    manifest_path = getattr(manifest, "package_path", None)
    manifest_path = Path(manifest_path).resolve() if manifest_path is not None else None
    lockfile_path = _python_lockfile_path(repo) if repo is not None else None
    package_sites = {}
    relative_sites = {}
    for raw_path in sorted(imports_by_file, key=lambda value: str(value)):
        records = imports_by_file[raw_path] or []
        file_path = Path(raw_path).resolve()
        source = _read_source(file_path)
        is_test = _is_test_path(file_path, repo)
        for record in records:
            specifier = getattr(record, "specifier", None)
            if not isinstance(specifier, str) or not specifier:
                continue
            start = getattr(record, "start", 0)
            line, column = _line_column(source, start if isinstance(start, int) else 0)
            if _is_relative_python(specifier):
                if not _resolves_python_relative(repo, file_path, specifier):
                    relative_sites.setdefault(specifier, (str(file_path), line, column))
                continue
            package = _python_package(specifier)
            if package is None or _is_python_stdlib(package):
                continue
            package_sites.setdefault(package, []).append(
                (str(file_path), line, column, is_test, getattr(record, "kind", "static"), specifier)
            )

    for package in sorted(package_sites):
        sites = package_sites[package]
        first = min(sites, key=lambda item: (item[0], item[1], item[2]))
        file_str, line, column, _is_test, kind, specifier = first
        dependency = declared_by_name.get(package)
        if dependency is None:
            if package in lockfile_resolved:
                finding_type = FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY
                severity = Severity.MEDIUM
                explanation = (
                    f"Python package {specifier!r} is imported ({kind}) but is present "
                    "only in the lockfile, not in the manifest."
                )
            else:
                finding_type = FindingType.UNDECLARED_DIRECT_USE
                severity = Severity.HIGH
                explanation = (
                    f"Python package {specifier!r} is imported ({kind}) but is neither "
                    "declared in the manifest nor present in the lockfile."
                )
            findings.append(_python_finding(
                finding_type, severity, Confidence.HIGH, package, file_str, line, column,
                manifest_path, lockfile_path, commit_sha, "dependencies", explanation,
            ))

    for dependency in dependencies:
        package = canonical_name(dependency.name)
        sites = package_sites.get(package, [])
        if not sites:
            for alias in _PYTHON_IMPORT_ALIASES.get(package, set()):
                sites.extend(package_sites.get(alias, []))
        if getattr(dependency, "kind", "dependencies") == "devDependencies":
            non_test = [site for site in sites if not site[3]]
            if non_test:
                first = min(non_test, key=lambda item: (item[0], item[1], item[2]))
                findings.append(_python_finding(
                    FindingType.SCOPE_MISMATCH, Severity.LOW, Confidence.MEDIUM, package,
                    first[0], first[1], first[2], manifest_path, lockfile_path, commit_sha,
                    dependency.kind, f"Development-only Python dependency {dependency.name!r} is imported by non-test code.",
                ))
        elif sites and all(site[3] for site in sites):
            first = min(sites, key=lambda item: (item[0], item[1], item[2]))
            findings.append(_python_finding(
                FindingType.SCOPE_MISMATCH, Severity.LOW, Confidence.MEDIUM, package,
                first[0], first[1], first[2], manifest_path, lockfile_path, commit_sha,
                dependency.kind, f"Production Python dependency {dependency.name!r} is imported only by test code.",
            ))
        if not sites:
            findings.append(_python_finding(
                FindingType.DECLARED_UNUSED_CANDIDATE, Severity.LOW, Confidence.MEDIUM, package,
                None, None, None, manifest_path, lockfile_path, commit_sha, dependency.kind,
                f"Declared Python dependency {dependency.name!r} is never imported by scanned files.",
                status=Status.ADVISORY,
            ))
        if lockfile is not None and getattr(dependency, "locked_version", None) is None:
            findings.append(_python_finding(
                FindingType.LOCKFILE_MANIFEST_MISMATCH, Severity.MEDIUM, Confidence.HIGH, package,
                None, None, None, manifest_path, lockfile_path, commit_sha, dependency.kind,
                f"Declared Python dependency {dependency.name!r} has no locked version.",
            ))

    for package in sorted(lockfile_resolved):
        if package not in declared_by_name and package not in package_sites:
            findings.append(_python_finding(
                FindingType.LOCKFILE_MANIFEST_MISMATCH, Severity.LOW, Confidence.MEDIUM, package,
                None, None, None, manifest_path, lockfile_path, commit_sha, "dependencies",
                f"Lockfile Python package {package!r} is neither declared nor imported.",
            ))

    if lockfile is None and dependencies:
        findings.append(Finding(
            finding_type=FindingType.MISSING_LOCKFILE, severity=Severity.MEDIUM,
            confidence=Confidence.HIGH, status=Status.OPEN, ecosystem="python",
            manifest=str(manifest_path) if manifest_path else None, lockfile=None,
            commit_sha=commit_sha, scope="dependencies",
            explanation="Python dependencies are declared but no supported lockfile was found.",
        ))
    for specifier, (file_str, line, column) in sorted(relative_sites.items()):
        findings.append(_python_finding(
            FindingType.UNRESOLVED_IMPORT, Severity.HIGH, Confidence.MEDIUM, specifier,
            file_str, line, column, manifest_path, lockfile_path, commit_sha, None,
            f"Relative Python import {specifier!r} does not resolve to a Python source file.",
        ))
    return findings


def _python_finding(finding_type, severity, confidence, package, file, line, column,
                    manifest, lockfile, commit_sha, scope, explanation, *, status=Status.OPEN):
    return Finding(
        finding_type=finding_type, severity=severity, confidence=confidence,
        status=status, ecosystem="python", package=package, file=file, line=line,
        column=column, manifest=str(manifest) if manifest else None,
        lockfile=str(lockfile) if lockfile else None, commit_sha=commit_sha,
        scope=scope, explanation=explanation,
    )


def classify_go(
    graph,
    *,
    repo_dir: str | None = None,
    go_manifest=None,
    go_sum=None,
    commit_sha: str | None = None,
) -> list:
    """Classify Go dependency drift.

    ``graph`` is a ``go_imports.GoImportGraph``; declared dependencies and
    replaces are taken from the workspace-aware ``graph.manifest`` (a
    ``go_mod.GoManifest``), which merges go.work member modules rather than
    reading the root go.mod alone. ``go_manifest`` is a deprecated legacy
    fallback used only when ``graph.manifest`` has no modules; ``go_sum``
    supplies the parsed ``go.sum`` entries. Scope is always ``None``.
    """
    findings = []

    repo = Path(repo_dir).resolve() if repo_dir is not None else None
    graph_manifest = getattr(graph, "manifest", None)
    main_module = getattr(graph_manifest, "main_module", None)

    go_mod_path = None
    if go_manifest is not None and getattr(go_manifest, "go_mod_path", None) is not None:
        go_mod_path = Path(go_manifest.go_mod_path).resolve()
    if go_mod_path is None and getattr(graph_manifest, "repo_dir", None) is not None:
        go_mod_path = Path(graph_manifest.repo_dir) / "go.mod"
    if go_mod_path is None and repo is not None:
        go_mod_path = repo / "go.mod"

    declared_deps = []
    declared_names = set()
    if getattr(graph_manifest, "modules", None) is None and go_manifest is not None:
        for dependency in getattr(go_manifest, "dependencies", []) or []:
            module = getattr(dependency, "module", None)
            if not module:
                continue
            direct = not bool(getattr(dependency, "indirect", False))
            declared_deps.append((module, direct))
            declared_names.add(module)
    else:
        for entry in getattr(graph_manifest, "modules", []) or []:
            module = getattr(entry, "module_path", None)
            if not module:
                continue
            if main_module and module == main_module:
                continue
            source = getattr(entry, "source", None)
            if source not in (None, "go.mod", "go.work"):
                continue
            direct = bool(getattr(entry, "direct", False))
            declared_deps.append((module, direct))
            declared_names.add(module)

    target_for = {}
    replacement_targets = set()
    if getattr(graph_manifest, "modules", None) is None and go_manifest is not None:
        for rule in getattr(go_manifest, "replaces", []) or []:
            old = getattr(rule, "old", None)
            new = getattr(rule, "new", None)
            if not old or not new:
                continue
            if getattr(rule, "local", False) or new.startswith(".") or Path(new).is_absolute():
                continue
            target_for[old] = new
            replacement_targets.add(new)
        for dependency in getattr(go_manifest, "dependencies", []) or []:
            module = getattr(dependency, "module", None)
            replacement = getattr(dependency, "replacement", None)
            if not module or not replacement:
                continue
            if getattr(dependency, "replacement_local", False):
                continue
            target = replacement.split()[0]
            if target.startswith(".") or Path(target).is_absolute():
                continue
            target_for[module] = target
            replacement_targets.add(target)
    else:
        for entry in getattr(graph_manifest, "modules", []) or []:
            module = getattr(entry, "module_path", None)
            if not module:
                continue
            if main_module and module == main_module:
                continue
            source = getattr(entry, "source", None)
            if source not in (None, "go.mod", "go.work"):
                continue
            replaced_by = getattr(entry, "replaced_by", None)
            if replaced_by is None:
                continue
            new_path = getattr(replaced_by, "new_path", None)
            if new_path is None or getattr(replaced_by, "local_dir", None) is not None:
                continue
            target_for[module] = new_path
            replacement_targets.add(new_path)

    declared_names.update(replacement_targets)

    if go_sum is None and repo is not None:
        try:
            go_sum = go_manifest_module.parse_go_sum(repo_dir)
        except Exception:
            go_sum = []
    go_sum_entries = go_sum or []
    go_sum_modules = {entry.module for entry in go_sum_entries if getattr(entry, "module", None)}

    go_sum_path = None
    if repo is not None:
        go_sum_path = repo / "go.sum"
    if go_sum_path is None and getattr(graph_manifest, "repo_dir", None) is not None:
        go_sum_path = Path(graph_manifest.repo_dir) / "go.sum"

    module_usage = getattr(graph, "module_usage", {}) or {}

    for module_path in sorted(module_usage):
        usage = module_usage[module_path]
        if not usage.used or usage.direct:
            continue
        findings.append(
            Finding(
                finding_type=FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY,
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                status=Status.OPEN,
                ecosystem="go",
                package=module_path,
                file=_first_import_file(usage),
                commit_sha=commit_sha,
                scope=None,
                explanation=(
                    f"Module {module_path!r} is imported directly but only declared "
                    "as an indirect dependency in go.mod."
                ),
            )
        )

    for module_path in sorted(module_usage):
        usage = module_usage[module_path]
        if not usage.used:
            continue
        if module_path in declared_names:
            continue
        if main_module and module_path == main_module:
            continue
        findings.append(
            Finding(
                finding_type=FindingType.UNDECLARED_DIRECT_USE,
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                status=Status.OPEN,
                ecosystem="go",
                package=module_path,
                file=_first_import_file(usage),
                commit_sha=commit_sha,
                scope=None,
                explanation=f"Module {module_path!r} is imported but not declared in go.mod.",
            )
        )

    for module, direct in declared_deps:
        if not direct:
            continue
        usage = module_usage.get(target_for.get(module, module))
        if usage is not None and usage.used:
            continue
        findings.append(
            Finding(
                finding_type=FindingType.DECLARED_UNUSED_CANDIDATE,
                severity=Severity.LOW,
                confidence=Confidence.MEDIUM,
                status=Status.ADVISORY,
                ecosystem="go",
                package=module,
                commit_sha=commit_sha,
                scope=None,
                explanation=f"Declared dependency {module!r} is never imported.",
            )
        )

    if go_sum_entries:
        for module, _direct in declared_deps:
            if target_for.get(module, module) in go_sum_modules:
                continue
            findings.append(
                Finding(
                    finding_type=FindingType.LOCKFILE_MANIFEST_MISMATCH,
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    status=Status.OPEN,
                    ecosystem="go",
                    package=module,
                    manifest=str(go_mod_path.resolve()) if go_mod_path is not None else None,
                    lockfile=str(go_sum_path.resolve()) if go_sum_path is not None else None,
                    commit_sha=commit_sha,
                    scope=None,
                    explanation=f"Declared module {module!r} has no go.sum entry.",
                )
            )

    for import_path in getattr(graph, "unresolved", []) or []:
        edge = None
        for candidate in getattr(graph, "package_edges", []) or []:
            if candidate.resolved is None and getattr(candidate, "import_path", None) == import_path:
                edge = candidate
                break
        file_str = None
        if edge is not None and getattr(edge, "package_dir", None) is not None:
            file_str = str(Path(edge.package_dir).resolve())
        findings.append(
            Finding(
                finding_type=FindingType.UNRESOLVED_IMPORT,
                severity=Severity.HIGH,
                confidence=Confidence.MEDIUM,
                status=Status.OPEN,
                ecosystem="go",
                package=import_path,
                file=file_str,
                commit_sha=commit_sha,
                scope=None,
                explanation=(
                    f"Go import {import_path!r} cannot be resolved to a declared "
                    "module."
                ),
            )
        )

    return findings


def _first_import_file(usage):
    files = getattr(usage, "importing_files", None)
    if not files:
        return None
    first = files[0]
    return str(Path(first).resolve())


def _sort_key(finding):
    return (
        finding.finding_type.value,
        finding.package or "",
        finding.file or "",
        finding.line if finding.line is not None else -1,
        finding.column if finding.column is not None else -1,
    )


def _read_source(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return ""


def _line_column(source: str, start: int) -> tuple:
    prefix = source[:start]
    line = prefix.count("\n") + 1
    column = start - prefix.rfind("\n")
    return line, column


def _find_lockfile(repo: Path):
    for name in _LOCKFILE_NAMES:
        candidate = repo / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def _python_lockfile_path(repo: Path | None):
    if repo is None:
        return None
    for name in ("poetry.lock", "uv.lock", "Pipfile.lock", "requirements.txt"):
        candidate = repo / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def _python_package(specifier: str):
    if not specifier or specifier.startswith("."):
        return None
    return canonical_name(specifier.split(".", 1)[0])


def _is_python_stdlib(package: str) -> bool:
    import sys

    stdlib = getattr(sys, "stdlib_module_names", set())
    return package in {canonical_name(name) for name in stdlib}


def _is_relative_python(specifier: str) -> bool:
    return specifier.startswith(".")


def _resolves_python_relative(repo, importing_file: Path, specifier: str) -> bool:
    base = importing_file.parent
    dots = len(specifier) - len(specifier.lstrip("."))
    target = specifier[dots:]
    current = base
    for _ in range(max(0, dots - 1)):
        current = current.parent
    candidate = current.joinpath(*target.split(".")) if target else current
    candidates = [candidate.with_suffix(".py"), candidate.with_suffix(".pyi"), candidate / "__init__.py"]
    if repo is not None:
        root = repo.resolve()
        candidates = [path for path in candidates if _is_within(path.resolve(), root)]
    return any(path.is_file() for path in candidates)


def _is_node_builtin(specifier: str) -> bool:
    return specifier.startswith("node:") or specifier in _NODE_BUILTINS


def _is_relative(specifier: str) -> bool:
    return specifier.startswith("./") or specifier.startswith("../") or specifier.startswith("/")


def _extract_package(specifier: str):
    if specifier.startswith("@"):
        parts = specifier.split("/")
        if len(parts) < 2:
            return None
        return "/".join(parts[:2])
    return specifier.split("/", 1)[0]


def _is_test_path(path: Path, repo: Path | None = None) -> bool:
    relative = path
    if repo is not None:
        try:
            relative = path.resolve().relative_to(repo.resolve())
        except (OSError, ValueError):
            relative = path
    if any(part in _TEST_SEGMENTS for part in relative.parts):
        return True
    name = relative.name
    return ".test." in name or ".spec." in name


def _resolves_relative(repo, importing_file: Path, specifier: str) -> bool:
    base = importing_file.parent
    root = repo.resolve() if repo is not None else base.resolve()
    try:
        target = (base / specifier).resolve()
    except OSError:
        return False
    if repo is not None and not _is_within(target, root):
        return False
    candidates = [target]
    if target.is_dir():
        for suffix in _NPM_SUFFIXES:
            candidates.append(target / ("index" + suffix))
    else:
        for suffix in _NPM_SUFFIXES:
            candidates.append(Path(str(target) + suffix))
    for candidate in candidates:
        if repo is not None and not _is_within(candidate, root):
            continue
        if candidate.is_file():
            return True
    return False


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
