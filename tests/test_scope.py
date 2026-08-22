import json

import pytest

from impactprism.scope import is_excluded_directory, normalize_excludes
from impactprism.scan_service import scan_repository
from impactprism.go_imports import scan_go_imports
from impactprism.imports import scan_imports
from impactprism.python_imports import scan_imports as scan_python_imports


def test_normalize_excludes_supports_names_and_relative_prefixes():
    assert normalize_excludes(
        ["tests", "./cmd\\fiximports\\testdata", "generated", "tests"]
    ) == frozenset({"tests", "cmd/fiximports/testdata", "generated"})


@pytest.mark.parametrize("value", ["../outside", "/absolute", "C:\\absolute", "."])
def test_normalize_excludes_rejects_unsafe_paths(value):
    with pytest.raises(ValueError):
        normalize_excludes([value])


def test_is_excluded_directory_matches_names_and_prefixes(tmp_path):
    repo = tmp_path / "repo"
    specific = repo / "cmd" / "fiximports" / "testdata" / "nested"
    unrelated = repo / "other" / "testdata" / "nested"
    specific.mkdir(parents=True)
    unrelated.mkdir(parents=True)

    excludes = normalize_excludes(["cmd/fiximports/testdata"])
    assert is_excluded_directory(repo, specific, excludes)
    assert not is_excluded_directory(repo, unrelated, excludes)
    assert is_excluded_directory(repo, unrelated, normalize_excludes(["testdata"]))


def test_is_excluded_directory_rejects_paths_outside_repository(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()

    assert is_excluded_directory(repo, outside, normalize_excludes(["fixtures"]))


def test_scan_repository_applies_path_exclusion_and_reports_scope(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "cmd" / "fiximports" / "testdata").mkdir(parents=True)
    (repo / "other" / "testdata").mkdir(parents=True)
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "scope-demo",
                "version": "1.0.0",
                "dependencies": {"react": "18.2.0"},
            }
        ),
        encoding="utf-8",
    )
    (repo / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "scope-demo", "version": "1.0.0"},
                    "node_modules/react": {"version": "18.2.0"},
                },
            }
        ),
        encoding="utf-8",
    )
    (repo / "src" / "index.js").write_text(
        "import React from 'react';\n", encoding="utf-8"
    )
    (repo / "cmd" / "fiximports" / "testdata" / "case.js").write_text(
        "import hiddenFromExcludedTree from 'excluded-only';\n", encoding="utf-8"
    )
    (repo / "other" / "testdata" / "case.js").write_text(
        "import visibleFinding from 'outside-excluded-tree';\n", encoding="utf-8"
    )

    result = scan_repository(
        repo,
        ecosystem="npm",
        excludes={r"cmd\fiximports\testdata"},
    )

    packages = {finding["package"] for finding in result.findings}
    assert "excluded-only" not in packages
    assert "outside-excluded-tree" in packages
    assert result.report["scope"] == {
        "mode": "repository",
        "root": ".",
        "exclude": ["cmd/fiximports/testdata"],
        "exclude_matching": "directory-name-or-relative-prefix",
    }


def test_all_source_scanners_honor_relative_prefix_exclusions(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "cmd" / "fiximports" / "testdata").mkdir(parents=True)
    (repo / "src" / "index.js").write_text("import visible from 'visible';\n", encoding="utf-8")
    (repo / "cmd" / "fiximports" / "testdata" / "case.js").write_text(
        "import hidden from 'hidden';\n", encoding="utf-8"
    )
    js_sources = scan_imports(repo, exclude={"cmd/fiximports/testdata"})
    assert all("fiximports" not in str(path) for path in js_sources)

    (repo / "src" / "module.py").write_text("import visible_python\n", encoding="utf-8")
    (repo / "cmd" / "fiximports" / "testdata" / "case.py").write_text(
        "import hidden_python\n", encoding="utf-8"
    )
    python_sources = scan_python_imports(repo, exclude={"cmd/fiximports/testdata"})
    assert all("fiximports" not in str(path) for path in python_sources)

    (repo / "go.mod").write_text("module example.com/scope\n\ngo 1.22\n", encoding="utf-8")
    (repo / "src" / "main.go").write_text(
        'package main\n\nimport "example.com/visible"\n', encoding="utf-8"
    )
    (repo / "cmd" / "fiximports" / "testdata" / "case.go").write_text(
        'package fixture\n\nimport "example.com/hidden"\n', encoding="utf-8"
    )
    go_sources = scan_go_imports(repo, exclude={"cmd/fiximports/testdata"})
    assert all("fiximports" not in str(path) for path in go_sources)
