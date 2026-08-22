import base64
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from impactprism.analysis import (
    _declared_dependencies,
    cross_check,
    generate_sbom,
    main,
    scan_imports,
)
from impactprism.version import __version__


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, name="repo", deps=None, dev_deps=None, versions=None, files=None):
    repo = tmp_path / name
    (repo / "src").mkdir(parents=True, exist_ok=True)
    package_json = {"name": name, "version": "1.0.0"}
    if deps:
        package_json["dependencies"] = deps
    if dev_deps:
        package_json["devDependencies"] = dev_deps
    write_file(repo, "package.json", json.dumps(package_json, indent=2))
    if versions is not None:
        packages = {"": {"name": name, "version": "1.0.0"}}
        dependencies = {}
        for dep, version in versions.items():
            packages["node_modules/" + dep] = {"version": version}
            dependencies[dep] = {"version": version}
        write_file(
            repo,
            "package-lock.json",
            json.dumps(
                {
                    "name": name,
                    "version": "1.0.0",
                    "lockfileVersion": 3,
                    "packages": packages,
                    "dependencies": dependencies,
                },
                indent=2,
            ),
        )
    for relpath, content in (files or {}).items():
        write_file(repo, relpath, content)
    return repo


def _make_clean_repo(tmp_path):
    return make_repo(
        tmp_path,
        "clean",
        deps={"react": "18.2.0"},
        files={"src/App.jsx": "import React from 'react';\n"},
    )


def _make_undeclared_repo(tmp_path):
    return make_repo(
        tmp_path,
        "undeclared",
        deps={"react": "^18.2.0"},
        files={
            "src/App.jsx": "import React from 'react';\n",
            "src/use.js": "import _ from 'lodash';\n",
        },
    )


def _make_drift_repo(tmp_path):
    return make_repo(
        tmp_path,
        "drift",
        deps={"react": "^18.2.0", "lodash": "^4.17.21"},
        files={"src/App.jsx": "import React from 'react';\n"},
    )


def _make_no_source_repo(tmp_path):
    return make_repo(
        tmp_path,
        "nosrc",
        deps={"react": "^18.2.0"},
    )


def _make_peer_optional_repo(tmp_path):
    repo = make_repo(
        tmp_path,
        "peeroptional",
        deps={"react": "18.2.0"},
        dev_deps={"eslint": "^8.0.0"},
        files={
            "src/index.js": (
                "import React from 'react';\n"
                "import eslint from 'eslint';\n"
                "import ReactDOM from 'react-dom';\n"
                "import fsevents from 'fsevents';\n"
            ),
        },
    )
    package_json = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    package_json["peerDependencies"] = {"react-dom": "^18.2.0"}
    package_json["optionalDependencies"] = {"fsevents": "^2.3.2"}
    write_file(repo, "package.json", json.dumps(package_json, indent=2))
    return repo, package_json


def _component(sbom, name):
    return next(c for c in sbom["components"] if c["name"] == name)


def test_generate_sbom_structure(tmp_path):
    repo = make_repo(
        tmp_path,
        "app",
        deps={"react": "^18.2.0", "@scope/hooks": "^1.0.0", "lodash": "^4.17.21"},
        dev_deps={"eslint": "^8.0.0"},
        versions={"react": "18.3.1", "@scope/hooks": "1.4.2"},
        files={"src/App.jsx": "import React from 'react';\n"},
    )
    sbom = generate_sbom(str(repo))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["version"] == 1
    assert sbom["metadata"]["component"]["type"] == "application"
    assert sbom["metadata"]["component"]["name"] == "app"
    assert sbom["metadata"]["component"]["version"] == "1.0.0"
    assert sbom["metadata"]["timestamp"].endswith("+00:00")
    assert sbom["metadata"]["tools"][0]["vendor"] == "impactprism"
    assert sbom["metadata"]["tools"][0]["name"] == "impactprism-cyclonedx"
    assert sbom["metadata"]["tools"][0]["version"] == __version__
    assert isinstance(sbom["components"], list)
    names = [c["name"] for c in sbom["components"]]
    assert [c["purl"] for c in sbom["components"]] == sorted(
        c["purl"] for c in sbom["components"]
    )
    assert set(names) == {"react", "hooks", "lodash", "eslint"}
    assert _component(sbom, "react")["type"] == "library"
    assert _component(sbom, "react")["version"] == "18.3.1"
    assert _component(sbom, "react")["purl"] == "pkg:npm/react@18.3.1"
    assert _component(sbom, "react")["scope"] == "required"
    assert (
        _component(sbom, "hooks")["bom-ref"]
        == "pkg:npm/%40scope/hooks@1.4.2"
    )
    assert _component(sbom, "hooks")["group"] == "@scope"
    assert _component(sbom, "hooks")["purl"] == "pkg:npm/%40scope/hooks@1.4.2"
    assert _component(sbom, "hooks")["scope"] == "required"
    assert _component(sbom, "eslint")["scope"] == "optional"


def test_legacy_analyze_applies_exclusions_to_python_repositories(tmp_path, capsys):
    repo = tmp_path / "python-repo"
    write_file(repo, "pyproject.toml", "[project]\nname = 'python-repo'\nversion = '1.0.0'\n")
    write_file(repo, "src/main.py", "import requests\n")
    write_file(repo, "fixtures/case.py", "import hidden_dependency\n")

    assert main([str(repo), "--exclude", "fixtures", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)

    assert report["imported"] == ["requests"]


def test_generate_sbom_fixture_contains_all_declared_components_and_root_edges(
    sbom_fixture_repo,
):
    sbom = generate_sbom(str(sbom_fixture_repo))

    assert {
        (component.get("group"), component["name"], component["version"])
        for component in sbom["components"]
    } == {
        ("@fixture", "core", "2.3.1"),
        (None, "lodash", "4.17.21"),
        (None, "tap", "18.2.0"),
    }

    root_dependency = next(
        dependency
        for dependency in sbom["dependencies"]
        if dependency["ref"] == "sbom-fixture@1.0.0"
    )
    assert root_dependency["dependsOn"] == [
        "pkg:npm/%40fixture/core@2.3.1",
        "pkg:npm/lodash@4.17.21",
        "pkg:npm/tap@18.2.0",
    ]


def test_generate_sbom_npm_integrity_hash(tmp_path):
    digest = hashlib.sha512(b"some-constant").digest()
    integrity = "sha512-" + base64.b64encode(digest).decode("ascii")
    repo = make_repo(
        tmp_path,
        "app",
        deps={"react": "^18.2.0"},
        versions={"react": "18.3.1"},
    )
    lockfile_path = repo / "package-lock.json"
    lockfile = json.loads(lockfile_path.read_text(encoding="utf-8"))
    lockfile["packages"]["node_modules/react"]["integrity"] = integrity
    write_file(repo, "package-lock.json", json.dumps(lockfile, indent=2))

    sbom = generate_sbom(str(repo))
    assert _component(sbom, "react")["hashes"] == [
        {"alg": "SHA-512", "content": digest.hex()}
    ]


def test_generate_sbom_version_from_lockfile(tmp_path):
    repo = make_repo(
        tmp_path,
        "app",
        deps={"react": "^18.2.0"},
        versions={"react": "18.3.1"},
    )
    sbom = generate_sbom(str(repo))
    assert _component(sbom, "react")["version"] == "18.3.1"

    repo_no_lock = make_repo(
        tmp_path,
        "app2",
        deps={"react": "^18.2.0"},
    )
    sbom_no_lock = generate_sbom(str(repo_no_lock))
    assert _component(sbom_no_lock, "react")["version"] == "^18.2.0"


def test_generate_sbom_shrinkwrap_fallback(tmp_path):
    repo = make_repo(
        tmp_path,
        "app",
        deps={"react": "^18.2.0"},
    )
    # Write npm-shrinkwrap.json instead of package-lock.json
    packages = {"": {"name": "app", "version": "1.0.0"}}
    packages["node_modules/react"] = {"version": "18.3.1"}
    dependencies = {"react": {"version": "18.3.1"}}
    write_file(
        repo,
        "npm-shrinkwrap.json",
        json.dumps(
            {
                "name": "app",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "packages": packages,
                "dependencies": dependencies,
            },
            indent=2,
        ),
    )
    sbom = generate_sbom(str(repo))
    assert _component(sbom, "react")["version"] == "18.3.1"


def test_generate_sbom_yarn_berry_lockfile(tmp_path):
    repo = make_repo(
        tmp_path,
        "yarn-app",
        deps={"react": "^18.2.0", "@scope/pkg": "^1.0.0"},
        files={
            "src/App.jsx": "import React from 'react';\nimport { hooks } from '@scope/pkg';\n",
            "yarn.lock": (
                "__metadata:\n"
                "  version: 6\n"
                "  cacheKey: 8\n"
                "\n"
                '"react@npm:^18.2.0":\n'
                "  version: 18.3.1\n"
                '  resolution: "react@npm:18.3.1"\n'
                "\n"
                '"@scope/pkg@npm:^1.0.0":\n'
                "  version: 1.2.3\n"
                '  resolution: "@scope/pkg@npm:1.2.3"\n'
            ),
        },
    )
    sbom = generate_sbom(str(repo))
    assert _component(sbom, "react")["version"] == "18.3.1"
    assert _component(sbom, "pkg")["version"] == "1.2.3"
    assert _component(sbom, "react")["purl"] == "pkg:npm/react@18.3.1"
    assert _component(sbom, "react")["scope"] == "required"
    assert (
        _component(sbom, "pkg")["purl"]
        == "pkg:npm/%40scope/pkg@1.2.3"
    )


def test_generate_sbom_pnpm_lockfile(tmp_path):
    repo = make_repo(
        tmp_path,
        "pnpm-app",
        deps={"react": "^18.2.0", "lodash": "^4.17.0"},
        files={
            "src/App.jsx": "import React from 'react';\nimport _ from 'lodash';\n",
            "pnpm-lock.yaml": (
                "lockfileVersion: '9.0'\n"
                "packages:\n"
                "  /react@18.3.1:\n"
                "    resolution: {integrity: sha512-example}\n"
                "  /lodash@4.17.21:\n"
                "    resolution: {integrity: sha512-example}\n"
                "snapshots:\n"
                "  react@18.3.1:\n"
                "    dependencies: {}\n"
                "  lodash@4.17.21:\n"
                "    dependencies: {}\n"
            ),
        },
    )
    sbom = generate_sbom(str(repo))
    assert _component(sbom, "react")["version"] == "18.3.1"
    assert _component(sbom, "lodash")["version"] == "4.17.21"


def test_generate_sbom_npm_lockfile_wins_over_yarn(tmp_path):
    repo = make_repo(
        tmp_path,
        "priority-app",
        deps={"react": "^18.2.0"},
        versions={"react": "19.0.0"},
        files={
            "src/App.jsx": "import React from 'react';\n",
            "yarn.lock": (
                "__metadata:\n"
                "  version: 6\n"
                "\n"
                '"react@npm:^18.2.0":\n'
                "  version: 18.3.1\n"
                '  resolution: "react@npm:18.3.1"\n'
            ),
        },
    )
    sbom = generate_sbom(str(repo))
    assert _component(sbom, "react")["version"] == "19.0.0"


def test_generate_sbom_missing_package_json(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        generate_sbom(str(empty))


def test_scan_imports_esm_variants(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "src/App.jsx": (
                "import React from 'react';\n"
                "import { useState } from 'react-dom';\n"
                "import * as d3 from 'd3';\n"
                "import { hooks } from '@scope/hooks';\n"
                "import _ from 'lodash/map';\n"
                "import 'bootstrap';\n"
            ),
        },
    )
    imported = scan_imports(str(repo))
    assert imported == {"react", "react-dom", "d3", "@scope/hooks", "lodash", "bootstrap"}


def test_scan_imports_commonjs(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "index.js": "const _ = require('lodash');\nconst path = require('path');\nconst fs = require(\"fs\");\n",
        },
    )
    imported = scan_imports(str(repo))
    assert imported == {"lodash"}


def test_scan_imports_dynamic_import(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "src/app.js": (
                "const a = await import('@scope/hooks');\n"
                "const b = import('dayjs');\n"
                "const c = import('./local');\n"
                "const d = import('node:fs');\n"
            ),
        },
    )
    imported = scan_imports(str(repo))
    assert imported == {"@scope/hooks", "dayjs"}


def test_scan_imports_builtin_and_relative_filtering(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "src/app.js": (
                "import fs from 'node:fs';\n"
                "const path = require('node:path');\n"
                "import promisified from 'node:fs/promises';\n"
                "import os from 'os';\n"
                "import x from './local';\n"
                "import y from '../other';\n"
                "import z from '/absolute/pkg';\n"
            ),
        },
    )
    imported = scan_imports(str(repo))
    assert imported == set()


def test_scan_imports_skips_node_modules_and_dot_dirs(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "src/App.jsx": "import React from 'react';\n",
            "node_modules/evil/index.js": "import hack from 'evil-pkg';\n",
            ".git/hooks.js": "import git from 'git-hook-pkg';\n",
            ".cache/x.js": "import cache from 'cache-pkg';\n",
            "notes.txt": "import txt from 'txt-pkg';\n",
        },
    )
    imported = scan_imports(str(repo))
    assert imported == {"react"}


def test_scan_imports_skips_build_dist_coverage_public(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "src/App.jsx": "import React from 'react';\n",
            "build/bundle.js": "import build from 'build-pkg';\n",
            "dist/main.js": "import dist from 'dist-pkg';\n",
            "coverage/coverage.js": "import cov from 'cov-pkg';\n",
            "public/app.js": "import pub from 'pub-pkg';\n",
        },
    )
    imported = scan_imports(str(repo))
    assert imported == {"react"}


def test_scan_imports_reduces_subpaths_to_package_root(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "src/app.js": (
                "import x from 'lodash/map';\n"
                "import y from 'react-dom/client';\n"
                "import z from '@scope/hooks/lib';\n"
            ),
        },
    )
    imported = scan_imports(str(repo))
    assert imported == {"lodash", "react-dom", "@scope/hooks"}


def test_cross_check_drift_and_undeclared():
    result = cross_check({"react", "lodash"}, {"react", "dayjs"})
    assert result["drift"] == ["lodash"]
    assert result["undeclared"] == ["dayjs"]
    assert result["declared_count"] == 2
    assert result["imported_count"] == 2
    assert result["matched_count"] == 1


def test_cross_check_sorted_and_counts():
    result = cross_check({"z", "a", "m"}, {"a", "b"})
    assert result["drift"] == ["m", "z"]
    assert result["undeclared"] == ["b"]
    assert result["declared_count"] == 3
    assert result["imported_count"] == 2
    assert result["matched_count"] == 1


def test_main_exit_codes(tmp_path):
    assert main([str(_make_clean_repo(tmp_path))]) == 0
    assert main([str(_make_undeclared_repo(tmp_path))]) == 1
    assert main([str(_make_drift_repo(tmp_path))]) == 1
    assert main([str(_make_no_source_repo(tmp_path))]) == 1

    missing = tmp_path / "missing"
    assert main([str(missing)]) == 2


def test_main_no_flags_no_files_written(tmp_path):
    repo = _make_clean_repo(tmp_path)
    # Snapshot existing files before running main
    files_before = {f.relative_to(repo) for f in repo.rglob("*") if f.is_file()}
    code = main([str(repo)])
    assert code == 0
    assert not (repo / "sbom.cyclonedx.json").is_file()
    assert not (repo / "sbom-report.json").is_file()
    # Assert no new files were written
    files_after = {f.relative_to(repo) for f in repo.rglob("*") if f.is_file()}
    assert files_before == files_after


def test_main_sbom_flag_writes_sbom(tmp_path):
    repo = _make_drift_repo(tmp_path)
    sbom_path = tmp_path / "out.cyclonedx.json"
    code = main([str(repo), "--sbom", str(sbom_path)])
    assert code == 1
    assert sbom_path.is_file()
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert "react" in [c["name"] for c in sbom["components"]]
    assert "lodash" in [c["name"] for c in sbom["components"]]


def test_main_report_flag_writes_report(tmp_path):
    repo = _make_undeclared_repo(tmp_path)
    report_path = tmp_path / "out-report.json"
    code = main([str(repo), "--report", str(report_path)])
    assert code == 1
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "repo" in report
    assert "package_name" in report
    assert "package_version" in report
    assert "declared" in report
    assert "imported" in report
    assert "drift" in report
    assert "undeclared" in report
    assert report["undeclared"] == ["lodash"]
    assert report["drift"] == []


def test_main_json_flag_prints_report(tmp_path, capsys):
    repo = _make_drift_repo(tmp_path)
    code = main([str(repo), "--json"])
    assert code == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert "repo" in report
    assert "package_name" in report
    assert "package_version" in report
    assert "declared" in report
    assert "imported" in report
    assert "drift" in report
    assert "undeclared" in report
    assert report["drift"] == ["lodash"]
    assert report["undeclared"] == []
    assert report["sbom"]["bomFormat"] == "CycloneDX"
    assert report["sbom"]["specVersion"] == "1.6"


def test_main_both_flags_writes_both_files(tmp_path):
    repo = _make_clean_repo(tmp_path)
    sbom_path = tmp_path / "out.cyclonedx.json"
    report_path = tmp_path / "out-report.json"
    code = main([str(repo), "--sbom", str(sbom_path), "--report", str(report_path)])
    assert code == 0
    assert sbom_path.is_file()
    assert report_path.is_file()
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["drift"] == []
    assert report["undeclared"] == []


def test_main_clean_repo_exit_0(tmp_path):
    repo = _make_clean_repo(tmp_path)
    assert main([str(repo)]) == 0


def test_main_undeclared_repo_exit_1(tmp_path):
    repo = _make_undeclared_repo(tmp_path)
    assert main([str(repo)]) == 1


def test_main_drift_repo_exit_1(tmp_path):
    repo = _make_drift_repo(tmp_path)
    assert main([str(repo)]) == 1


def test_main_no_source_repo_exit_1(tmp_path):
    repo = _make_no_source_repo(tmp_path)
    assert main([str(repo)]) == 1


def test_main_missing_dir_exit_2(tmp_path):
    missing = tmp_path / "missing"
    assert main([str(missing)]) == 2


def test_declared_dependencies_includes_peer_and_optional(tmp_path):
    repo, package_json = _make_peer_optional_repo(tmp_path)
    declared = _declared_dependencies(package_json)
    assert set(declared) == {"react", "eslint", "react-dom", "fsevents"}


def test_main_peer_and_optional_deps_no_undeclared(tmp_path, capsys):
    repo, _package_json = _make_peer_optional_repo(tmp_path)
    code = main([str(repo), "--json"])
    assert code == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["undeclared"] == []
    assert report["drift"] == []
    components = {c["name"]: c for c in report["sbom"]["components"]}
    assert components["react"]["scope"] == "required"
    assert components["eslint"]["scope"] == "optional"
    assert components["react-dom"]["scope"] == "optional"
    assert components["fsevents"]["scope"] == "optional"


def test_import_outside_all_groups_flagged_undeclared(tmp_path, capsys):
    repo = make_repo(
        tmp_path,
        "undeclaredoutside",
        deps={"react": "18.2.0"},
        files={
            "src/index.js": (
                "import React from 'react';\n"
                "import _ from 'lodash';\n"
            ),
        },
    )
    code = main([str(repo), "--json"])
    assert code == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["undeclared"] == ["lodash"]
    assert report["drift"] == []


def test_generate_go_sbom_roots_imported_indirect_modules(tmp_path):
    repo = tmp_path / "go-app"
    write_file(
        repo,
        "go.mod",
        "module example.com/app\n\ngo 1.21\n\nrequire example.com/dep v1.2.3 // indirect\n",
    )
    write_file(
        repo,
        "main.go",
        'package main\n\nimport "example.com/dep/pkg"\n\nfunc main() { pkg.Run() }\n',
    )

    sbom = generate_sbom(str(repo))
    purl = "pkg:golang/example.com/dep@v1.2.3"
    root = next(item for item in sbom["dependencies"] if item["ref"] == "example.com/app@0.0.0")
    assert root["dependsOn"] == [purl]
    component = _component(sbom, "dep")
    assert {item["value"] for item in component["properties"] if item["name"] == "impactprism:direct"} == {"false"}
