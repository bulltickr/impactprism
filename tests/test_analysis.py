import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import cross_check, generate_sbom, main, scan_imports


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
    assert sbom["specVersion"] == "1.5"
    assert sbom["version"] == 1
    assert sbom["metadata"]["component"]["type"] == "application"
    assert sbom["metadata"]["component"]["name"] == "app"
    assert sbom["metadata"]["component"]["version"] == "1.0.0"
    assert sbom["metadata"]["timestamp"].endswith("Z")
    assert sbom["metadata"]["tools"] == [
        {"vendor": "impactprism", "name": "impactprism-analysis", "version": "0.1.0"}
    ]
    assert isinstance(sbom["components"], list)
    names = [c["name"] for c in sbom["components"]]
    assert names == sorted(names)
    assert set(names) == {"react", "@scope/hooks", "lodash", "eslint"}
    assert _component(sbom, "react")["type"] == "library"
    assert _component(sbom, "react")["version"] == "18.3.1"
    assert _component(sbom, "react")["purl"] == "pkg:npm/react@18.3.1"
    assert _component(sbom, "@scope/hooks")["purl"] == "pkg:npm/%40scope%2Fhooks@1.4.2"


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
    assert sbom["specVersion"] == "1.5"
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
