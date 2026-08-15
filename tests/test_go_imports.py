import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from impactprism import budgets
from impactprism.go_imports import (
    GoImport,
    GoImportGraph,
    PackageEdge,
    build_import_graph,
    parse_go_source,
    scan_go_imports,
)


def module_paths(imports):
    return [item.module_path for item in imports]


def kinds_and_names(imports):
    return [(item.kind, item.name) for item in imports]


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, go_mod="module example.com/app\n\ngo 1.21\n", files=None):
    repo = tmp_path / "repo"
    write_file(repo, "go.mod", go_mod)
    for relpath, content in (files or {}).items():
        write_file(repo, relpath, content)
    return repo


def test_parse_single_import():
    result = parse_go_source('import "fmt"\n', Path("main.go"))
    assert module_paths(result) == ["fmt"]
    assert result[0].kind == "normal"
    assert result[0].name is None


def test_parse_alias_underscore_dot():
    src = (
        'import alias "example.com/a"\n'
        'import _ "example.com/b"\n'
        'import . "example.com/c"\n'
    )
    result = parse_go_source(src, Path("main.go"))
    assert module_paths(result) == ["example.com/a", "example.com/b", "example.com/c"]
    assert kinds_and_names(result) == [
        ("alias", "alias"),
        ("underscore", "_"),
        ("dot", "."),
    ]


def test_parse_grouped_multiline_imports():
    src = (
        "import (\n"
        '    "fmt"\n'
        '    alias "example.com/a"\n'
        '    _ "example.com/b"\n'
        '    . "example.com/c"\n'
        '    "net/http"\n'
        ")\n"
    )
    result = parse_go_source(src, Path("main.go"))
    assert module_paths(result) == ["fmt", "example.com/a", "example.com/b", "example.com/c", "net/http"]
    assert kinds_and_names(result) == [
        ("normal", None),
        ("alias", "alias"),
        ("underscore", "_"),
        ("dot", "."),
        ("normal", None),
    ]


def test_parse_imports_in_comments_strings_raw_ignored():
    src = (
        '// import "fake1"\n'
        '/* import "fake2" */\n'
        'var s = "import \\"fake3\\""\n'
        "var r = `import \"fake4\"`\n"
        'import "real"\n'
    )
    result = parse_go_source(src, Path("main.go"))
    assert module_paths(result) == ["real"]


def test_parse_trailing_comments_on_import_lines():
    src = (
        'import "fmt" // stdlib\n'
        'import (\n'
        '    alias "example.com/a" // group trailing\n'
        '    "example.com/b"\n'
        ")\n"
    )
    result = parse_go_source(src, Path("main.go"))
    assert module_paths(result) == ["fmt", "example.com/a", "example.com/b"]


def test_parse_import_keyword_in_strings_and_larger_identifiers():
    src = (
        'var a = "import not-import"\n'
        'var b = `import not-import-raw`\n'
        "var c = something_import\n"
        'import "real"\n'
    )
    result = parse_go_source(src, Path("main.go"))
    assert module_paths(result) == ["real"]


def test_parse_malformed_never_raises():
    bad_sources = [
        "import\n",
        "import (\n",
        'import (\n  "unclosed"\n',
        'import "fmt" "garbage"\n',
        "import alias\n",
        "import 12345\n",
        "var x = import\n",
        "import /* no path */\n",
        'import alias /* comment */ "path"\n',
        "",
        "import)\n",
    ]
    for source in bad_sources:
        result = parse_go_source(source, Path("main.go"))
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, GoImport)


def test_scan_go_imports_finds_only_go_files_skips_vendor_and_dots(tmp_path):
    repo = tmp_path / "repo"
    (repo / "cmd" / "app").mkdir(parents=True)
    write_file(repo, "cmd/app/main.go", 'import "fmt"\n')
    write_file(repo, "internal/util/util.go", 'import "os"\n')
    write_file(repo, "vendor/github.com/foo/bar/baz.go", 'import "evil"\n')
    write_file(repo, "vendor/modules.txt", "# example.com/x v1.0.0\n")
    write_file(repo, ".cache/evil.go", 'import "evil2"\n')
    write_file(repo, ".git/config.go", 'import "evil3"\n')
    write_file(repo, "notes.txt", 'import "txt"\n')
    write_file(repo, "ignored.go.txt", 'import "txt2"\n')
    write_file(repo, ".hidden.go", 'import "evil4"\n')
    result = scan_go_imports(str(repo))
    assert set(result) == {repo / "cmd" / "app" / "main.go", repo / "internal" / "util" / "util.go"}
    assert module_paths(result[repo / "cmd" / "app" / "main.go"]) == ["fmt"]
    for path in result:
        assert path.is_absolute()


def test_scan_go_imports_missing_directory(tmp_path):
    assert scan_go_imports(str(tmp_path / "missing")) == {}


def test_scan_go_imports_file_count_budget(tmp_path):
    repo = tmp_path / "repo"
    (repo / "cmd").mkdir(parents=True)
    for index in range(45):
        write_file(repo, os.path.join("cmd", f"file{index}.go"), "package main\n")
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_go_imports(str(repo), max_files=20)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "files"


def test_scan_go_imports_depth_budget(tmp_path):
    repo = tmp_path / "repo"
    current = repo
    for index in range(30):
        current = current / f"level{index}"
        write_file(current, "a.go", "package a\n")
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_go_imports(str(repo), max_depth=10)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "depth"


def test_scan_go_imports_file_byte_budget(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo, "big.go", "x" * (3 * 1024 * 1024))
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_go_imports(str(repo), max_file_bytes=1024)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "file_bytes"


def test_scan_go_imports_timeout_budget(tmp_path):
    repo = tmp_path / "repo"
    (repo / "cmd").mkdir(parents=True)
    for index in range(3):
        write_file(repo, os.path.join("cmd", f"f{index}.go"), "package main\n")
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_go_imports(str(repo), max_seconds=0.0)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "seconds"


def test_stdlib_imports_classified_separately(tmp_path):
    repo = make_repo(tmp_path)
    write_file(repo, "main.go", 'import (\n\t"fmt"\n\t"net/http"\n)\n')
    graph = build_import_graph(str(repo))
    assert isinstance(graph, GoImportGraph)
    assert set(graph.stdlib_imports) == {"fmt", "net/http"}
    assert graph.unresolved == []
    assert graph.package_edges == []


def test_internal_imports_resolve_to_main_module(tmp_path):
    repo = make_repo(tmp_path)
    write_file(repo, "pkg/other.go", "package pkg\n")
    write_file(repo, "main.go", 'import (\n\t"example.com/app/pkg"\n)\n')
    graph = build_import_graph(str(repo))
    assert len(graph.package_edges) == 1
    edge = graph.package_edges[0]
    assert edge.import_path == "example.com/app/pkg"
    assert edge.resolved is not None
    assert edge.resolved.module_path == "example.com/app"
    assert graph.unresolved == []
    assert graph.stdlib_imports == []


def test_longest_prefix_module_matching(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "vendor/modules.txt": (
                "# example.com/x v1.0.0\n"
                "## explicit; go 1.21\n"
                "example.com/x\n"
            ),
            "vendor/example.com/x/pkg.go": "package x\n",
            "main.go": (
                'import (\n'
                '\t"example.com/x/y"\n'
                '\t"example.com/x/y/z"\n'
                '\t"example.com/unmatched"\n'
                ")\n"
            ),
        },
    )
    graph = build_import_graph(str(repo))
    by_path = {edge.import_path: edge for edge in graph.package_edges}
    assert isinstance(by_path["example.com/x/y"], PackageEdge)
    assert by_path["example.com/x/y"].resolved is not None
    assert by_path["example.com/x/y"].resolved.module_path == "example.com/x"
    assert by_path["example.com/x/y"].resolved.kind == "vendor"
    assert by_path["example.com/x/y/z"].resolved.module_path == "example.com/x"
    assert by_path["example.com/unmatched"].resolved is None
    assert "example.com/unmatched" in graph.unresolved
    assert "example.com/x/y" not in graph.unresolved


def test_replace_resolution_module_to_module(tmp_path):
    repo = make_repo(
        tmp_path,
        go_mod=(
            "module example.com/app\n"
            "\n"
            "go 1.21\n"
            "\n"
            "require example.com/old v1.0.0\n"
            "\n"
            "replace example.com/old => example.com/new v1.2.3\n"
        ),
        files={"main.go": 'import (\n\t"example.com/old/pkg"\n)\n'},
    )
    graph = build_import_graph(str(repo))
    assert len(graph.package_edges) == 1
    resolved = graph.package_edges[0].resolved
    assert resolved is not None
    assert resolved.module_path == "example.com/new"
    assert resolved.version == "v1.2.3"
    assert resolved.kind == "module"
    assert graph.unresolved == []


def test_replace_resolution_module_to_local_dir(tmp_path):
    repo = make_repo(
        tmp_path,
        go_mod=(
            "module example.com/app\n"
            "\n"
            "go 1.21\n"
            "\n"
            "require example.com/locdep v0.0.0\n"
            "\n"
            "replace example.com/locdep => ./local\n"
        ),
        files={
            "local/thing.go": "package local\n",
            "main.go": 'import (\n\t"example.com/locdep/sub"\n)\n',
        },
    )
    graph = build_import_graph(str(repo))
    assert len(graph.package_edges) == 1
    resolved = graph.package_edges[0].resolved
    assert resolved is not None
    assert resolved.kind == "local"
    assert resolved.module_path == "example.com/locdep"
    assert resolved.root_dir is not None
    assert Path(resolved.root_dir) == (repo / "local").resolve()
    assert graph.unresolved == []


def test_vendored_fixture_resolves_with_kind_vendor(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "vendor/modules.txt": (
                "# example.com/dep v0.5.0\n"
                "## explicit; go 1.21\n"
                "example.com/dep\n"
                "# example.com/trans v0.1.0\n"
                "example.com/trans\n"
            ),
            "vendor/example.com/dep/pkg.go": "package dep\n",
            "main.go": (
                'import (\n'
                '\t"example.com/dep"\n'
                '\t"example.com/trans/x"\n'
                ")\n"
            ),
        },
    )
    graph = build_import_graph(str(repo))
    edges = {edge.import_path: edge.resolved for edge in graph.package_edges}
    dep = edges["example.com/dep"]
    assert dep is not None
    assert dep.module_path == "example.com/dep"
    assert dep.kind == "vendor"
    assert dep.version == "v0.5.0"
    trans = edges["example.com/trans/x"]
    assert trans is not None
    assert trans.module_path == "example.com/trans"
    assert trans.kind == "vendor"
    assert graph.module_usage["example.com/dep"].direct is True
    assert graph.module_usage["example.com/trans"].direct is False
    assert graph.module_usage["example.com/dep"].used is True


def test_module_usage_direct_used_indirect_used_unused(tmp_path):
    repo = make_repo(
        tmp_path,
        files={
            "vendor/modules.txt": (
                "# example.com/directdep v1.0.0\n"
                "## explicit; go 1.21\n"
                "example.com/directdep\n"
                "# example.com/indirectdep v2.0.0\n"
                "example.com/indirectdep\n"
                "# example.com/unuseddep v3.0.0\n"
                "## explicit; go 1.21\n"
                "example.com/unuseddep\n"
            ),
            "vendor/example.com/directdep/d.go": "package directdep\n",
            "vendor/example.com/indirectdep/i.go": "package indirectdep\n",
            "main.go": (
                'import (\n'
                '\t"example.com/directdep"\n'
                '\t"example.com/indirectdep"\n'
                ")\n"
            ),
        },
    )
    graph = build_import_graph(str(repo))
    direct_used = {usage.module_path for usage in graph.directly_used_modules()}
    indirect_used = {usage.module_path for usage in graph.indirectly_used_modules()}
    unused = {usage.module_path for usage in graph.declared_unused_modules()}
    assert "example.com/directdep" in direct_used
    assert "example.com/indirectdep" in indirect_used
    assert "example.com/unuseddep" in unused
    assert "example.com/directdep" not in unused
    assert "example.com/indirectdep" not in direct_used

    usage = graph.module_usage["example.com/directdep"]
    assert usage.direct is True
    assert usage.used is True
    assert usage.import_count == 1
    assert usage.importing_files == [repo / "main.go"]
    assert usage.importing_packages == [repo]
