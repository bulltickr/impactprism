import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import impactprism.manifest
from impactprism import budgets
from impactprism.manifest import parse_lockfile, parse_manifest


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, package=None, lockfile=None, lockfile_name=None):
    repo = tmp_path / "repo"
    if package is not None:
        write_file(repo, "package.json", json.dumps(package, indent=2))
    if lockfile_name is not None:
        write_file(repo, lockfile_name, lockfile)
    return repo


def test_manifest_reads_all_dependency_kinds(tmp_path):
    package = {
        "name": "demo",
        "version": "1.0.0",
        "dependencies": {"react": "^18.2.0"},
        "devDependencies": {"eslint": "^8.0.0"},
        "peerDependencies": {"react-dom": ">=18"},
        "optionalDependencies": {"fsevents": "^2.3.3"},
    }
    manifest = parse_manifest(make_repo(tmp_path, package))

    assert manifest.name == "demo"
    assert manifest.version == "1.0.0"
    assert manifest.package_path == tmp_path / "repo" / "package.json"
    assert manifest.dependency_names() == {"react", "eslint", "react-dom", "fsevents"}
    assert manifest.by_name("eslint").dev is True
    assert manifest.by_name("react").kind == "dependencies"
    assert manifest.by_name("missing") is None


def test_package_lock_resolves_scoped_dependencies(tmp_path):
    package = {"name": "demo", "version": "1.0.0", "dependencies": {"react": "^18.2.0", "@scope/pkg": "^1.0.0"}}
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "demo", "version": "1.0.0"},
            "node_modules/react": {"version": "18.3.1"},
            "node_modules/@scope/pkg": {"version": "1.2.3"},
        },
    }
    repo = make_repo(tmp_path, package, json.dumps(lock), "package-lock.json")
    manifest = parse_manifest(repo)

    assert manifest.by_name("react").locked_version == "18.3.1"
    assert manifest.by_name("@scope/pkg").locked_version == "1.2.3"
    assert parse_lockfile(repo).kind == "npm"


def test_npm_shrinkwrap_legacy_fallback(tmp_path):
    package = {"name": "demo", "version": "1.0.0", "dependencies": {"lodash": "^4.17.0"}}
    lock = {"lockfileVersion": 1, "dependencies": {"lodash": {"version": "4.17.21"}}}
    repo = make_repo(tmp_path, package, json.dumps(lock), "npm-shrinkwrap.json")

    assert parse_manifest(repo).by_name("lodash").locked_version == "4.17.21"


def test_yarn_lock_parses_quoted_scoped_and_comma_keys(tmp_path):
    package = {
        "name": "demo",
        "version": "1.0.0",
        "dependencies": {"react": "^18.2.0", "@scope/pkg": "^1.0.0"},
    }
    lock = (
        '"@scope/pkg@^1.0.0", "@scope/pkg@^1.1.0":\n'
        '  version "1.2.3"\n'
        'react@^18.2.0:\n'
        '  version "18.3.1"\n'
    )
    repo = make_repo(tmp_path, package, lock, "yarn.lock")
    manifest = parse_manifest(repo)

    assert manifest.by_name("react").locked_version == "18.3.1"
    assert manifest.by_name("@scope/pkg").locked_version == "1.2.3"
    assert parse_lockfile(repo).kind == "yarn"


def test_pnpm_lock_parses_scoped_and_v9_snapshot_keys(tmp_path):
    package = {
        "name": "demo",
        "version": "1.0.0",
        "dependencies": {"react": "^18.2.0", "@scope/pkg": "^1.0.0", "lodash": "^4.17.0"},
    }
    lock = (
        "lockfileVersion: '9.0'\n"
        "packages:\n"
        "  /react@18.3.1:\n"
        "    resolution: {integrity: sha512-example}\n"
        "  /@scope/pkg@1.2.3:\n"
        "    resolution: {integrity: sha512-example}\n"
        "snapshots:\n"
        "  lodash@4.17.21:\n"
        "    dependencies: {}\n"
    )
    repo = make_repo(tmp_path, package, lock, "pnpm-lock.yaml")
    manifest = parse_manifest(repo)

    assert manifest.by_name("react").locked_version == "18.3.1"
    assert manifest.by_name("@scope/pkg").locked_version == "1.2.3"
    assert manifest.by_name("lodash").locked_version == "4.17.21"
    assert parse_lockfile(repo).kind == "pnpm"


def test_missing_lockfile_leaves_versions_unlocked(tmp_path):
    package = {"name": "demo", "version": "1.0.0", "dependencies": {"react": "^18.2.0"}}

    repo = make_repo(tmp_path, package)
    assert parse_lockfile(repo) is None
    assert parse_manifest(repo).by_name("react").locked_version is None


def test_missing_package_json_raises(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    with pytest.raises(FileNotFoundError):
        parse_manifest(repo)


def test_non_object_package_json_raises(tmp_path):
    repo = tmp_path / "invalid"
    write_file(repo, "package.json", "[]")
    with pytest.raises(ValueError):
        parse_manifest(repo)


def test_deeply_nested_npm_lockfile_raises_controlled_error(tmp_path):
    depth = 600
    body = (
        '{"packages":{}, "dependencies":'
        + '{"a":{"dependencies":' * depth
        + "{}"
        + "}}" * depth
        + "}"
    )
    repo = tmp_path / "repo"
    write_file(
        repo,
        "package.json",
        json.dumps({"name": "demo", "version": "1.0.0", "dependencies": {"a": "^1.0.0"}}),
    )
    write_file(repo, "package-lock.json", body)

    t0 = time.monotonic()
    with pytest.raises(impactprism.manifest.LockfileParseError) as excinfo:
        impactprism.manifest.parse_lockfile(repo)
    assert time.monotonic() - t0 < 10

    assert excinfo.value.cause is not None
    assert isinstance(excinfo.value.cause, budgets.ScannerBudgetError)
    assert not isinstance(excinfo.value.cause, RecursionError)

    manifest = impactprism.manifest.parse_manifest(repo)
    assert manifest.by_name("a").locked_version is None


def test_oversized_lockfile_raises_controlled_error(tmp_path, monkeypatch):
    monkeypatch.setattr(budgets, "MAX_JSON_BYTES", 64)
    repo = tmp_path / "repo"
    write_file(repo, "package.json", json.dumps({"name": "demo", "version": "1.0.0"}))
    write_file(
        repo,
        "package-lock.json",
        json.dumps({"name": "demo", "version": "1.0.0", "packages": {}, "dependencies": {}}),
    )

    t0 = time.monotonic()
    with pytest.raises(impactprism.manifest.LockfileParseError) as excinfo:
        impactprism.manifest.parse_lockfile(repo)
    assert time.monotonic() - t0 < 10
    assert isinstance(excinfo.value.cause, budgets.ScannerBudgetError)


def test_deeply_nested_package_json_raises_controlled_error(tmp_path):
    depth = 600
    body = (
        '{"name":"demo","version":"1.0.0","dependencies":'
        + '{"a":' * depth
        + "{}"
        + "}" * depth
        + "}"
    )
    repo = tmp_path / "repo"
    write_file(repo, "package.json", body)

    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError):
        impactprism.manifest.parse_manifest(repo)
    assert time.monotonic() - t0 < 10


def test_dependencies_nesting_cap_controlled(tmp_path, monkeypatch):
    monkeypatch.setattr(budgets, "MAX_NESTING_DEPTH", 8)
    depth = 12
    body = (
        '{"packages":{}, "dependencies":'
        + '{"a":{"dependencies":' * depth
        + "{}"
        + "}}" * depth
        + "}"
    )
    repo = tmp_path / "repo"
    write_file(
        repo,
        "package.json",
        json.dumps({"name": "demo", "version": "1.0.0", "dependencies": {"a": "^1.0.0"}}),
    )
    write_file(repo, "package-lock.json", body)

    t0 = time.monotonic()
    with pytest.raises(impactprism.manifest.LockfileParseError) as excinfo:
        impactprism.manifest.parse_lockfile(repo)
    assert time.monotonic() - t0 < 10
    assert isinstance(excinfo.value.cause, budgets.ScannerBudgetError)
    assert excinfo.value.cause.budget_name == "nesting"


def test_workspace_match_cap_controlled(tmp_path, monkeypatch):
    monkeypatch.setattr(budgets, "MAX_WORKSPACE_MATCHES", 3)
    repo = tmp_path / "repo"
    write_file(
        repo,
        "package.json",
        json.dumps({"name": "root", "version": "1.0.0", "workspaces": ["packages/*"]}),
    )
    for index in range(4):
        write_file(
            repo,
            os.path.join("packages", f"pkg{index}", "package.json"),
            json.dumps({"name": f"pkg{index}", "version": "1.0.0"}),
        )

    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        impactprism.manifest.discover_workspaces(str(repo))
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "workspace_matches"


def test_pnpm_workspace_yaml_discovers_included_and_excluded_packages(tmp_path):
    repo = tmp_path / "repo"
    write_file(
        repo,
        "package.json",
        json.dumps({"name": "root", "version": "1.0.0"}),
    )
    write_file(
        repo,
        "pnpm-workspace.yaml",
        "packages:\n  - 'packages/*'\n  - '!packages/ignored'\n",
    )
    write_file(
        repo,
        "packages/app/package.json",
        json.dumps({"name": "app", "version": "1.0.0"}),
    )
    write_file(
        repo,
        "packages/ignored/package.json",
        json.dumps({"name": "ignored", "version": "1.0.0"}),
    )

    discovered = impactprism.manifest.discover_workspaces(str(repo))

    assert [path.name for path in discovered] == ["app"]
