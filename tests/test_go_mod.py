import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from impactprism.go_mod import (
    GoModuleEntry,
    GoManifest,
    GoMod,
    GoReplace,
    GoRequire,
    GoWork,
    ResolvedImport,
    VendorInfo,
    parse_go_manifest,
    parse_go_mod,
    parse_go_sum,
    parse_go_work,
    parse_vendor_modules,
)


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_go_mod_require_lines(tmp_path):
    path = write_file(
        tmp_path,
        "go.mod",
        "module example.com/app\ngo 1.22\nrequire example.com/direct v1.2.3\nrequire example.com/indirect v1.0.0 // indirect\n",
    )
    assert parse_go_mod(path) == GoMod(
        "example.com/app",
        "1.22",
        [GoRequire("example.com/direct", "v1.2.3", False), GoRequire("example.com/indirect", "v1.0.0", True)],
        [],
    )


def test_parse_go_mod_blocks_and_replaces(tmp_path):
    path = write_file(
        tmp_path,
        "go.mod",
        "module example.com/app\nrequire (\n example.com/direct v1.0.0\n example.com/indirect v1.1.0 // indirect\n)\n"
        "replace example.com/a v1.0.0 => example.com/b v2.0.0\nreplace (\n example.com/c => example.com/d v1.0.1\n)\n",
    )
    assert parse_go_mod(path).requires == [
        GoRequire("example.com/direct", "v1.0.0", False),
        GoRequire("example.com/indirect", "v1.1.0", True),
    ]
    assert parse_go_mod(path).replaces == [
        GoReplace("example.com/a", "v1.0.0", "example.com/b", "v2.0.0", None),
        GoReplace("example.com/c", None, "example.com/d", "v1.0.1", None),
    ]


def test_parse_relative_local_replace(tmp_path):
    path = write_file(tmp_path, "go.mod", "module example.com/app\nreplace example.com/dep => ./local/dep\n")
    local_dir = (tmp_path / "local" / "dep").resolve()
    assert parse_go_mod(path).replaces == [GoReplace("example.com/dep", None, None, None, str(local_dir))]


def test_parse_go_sum(tmp_path):
    path = write_file(
        tmp_path,
        "go.sum",
        "example.com/a v1.0.0 h1:aaa\nexample.com/a v1.0.0/go.mod h1:bbb\nexample.com/b v2.0.0 h1:ccc\n",
    )
    assert parse_go_sum(path) == {
        "example.com/a@v1.0.0": {"h1": "h1:aaa", "go.mod": "h1:bbb"},
        "example.com/b@v2.0.0": {"h1": "h1:ccc"},
    }


def test_parse_go_work(tmp_path):
    path = write_file(
        tmp_path,
        "go.work",
        "go 1.22\nuse (\n ./one\n ./two\n)\nrequire example.com/work v1.0.0 // indirect\nreplace (\n example.com/dep => ./local\n)\n",
    )
    assert parse_go_work(path) == GoWork(
        "1.22",
        [(tmp_path / "one").resolve(), (tmp_path / "two").resolve()],
        [GoRequire("example.com/work", "v1.0.0", True)],
        [GoReplace("example.com/dep", None, None, None, str((tmp_path / "local").resolve()))],
    )


def test_parse_vendor_modules(tmp_path):
    path = write_file(
        tmp_path,
        "vendor/modules.txt",
        "# example.com/a v1.0.0\n## explicit\nexample.com/a/pkg\n"
        "# example.com/b v2.0.0 => example.com/c v3.0.0\n## explicit; go 1.22\nexample.com/b/pkg\n",
    )
    assert parse_vendor_modules(path) == VendorInfo(
        [
            GoModuleEntry("example.com/a", "v1.0.0", True, "vendor", None),
            GoModuleEntry(
                "example.com/b",
                "v2.0.0",
                True,
                "vendor",
                GoReplace("example.com/b", "v2.0.0", "example.com/c", "v3.0.0", None),
            ),
        ],
        "1.22",
    )


def test_manifest_workspace_vendor_and_resolution(tmp_path):
    write_file(
        tmp_path,
        "go.mod",
        "module example.com/app\ngo 1.21\nrequire (\n example.com/a v1.0.0\n example.com/long v1.0.0 // indirect\n)\nreplace example.com/a => example.com/old v1.0.0\n",
    )
    write_file(tmp_path, "go.sum", "example.com/a v1.0.0 h1:aaa\n")
    write_file(tmp_path, "go.work", "go 1.22\nuse ./tool\nreplace example.com/a => ./local\n")
    write_file(tmp_path, "tool/go.mod", "module example.com/tool\ngo 1.22\nrequire example.com/long/nested v2.0.0\n")
    write_file(tmp_path, "local/go.mod", "module example.com/a\n")
    write_file(tmp_path, "vendor/modules.txt", "# example.com/vendor v1.0.0\n## explicit; go 1.22\nexample.com/vendor/pkg\n")
    manifest = parse_go_manifest(tmp_path)

    assert manifest.main_module == "example.com/app"
    assert manifest.go_version == "1.21"
    assert manifest.is_vendored is True
    assert manifest.versions["example.com/a"] == str((tmp_path / "local").resolve())
    assert manifest.resolve_import_path("fmt") is None
    assert manifest.resolve_import_path("example.com/missing") is None
    assert manifest.resolve_import_path("example.com/long/nested/pkg") == ResolvedImport(
        "example.com/long/nested",
        "v2.0.0",
        "module",
        None,
        "go.mod",
        True,
    )
    assert manifest.resolve_import_path("example.com/a/pkg") == ResolvedImport(
        "example.com/a",
        None,
        "local",
        (tmp_path / "local").resolve(),
        "go.mod",
        True,
    )
    assert manifest.resolve_import_path("example.com/vendor/pkg") == ResolvedImport(
        "example.com/vendor",
        "v1.0.0",
        "vendor",
        (tmp_path / "vendor" / "example.com" / "vendor").resolve(),
        "vendor",
        True,
    )


def test_manifest_missing_go_mod_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_go_manifest(tmp_path)


def test_go_work_single_line_use_escape_ignored(tmp_path):
    repo = tmp_path / "repo"
    sentinel = tmp_path / "sentinel"
    write_file(repo, "go.mod", "module example.com/app\n")
    write_file(repo, "go.work", "go 1.22\nuse ../sentinel\n")
    write_file(sentinel, "go.mod", "module example.com/sentinel\n")

    assert parse_go_work(repo / "go.work").use_dirs == []

    manifest = parse_go_manifest(repo)
    assert not any(entry.module_path == "example.com/sentinel" for entry in manifest.modules)
    assert manifest.resolve_import_path("example.com/sentinel/pkg") is None


def test_go_work_block_use_escape_ignored(tmp_path):
    repo = tmp_path / "repo"
    sentinel = tmp_path / "sentinel"
    write_file(repo, "go.mod", "module example.com/app\n")
    write_file(repo, "go.work", "go 1.22\nuse (\n ../sentinel\n ./tool\n)\n")
    write_file(repo, "tool/go.mod", "module example.com/tool\n")
    write_file(sentinel, "go.mod", "module example.com/sentinel\n")

    use_dirs = parse_go_work(repo / "go.work").use_dirs
    assert use_dirs == [(repo / "tool").resolve()]
    assert (repo / "sentinel").resolve() not in use_dirs

    manifest = parse_go_manifest(repo)
    assert not any(entry.module_path == "example.com/sentinel" for entry in manifest.modules)
    assert any(entry.module_path == "example.com/tool" for entry in manifest.modules)


def test_local_replace_escaping_repo_ignored(tmp_path):
    repo = tmp_path / "repo"
    write_file(
        repo,
        "go.mod",
        "module example.com/app\nrequire example.com/x v1.0.0\nreplace example.com/x => ../outside\n",
    )

    manifest = parse_go_manifest(repo)

    assert all(
        replacement.old_path != "example.com/x" or replacement.local_dir is None
        for replacement in manifest.replaces
    )
    x_entry = next(entry for entry in manifest.modules if entry.module_path == "example.com/x")
    assert x_entry.replaced_by is None
    resolved = manifest.resolve_import_path("example.com/x/pkg")
    assert resolved is not None
    assert resolved.root_dir is None


def test_vendor_local_replace_escaping_repo_ignored(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo, "go.mod", "module example.com/app\n")
    write_file(
        repo,
        "vendor/modules.txt",
        "# example.com/x v1.0.0 => ../../outside\n## explicit; go 1.22\nexample.com/x\n",
    )

    vendor = parse_vendor_modules(repo / "vendor" / "modules.txt")
    vendor_entry = vendor.modules[0]
    assert vendor_entry.replaced_by is None

    manifest = parse_go_manifest(repo)
    entry = next(entry for entry in manifest.modules if entry.module_path == "example.com/x")
    assert entry.replaced_by is None
    resolved = manifest.resolve_import_path("example.com/x/pkg")
    assert resolved is not None
    assert resolved.root_dir == (repo / "vendor" / "example.com" / "x").resolve()
