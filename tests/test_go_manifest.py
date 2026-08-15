import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from impactprism.go_manifest import (
    GoSumEntry,
    ReplaceRule,
    VendorModule,
    detect_vendor,
    parse_go_manifest,
    parse_go_mod_text,
    parse_go_sum,
    parse_go_work,
    parse_vendor_modules,
)

MINIMAL_GO_MOD = (
    "module example.com/demo\n"
    "\n"
    "go 1.22\n"
    "\n"
    "require github.com/google/uuid v1.6.0\n"
)

BLOCK_GO_MOD = (
    "module example.com/demo\n"
    "go 1.22\n"
    "\n"
    "require (\n"
    "\tgithub.com/foo/bar v1.0.0 // indirect\n"
    "\tgithub.com/baz/qux v2.1.0\n"
    ")\n"
)


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, go_mod=None, go_work=None, go_sum=None, vendor_modules=None):
    repo = tmp_path / "repo"
    if go_mod is not None:
        write_file(repo, "go.mod", go_mod)
    if go_work is not None:
        write_file(repo, "go.work", go_work)
    if go_sum is not None:
        write_file(repo, "go.sum", go_sum)
    if vendor_modules is not None:
        write_file(repo, os.path.join("vendor", "modules.txt"), vendor_modules)
    return repo


def test_minimal_go_mod_parses_dependency(tmp_path):
    repo = make_repo(tmp_path, go_mod=MINIMAL_GO_MOD)
    manifest = parse_go_manifest(repo)

    assert manifest.module_path == "example.com/demo"
    assert manifest.go_version == "1.22"
    assert manifest.toolchain is None
    assert manifest.go_mod_path == repo / "go.mod"
    dependency = manifest.dependency("github.com/google/uuid")
    assert dependency.version == "v1.6.0"
    assert dependency.indirect is False
    assert dependency.direct is True
    assert manifest.dependency_names() == {"github.com/google/uuid"}
    assert manifest.dependency("missing") is None


def test_require_block_indirect_entry(tmp_path):
    repo = make_repo(tmp_path, go_mod=BLOCK_GO_MOD)
    manifest = parse_go_manifest(repo)

    indirect = manifest.dependency("github.com/foo/bar")
    direct = manifest.dependency("github.com/baz/qux")
    assert indirect.indirect is True
    assert indirect.direct is False
    assert direct.indirect is False
    assert direct.direct is True


def test_multi_module_single_line_require():
    go_mod_path = Path("go.mod")
    manifest = parse_go_mod_text(
        "module example.com/demo\n"
        "go 1.22\n"
        "require github.com/a/mod v1.0.0 github.com/b/mod v1.1.0\n",
        go_mod_path,
    )

    assert manifest.module_path == "example.com/demo"
    assert manifest.go_version == "1.22"
    assert len(manifest.dependencies) == 2
    assert manifest.dependencies[0].module == "github.com/a/mod"
    assert manifest.dependencies[0].version == "v1.0.0"
    assert manifest.dependencies[0].indirect is False
    assert manifest.dependencies[1].module == "github.com/b/mod"
    assert manifest.dependencies[1].version == "v1.1.0"


def test_toolchain_parsed(tmp_path):
    go_mod = (
        "module example.com/demo\n"
        "go 1.22\n"
        "toolchain go1.22.5\n"
        "require github.com/google/uuid v1.6.0\n"
    )
    repo = make_repo(tmp_path, go_mod=go_mod)
    manifest = parse_go_manifest(repo)

    assert manifest.toolchain == "go1.22.5"
    assert manifest.go_version == "1.22"


def test_all_replace_forms(tmp_path):
    go_mod = (
        "module example.com/demo\n"
        "go 1.22\n"
        "replace (\n"
        "\told.example.com/one => github.com/new/one v1.2.3\n"
        "\told.example.com/two v1.0.0 => github.com/new/two v2.0.0\n"
        "\told.example.com/three => ../local/three\n"
        "\told.example.com/four v3.1.0 => ../local/four\n"
        ")\n"
        "replace single.example.com/old => github.com/single/new v0.9.0\n"
    )
    repo = make_repo(tmp_path, go_mod=go_mod)
    manifest = parse_go_manifest(repo)

    assert len(manifest.replaces) == 5
    module_rule = manifest.replaces[0]
    assert isinstance(module_rule, ReplaceRule)
    assert module_rule.old == "old.example.com/one"
    assert module_rule.old_version is None
    assert module_rule.new == "github.com/new/one"
    assert module_rule.new_version == "v1.2.3"
    assert module_rule.local is False

    versioned = manifest.replaces[1]
    assert versioned.old == "old.example.com/two"
    assert versioned.old_version == "v1.0.0"
    assert versioned.new == "github.com/new/two"
    assert versioned.new_version == "v2.0.0"
    assert versioned.local is False

    local_rule = manifest.replaces[2]
    assert local_rule.old == "old.example.com/three"
    assert local_rule.old_version is None
    assert local_rule.new == "../local/three"
    assert local_rule.new_version is None
    assert local_rule.local is True

    versioned_local = manifest.replaces[3]
    assert versioned_local.old == "old.example.com/four"
    assert versioned_local.old_version == "v3.1.0"
    assert versioned_local.new == "../local/four"
    assert versioned_local.new_version is None
    assert versioned_local.local is True

    single = manifest.replaces[4]
    assert single.old == "single.example.com/old"
    assert single.new == "github.com/single/new"
    assert single.new_version == "v0.9.0"
    assert single.local is False


def test_replaced_dependency_and_replacement_for(tmp_path):
    go_mod = (
        "module example.com/demo\n"
        "go 1.22\n"
        "require old.example.com/foo v1.0.0\n"
        "replace old.example.com/foo => github.com/new/foo v1.5.0\n"
    )
    repo = make_repo(tmp_path, go_mod=go_mod)
    manifest = parse_go_manifest(repo)

    dependency = manifest.dependency("old.example.com/foo")
    assert dependency.replaced is True
    assert dependency.replacement == "github.com/new/foo v1.5.0"
    assert dependency.replacement_local is False
    assert manifest.replacement_for("old.example.com/foo") == "github.com/new/foo v1.5.0"
    assert manifest.replacement_for("missing.example.com/x") is None


def test_local_replaced_dependency_is_local(tmp_path):
    go_mod = (
        "module example.com/demo\n"
        "go 1.22\n"
        "require old.example.com/local v1.0.0\n"
        "replace old.example.com/local => ../vendor/local\n"
    )
    repo = make_repo(tmp_path, go_mod=go_mod)
    manifest = parse_go_manifest(repo)

    dependency = manifest.dependency("old.example.com/local")
    assert dependency.replaced is True
    assert dependency.replacement == "../vendor/local"
    assert dependency.replacement_local is True


def test_go_work_missing_returns_none(tmp_path):
    repo = make_repo(tmp_path, go_mod=MINIMAL_GO_MOD)
    assert parse_go_work(repo) is None


def test_go_work_parses_use_and_replaces(tmp_path):
    go_work = (
        "go 1.22\n"
        "\n"
        "use (\n"
        "\t./services/auth\n"
        "\t./services/api\n"
        ")\n"
        "\n"
        "use ./cmd/app\n"
        "\n"
        "replace (\n"
        "\told.example.com/a => github.com/new/a v1.0.0\n"
        ")\n"
        "replace old.example.com/b => ../local/b\n"
    )
    repo = make_repo(tmp_path, go_work=go_work)
    work = parse_go_work(repo)

    assert work.go_version == "1.22"
    assert work.toolchain is None
    assert work.uses == ["./services/auth", "./services/api", "./cmd/app"]
    assert len(work.replaces) == 2
    assert work.replaces[0].old == "old.example.com/a"
    assert work.replaces[0].new == "github.com/new/a"
    assert work.replaces[0].new_version == "v1.0.0"
    assert work.replaces[1].old == "old.example.com/b"
    assert work.replaces[1].new == "../local/b"
    assert work.replaces[1].local is True
    assert work.go_work_path == repo / "go.work"


def test_go_sum_parses_zip_and_mod_hash_lines(tmp_path):
    go_sum = (
        "github.com/google/uuid v1.6.0 h1:firsthash\n"
        "github.com/google/uuid v1.6.0/go.mod h1:secondhash\n"
        "github.com/foo/bar v0.0.0-20240101000000-abcdef123 h1:thirdhash\n"
        "\n"
        "// a comment line\n"
    )
    repo = make_repo(tmp_path, go_sum=go_sum)
    entries = parse_go_sum(repo)

    assert len(entries) == 3
    assert entries[0] == GoSumEntry("github.com/google/uuid", "v1.6.0", False, "h1:firsthash")
    assert entries[1].module == "github.com/google/uuid"
    assert entries[1].version == "v1.6.0"
    assert entries[1].is_mod_hash is True
    assert entries[1].hash == "h1:secondhash"
    assert entries[2].module == "github.com/foo/bar"
    assert entries[2].version == "v0.0.0-20240101000000-abcdef123"
    assert entries[2].is_mod_hash is False


def test_go_sum_missing_returns_empty(tmp_path):
    repo = make_repo(tmp_path, go_mod=MINIMAL_GO_MOD)
    assert parse_go_sum(repo) == []


def test_detect_vendor_absent_and_present(tmp_path):
    repo = make_repo(tmp_path, go_mod=MINIMAL_GO_MOD)
    assert detect_vendor(repo) is False

    write_file(repo, os.path.join("vendor", "modules.txt"), "# github.com/foo/bar v1.0.0\n")
    assert detect_vendor(repo) is True


def test_parse_vendor_modules_absent_returns_none(tmp_path):
    repo = make_repo(tmp_path, go_mod=MINIMAL_GO_MOD)
    assert parse_vendor_modules(repo) is None


def test_parse_vendor_modules_explicit_and_deps_of(tmp_path):
    modules = (
        "# github.com/foo/bar v1.2.3\n"
        "## explicit; go 1.21\n"
        "\tgithub.com/foo/bar\n"
        "\tgithub.com/foo/bar/baz\n"
        "\n"
        "# github.com/baz/qux v0.4.0\n"
        "## deps of github.com/foo/bar\n"
        "\tgithub.com/baz/qux\n"
        "\tgithub.com/baz/qux/pkg\n"
        "\n"
        "# github.com/plain/mod v1.0.0\n"
        "## explicit\n"
        "\tgithub.com/plain/mod\n"
    )
    repo = make_repo(tmp_path, vendor_modules=modules)
    vendor = parse_vendor_modules(repo)

    assert vendor is not None
    assert len(vendor) == 3
    explicit = vendor[0]
    assert isinstance(explicit, VendorModule)
    assert explicit.module == "github.com/foo/bar"
    assert explicit.version == "v1.2.3"
    assert explicit.explicit is True
    assert explicit.packages == ["github.com/foo/bar", "github.com/foo/bar/baz"]

    implicit = vendor[1]
    assert implicit.module == "github.com/baz/qux"
    assert implicit.version == "v0.4.0"
    assert implicit.explicit is False
    assert implicit.packages == ["github.com/baz/qux", "github.com/baz/qux/pkg"]

    plain = vendor[2]
    assert plain.module == "github.com/plain/mod"
    assert plain.explicit is True
    assert plain.packages == ["github.com/plain/mod"]


def test_exclude_and_retract_skipped(tmp_path):
    go_mod = (
        "module example.com/demo\n"
        "go 1.22\n"
        "require github.com/google/uuid v1.6.0\n"
        "exclude (\n"
        "\tgithub.com/bad/old v1.0.0\n"
        ")\n"
        "retract v1.0.0\n"
    )
    repo = make_repo(tmp_path, go_mod=go_mod)
    manifest = parse_go_manifest(repo)

    assert manifest.dependency("github.com/bad/old") is None
    assert manifest.dependency("github.com/google/uuid") is not None


def test_missing_go_mod_raises(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    with pytest.raises(FileNotFoundError):
        parse_go_manifest(repo)
