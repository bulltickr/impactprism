import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from impactprism import budgets
from impactprism.imports import ImportRecord, parse_imports, scan_imports
from impactprism.js_ast import Node, parse


def specifiers(records):
    return [record.specifier for record in records]


def kinds(records):
    return [record.kind for record in records]


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_returns_module_ast():
    node = parse("const x = 1;\n")
    assert isinstance(node, Node)
    assert node.type == "Module"
    assert any(child.type == "VariableDeclaration" for child in node.children)


def test_ast_import_node_types_and_source():
    node = parse("import a from 'x';\nconst r = require('y');\nconst d = import('z');\n")
    types = {child.type for child in node.children}
    assert "ImportDeclaration" in types
    assert "VariableDeclaration" in types

    def walk(ast_node):
        yield ast_node
        for child in ast_node.children:
            yield from walk(child)

    all_nodes = list(walk(node))
    assert any(n.type == "ImportExpression" for n in all_nodes)
    call = next(n for n in all_nodes if n.type == "CallExpression")
    assert call.children[0].type == "Identifier"
    assert call.children[0].name == "require"
    import_node = next(child for child in node.children if child.type == "ImportDeclaration")
    source = next(child for child in import_node.children if child.type == "StringLiteral")
    assert source.source == "x"


def test_esm_default_named_namespace_side_effect():
    src = (
        "import React from 'react';\n"
        "import { useState } from 'react-dom';\n"
        "import * as d3 from 'd3';\n"
        "import { hooks } from '@scope/hooks';\n"
        "import _ from 'lodash/map';\n"
        "import 'bootstrap';\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["react", "react-dom", "d3", "@scope/hooks", "lodash/map", "bootstrap"]
    assert kinds(records) == ["esm"] * 6


def test_esm_multiline_and_variants():
    src = (
        "import {\n"
        "  a,\n"
        "  b as c,\n"
        "} from 'pkg-a';\n"
        "import d, { e } from 'pkg-b';\n"
        "import type { T } from 'pkg-c';\n"
        "import * as ns from 'pkg-d';\n"
        "import type * as T2 from 'pkg-e';\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["pkg-a", "pkg-b", "pkg-c", "pkg-d", "pkg-e"]
    assert kinds(records) == ["esm"] * 5


def test_export_from_and_export_all():
    src = (
        "export { x } from 'pkg-a';\n"
        "export { y as z } from 'pkg-b';\n"
        "export * from 'pkg-c';\n"
        "export * as ns from 'pkg-d';\n"
        "export type { T } from 'pkg-e';\n"
        "export const local = 1;\n"
        "export default function f() {}\n"
        "export interface Other { x: 1 }\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["pkg-a", "pkg-b", "pkg-c", "pkg-d", "pkg-e"]
    assert kinds(records) == ["esm"] * 5


def test_cjs_require():
    src = "const a = require('pkg-a');\nconst b = require(\"pkg-b\");\nconst c = require('pkg-c');\n"
    records = parse_imports(src)
    assert specifiers(records) == ["pkg-a", "pkg-b", "pkg-c"]
    assert kinds(records) == ["cjs"] * 3


def test_dynamic_import_and_await():
    src = (
        "const a = import('pkg-a');\n"
        "const b = await import('pkg-b');\n"
        "async function f() { return await import('pkg-c'); }\n"
        "Promise.all([import('pkg-d'), import('pkg-d')]);\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["pkg-a", "pkg-b", "pkg-c", "pkg-d", "pkg-d"]
    assert kinds(records) == ["dynamic"] * 5


def test_non_literal_dynamic_module_names_are_not_guessed():
    records = parse_imports(
        "const name = 'pkg-a';\n"
        "import(name);\n"
        "require(name);\n"
    )

    assert records == []


def test_false_positives_in_comments_strings_templates_ignored():
    src = (
        "// import a from 'a';\n"
        "/* import b from 'b'; */\n"
        "const s = \"require('b')\";\n"
        "const t = 'import c from \"c\"';\n"
        "const u = `import d from 'd'`;\n"
        "const v = `text ${x} import e from 'e'`;\n"
        "const w = `require('f')`;\n"
        "// require('g');\n"
    )
    records = parse_imports(src)
    assert records == []


def test_template_interpolation_expressions_are_parsed():
    src = "const t = `before ${require('inside')} after`;\n"
    records = parse_imports(src)
    assert specifiers(records) == ["inside"]
    assert kinds(records) == ["cjs"]


def test_non_literal_require_and_import_ignored():
    src = (
        "const x = require(variable);\n"
        "const y = import(someVar);\n"
        "const z = require(compute(1));\n"
    )
    records = parse_imports(src)
    assert records == []


def test_ts_surface_parses_and_finds_imports():
    src = (
        "import React from 'react';\n"
        "interface Props {\n"
        "  a: string;\n"
        "  b?: number;\n"
        "  c: { d: boolean };\n"
        "}\n"
        "type Maybe<T> = T | null;\n"
        "const x: number = 1;\n"
        "function f<T extends { a: string }>(p: T, q?: string): number {\n"
        "  return 1;\n"
        "}\n"
        "const g = (h: Props): void => {};\n"
        "const el = foo as Props;\n"
        "enum Color { Red, Green }\n"
        "const y = generic<number>(1);\n"
        "import { util } from 'lodash';\n"
        "export interface Other { x: 1 }\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["react", "lodash"]


def test_require_named_user_function_definition_creates_no_imports():
    src = (
        "function require(name) { return name; }\n"
        "const require = function(x) {};\n"
        "const require = (x) => x;\n"
    )
    records = parse_imports(src)
    assert records == []


def test_no_dedup_multiple_same_module():
    src = (
        "import a from 'pkg';\n"
        "import b from 'pkg';\n"
        "const c = require('pkg');\n"
        "import('pkg');\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["pkg", "pkg", "pkg", "pkg"]
    assert kinds(records) == ["esm", "esm", "cjs", "dynamic"]


def test_record_positions_in_source_order():
    src = "import a from 'pkg-a';\nconst x = require('pkg-b');\nimport('pkg-c');\n"
    records = parse_imports(src)
    assert specifiers(records) == ["pkg-a", "pkg-b", "pkg-c"]
    starts = [record.start for record in records]
    assert starts == sorted(starts)
    for record in records:
        assert 0 <= record.start < record.end <= len(src)
        assert isinstance(record, ImportRecord)


def test_imports_inside_function_and_control_flow_found():
    src = (
        "function a() { require('inside-fn'); }\n"
        "if (cond) {\n"
        "  import('inside-if');\n"
        "}\n"
        "switch (x) {\n"
        "  case 1:\n"
        "    require('inside-case');\n"
        "    break;\n"
        "}\n"
    )
    records = parse_imports(src)
    assert specifiers(records) == ["inside-fn", "inside-if", "inside-case"]


def test_malformed_source_never_raises():
    bad_sources = [
        "import { x\n",
        "const = ;;;;\n",
        "function (\n",
        "if (\n",
        "export { a from\n",
        "const x = `unterminated\n",
        "const y = 'unterminated\n",
        "} }\n",
        "type X = <\n",
        "import\n",
        "export\n",
        "(() => {\n",
        "import a from 'x'\nconst b = require('y');\n",
        "const obj = { a: },\n",
        "const r = /unterminated\n",
        "class C { constructor( { }\n",
    ]
    for source in bad_sources:
        records = parse_imports(source)
        assert isinstance(records, list)


def test_scan_imports_skips_ignored_dirs_and_non_source(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    write_file(repo, "src/app.js", "import a from 'real-a';\n")
    for directory in ("node_modules", "build", "dist", "coverage", "public", ".cache"):
        write_file(repo, os.path.join(directory, "evil.js"), "import x from 'evil';\n")
    write_file(repo, "notes.txt", "import t from 'txt-pkg';\n")
    write_file(repo, ".hidden.js", "import h from 'hidden-pkg';\n")
    result = scan_imports(str(repo))
    assert set(result) == {repo / "src" / "app.js"}
    assert specifiers(result[repo / "src" / "app.js"]) == ["real-a"]


def test_scan_imports_all_source_extensions(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    sources = {
        "src/a.js": "import a from 'a';\n",
        "src/b.jsx": "import b from 'b';\n",
        "src/c.ts": "import c from 'c';\n",
        "src/d.tsx": "import d from 'd';\n",
        "src/e.mjs": "import e from 'e';\n",
        "src/f.cjs": "const f = require('f');\n",
        "src/empty.js": "const nothing = 1;\n",
    }
    for relpath, content in sources.items():
        write_file(repo, relpath, content)
    result = scan_imports(str(repo))
    assert set(result) == {repo / relpath for relpath in sources}
    assert specifiers(result[repo / "src" / "f.cjs"]) == ["f"]
    assert result[repo / "src" / "empty.js"] == []


def test_scan_imports_no_dedup_across_file(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    write_file(repo, "src/a.js", "import x from 'dup';\nimport y from 'dup';\n")
    write_file(repo, "src/b.js", "import z from 'dup';\n")
    result = scan_imports(str(repo))
    combined = []
    for path in sorted(result):
        combined.extend(specifiers(result[path]))
    assert combined == ["dup", "dup", "dup"]


def test_scan_imports_missing_directory(tmp_path):
    assert scan_imports(str(tmp_path / "missing")) == {}


def test_scan_imports_file_count_budget(tmp_path):
    repo = tmp_path / "repo"
    for index in range(45):
        write_file(
            repo,
            os.path.join("src", f"dir{index % 5}", f"file{index}.js"),
            "import x from 'x';\n",
        )
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_imports(str(repo), max_files=20)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "files"


def test_scan_imports_depth_budget(tmp_path):
    repo = tmp_path / "repo"
    current = repo
    for index in range(30):
        current = current / f"level{index}"
        write_file(current, "a.js", "import x from 'x';\n")
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_imports(str(repo), max_depth=10)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "depth"


def test_scan_imports_file_byte_budget(tmp_path):
    repo = tmp_path / "repo"
    write_file(repo, os.path.join("src", "big.js"), "x" * (3 * 1024 * 1024))
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_imports(str(repo), max_file_bytes=1024)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "file_bytes"


def test_scan_imports_timeout_budget(tmp_path):
    repo = tmp_path / "repo"
    for index in range(3):
        write_file(repo, os.path.join("src", f"f{index}.js"), "import x from 'x';\n")
    t0 = time.monotonic()
    with pytest.raises(budgets.ScannerBudgetError) as excinfo:
        scan_imports(str(repo), max_seconds=0.0)
    assert time.monotonic() - t0 < 10
    assert excinfo.value.budget_name == "seconds"
