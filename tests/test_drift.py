import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from impactprism import budgets
from impactprism.drift import analyze_repo, classify_drift, DriftReport, Finding, FindingType, Severity, Confidence, Status
from impactprism.manifest import parse_manifest, parse_lockfile


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(root, relpath, value):
    return write_file(root, relpath, json.dumps(value, indent=2) + "\n")


def make_npm_repo(tmp_path, package, source, lock_packages=None):
    repo = tmp_path / "npm-repo"
    write_json(repo, "package.json", package)
    if lock_packages is not None:
        packages = {"": {"name": package.get("name", "fixture"), "version": "1.0.0"}}
        packages.update(
            {
                f"node_modules/{name}": {"version": version}
                for name, version in lock_packages.items()
            }
        )
        write_json(
            repo,
            "package-lock.json",
            {
                "name": package.get("name", "fixture"),
                "version": "1.0.0",
                "lockfileVersion": 3,
                "packages": packages,
            },
        )
    write_file(repo, "src/app.js", source)
    return repo


def make_go_repo(tmp_path, go_mod, source):
    repo = tmp_path / "go-repo"
    write_file(repo, "go.mod", go_mod)
    write_file(repo, "main.go", source)
    return repo


def finding(report, finding_type, package):
    matches = [
        item
        for item in report.findings
        if item.finding_type == finding_type and item.package == package
    ]
    assert len(matches) == 1, (finding_type, package, matches)
    return matches[0]


def test_undeclared_direct_use(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {"name": "demo", "version": "1.0.0"},
        'import someLib from "some-lib";\nexport default someLib;\n',
    )

    item = finding(analyze_repo(repo), FindingType.UNDECLARED_DIRECT_USE, "some-lib")

    assert item.severity == Severity.HIGH
    assert item.confidence == Confidence.HIGH
    assert item.status == Status.OPEN
    assert item.ecosystem == "npm"
    assert item.file.replace("\\", "/").endswith("src/app.js")
    assert item.line >= 1
    assert item.column >= 1
    assert item.scope == "dependencies"


def test_declared_unused_candidate_is_advisory(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {
            "name": "demo",
            "version": "1.0.0",
            "dependencies": {"unused-lib": "^1.0.0"},
        },
        "export {};\n",
        {"unused-lib": "1.0.0"},
    )

    item = finding(
        analyze_repo(repo), FindingType.DECLARED_UNUSED_CANDIDATE, "unused-lib"
    )

    assert item.severity == Severity.LOW
    assert item.confidence == Confidence.MEDIUM
    assert item.status == Status.ADVISORY
    assert item.file is None
    assert item.line is None
    assert item.column is None
    assert item.scope == "dependencies"


def test_direct_dependency_used_transitively(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {"name": "demo", "version": "1.0.0"},
        'import transLib from "trans-lib";\nexport default transLib;\n',
        {"trans-lib": "2.0.0"},
    )

    item = finding(
        analyze_repo(repo),
        FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY,
        "trans-lib",
    )

    assert item.severity == Severity.MEDIUM
    assert item.confidence == Confidence.HIGH
    assert item.status == Status.OPEN
    assert item.ecosystem == "npm"


def test_lockfile_manifest_mismatch(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {
            "name": "demo",
            "version": "1.0.0",
            "dependencies": {"react": "^18.0.0"},
        },
        "export {};\n",
        {},
    )

    item = finding(
        analyze_repo(repo), FindingType.LOCKFILE_MANIFEST_MISMATCH, "react"
    )

    assert item.severity == Severity.MEDIUM
    assert item.confidence == Confidence.HIGH
    assert item.status == Status.OPEN
    assert item.manifest.replace("\\", "/").endswith("package.json")
    assert item.lockfile.replace("\\", "/").endswith("package-lock.json")


def test_missing_lockfile_emits_policy_finding(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {
            "name": "demo",
            "version": "1.0.0",
            "dependencies": {"some-lib": "^1.0.0"},
        },
        'import someLib from "some-lib";\nexport default someLib;\n',
    )

    report = analyze_repo(repo)
    missing = [
        finding
        for finding in report.findings
        if finding.finding_type == FindingType.MISSING_LOCKFILE
    ]

    assert len(missing) == 1
    item = missing[0]
    assert item.severity == Severity.MEDIUM
    assert item.confidence == Confidence.HIGH
    assert item.status == Status.OPEN
    assert item.ecosystem == "npm"
    assert item.package is None
    assert item.manifest.replace("\\", "/").endswith("package.json")
    assert item.lockfile is None
    assert item.scope == "dependencies"
    assert len(report.findings) == 1
    assert not any(
        finding.finding_type == FindingType.UNDECLARED_DIRECT_USE
        and finding.package == "some-lib"
        for finding in report.findings
    )
    assert not any(
        finding.finding_type == FindingType.DECLARED_UNUSED_CANDIDATE
        and finding.package == "some-lib"
        for finding in report.findings
    )


def test_workspace_without_lockfile_emits_missing_lockfile(tmp_path):
    repo = tmp_path / "npm-workspace"
    write_json(
        repo,
        "package.json",
        {"name": "root", "version": "1.0.0", "workspaces": ["packages/*"]},
    )
    write_json(
        repo / "packages" / "app",
        "package.json",
        {"name": "app", "version": "1.0.0", "dependencies": {"some-lib": "^1.0.0"}},
    )

    missing = [
        finding
        for finding in analyze_repo(repo)
        if finding.finding_type == FindingType.MISSING_LOCKFILE
    ]

    assert len(missing) == 1
    assert missing[0].manifest.replace("\\", "/").endswith("packages/app/package.json")


def test_workspace_inheriting_root_lockfile_has_no_missing_lockfile(tmp_path):
    repo = tmp_path / "npm-workspace"
    write_json(
        repo,
        "package.json",
        {"name": "root", "version": "1.0.0", "workspaces": ["packages/*"]},
    )
    write_json(
        repo / "packages" / "app",
        "package.json",
        {"name": "app", "version": "1.0.0", "dependencies": {"some-lib": "^1.0.0"}},
    )
    write_json(
        repo,
        "package-lock.json",
        {
            "name": "root",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root", "version": "1.0.0"},
                "node_modules/some-lib": {"version": "1.2.0"},
            },
        },
    )

    assert not any(
        finding.finding_type == FindingType.MISSING_LOCKFILE
        for finding in analyze_repo(repo)
    )


def test_scope_mismatch_dev_imported_in_prod(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {
            "name": "demo",
            "version": "1.0.0",
            "devDependencies": {"chai": "*"},
        },
        "export {};\n",
        {"chai": "5.0.0"},
    )
    write_file(repo, "src/lib.js", 'import chai from "chai";\nexport default chai;\n')

    item = finding(analyze_repo(repo), FindingType.SCOPE_MISMATCH, "chai")

    assert item.severity == Severity.LOW
    assert item.confidence == Confidence.MEDIUM
    assert item.status == Status.OPEN
    assert item.scope == "devDependencies"
    assert item.file.replace("\\", "/").endswith("src/lib.js")
    assert item.line >= 1
    assert item.column >= 1


def test_unresolved_relative_import(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {"name": "demo", "version": "1.0.0"},
        'import x from "./missing-helper";\nexport default x;\n',
    )

    item = finding(
        analyze_repo(repo), FindingType.UNRESOLVED_IMPORT, "./missing-helper"
    )

    assert item.severity == Severity.HIGH
    assert item.confidence == Confidence.MEDIUM
    assert item.status == Status.OPEN
    assert item.package == "./missing-helper"
    assert item.file.replace("\\", "/").endswith("src/app.js")
    assert item.line >= 1
    assert item.column >= 1


def test_finding_id_is_deterministic():
    fields = {
        "finding_type": FindingType.UNDECLARED_DIRECT_USE,
        "severity": Severity.HIGH,
        "confidence": Confidence.HIGH,
        "ecosystem": "npm",
        "package": "some-lib",
        "file": "src/app.js",
        "line": 1,
        "column": 20,
        "scope": "dependencies",
    }
    first = Finding(**fields)
    second = Finding(**fields)

    assert first.finding_id == second.finding_id
    assert len(first.finding_id) == 16
    assert all(character in "0123456789abcdef" for character in first.finding_id)


def test_analyze_finding_id_is_stable_across_checkout_paths(tmp_path):
    first_repo = make_npm_repo(
        tmp_path / "first",
        {"name": "demo", "version": "1.0.0"},
        'import someLib from "some-lib";\nexport default someLib;\n',
    )
    second_repo = make_npm_repo(
        tmp_path / "second",
        {"name": "demo", "version": "1.0.0"},
        'import someLib from "some-lib";\nexport default someLib;\n',
    )

    first = analyze_repo(first_repo).findings
    second = analyze_repo(second_repo).findings
    assert [item.finding_id for item in first] == [item.finding_id for item in second]


def test_report_api(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {"name": "demo", "version": "1.0.0"},
        'import someLib from "some-lib";\nexport default someLib;\n',
    )
    report = analyze_repo(repo)

    assert isinstance(report, DriftReport)
    assert isinstance(report.findings, list)
    assert len(report) == len(report.findings)
    assert list(report) == report.findings
    dictionaries = report.as_dicts()
    assert len(dictionaries) == len(report)
    documented_keys = {
        "finding_type",
        "finding_id",
        "severity",
        "confidence",
        "ecosystem",
        "package",
        "file",
        "line",
        "column",
        "manifest",
        "lockfile",
        "commit_sha",
        "scope",
        "explanation",
        "status",
    }
    assert documented_keys <= set(dictionaries[0])
    grouped = report.by_type()
    assert set(grouped) <= set(FindingType)
    assert list(grouped) == [member for member in FindingType if member in grouped]


def test_commit_sha_stamped(tmp_path):
    repo = make_npm_repo(
        tmp_path,
        {"name": "demo", "version": "1.0.0"},
        'import someLib from "some-lib";\nexport default someLib;\n',
    )

    report = analyze_repo(repo, commit_sha="abc123")

    assert report.findings
    assert all(item.commit_sha == "abc123" for item in report)


def test_analyze_repo_unsupported_raises(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()

    with pytest.raises(ValueError):
        analyze_repo(repo)


def test_go_direct_dependency_used_transitively(tmp_path):
    repo = make_go_repo(
        tmp_path,
        "module example.com/demo\n\ngo 1.22\n\nrequire github.com/foo/bar v1.0.0 // indirect\n",
        'package main\n\nimport "github.com/foo/bar"\n\nfunc main() {}\n',
    )

    item = finding(
        analyze_repo(repo),
        FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY,
        "github.com/foo/bar",
    )

    assert item.severity == Severity.MEDIUM
    assert item.confidence == Confidence.HIGH
    assert item.status == Status.OPEN
    assert item.ecosystem == "go"


def test_go_unresolved_import(tmp_path):
    repo = make_go_repo(
        tmp_path,
        "module example.com/demo\n\ngo 1.22\n",
        'package main\n\nimport "example.com/missing/pkg"\n\nfunc main() {}\n',
    )

    item = finding(
        analyze_repo(repo), FindingType.UNRESOLVED_IMPORT, "example.com/missing/pkg"
    )

    assert item.severity == Severity.HIGH
    assert item.status == Status.OPEN
    assert item.ecosystem == "go"


def test_analyze_repo_budget_error_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(budgets, "MAX_FILE_COUNT", 5)
    repo = tmp_path / "npm-repo"
    write_json(repo, "package.json", {"name": "demo", "version": "1.0.0"})
    for index in range(20):
        write_file(repo, os.path.join("src", f"f{index}.js"), "import x from 'x';\n")

    report = analyze_repo(repo)

    assert isinstance(report, DriftReport)
    assert report.findings == []
