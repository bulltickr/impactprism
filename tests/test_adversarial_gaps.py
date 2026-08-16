"""Executable probes for high-impact gaps found during adversarial review.

These are intentionally strict xfails: each test describes the safety or
classification invariant the implementation should satisfy, while preserving
the current audit baseline until the production fix is made.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from impactprism.drift import analyze_repo
from impactprism.manifest import parse_lockfile


def _load_action_module():
    path = ROOT / "action" / "run.py"
    spec = importlib.util.spec_from_file_location("impactprism_adversarial_action", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_malformed_package_json_must_not_classify_clean(tmp_path):
    (tmp_path / "package.json").write_text("{broken", encoding="utf-8")
    findings = analyze_repo(str(tmp_path), ecosystem="npm").findings
    assert findings
    assert any(
        finding.finding_type.name == "SCANNER_ERROR" for finding in findings
    )


def test_malformed_lockfile_must_not_disappear_from_classification(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"a": "1.0.0"}}), encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "index.js").write_text("import 'a';", encoding="utf-8")
    findings = analyze_repo(str(tmp_path), ecosystem="npm")
    assert any(
        finding.finding_type.name == "LOCKFILE_MANIFEST_MISMATCH"
        for finding in findings
    )
    assert not any(
        finding.finding_type.name == "MISSING_LOCKFILE" for finding in findings
    )


def test_locked_version_outside_npm_range_is_reported(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"a": "^1.0.0"}}), encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/a": {"version": "2.0.0"}}}),
        encoding="utf-8",
    )
    (tmp_path / "index.js").write_text("import 'a';", encoding="utf-8")
    assert any(
        finding.finding_type.name == "LOCKFILE_MANIFEST_MISMATCH"
        for finding in analyze_repo(str(tmp_path), ecosystem="npm")
    )


def test_yarn_berry_lockfile_resolves_dependency_version(tmp_path):
    (tmp_path / "yarn.lock").write_text(
        '"a@npm:^1.0.0":\n  version: 1.0.0\n', encoding="utf-8"
    )
    lockfile = parse_lockfile(tmp_path)
    assert lockfile is not None
    assert lockfile.resolved_versions == {"a": "1.0.0"}


def test_npm_workspace_dependency_is_not_reported_as_root_undeclared(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"workspaces": ["packages/*"], "dependencies": {}}),
        encoding="utf-8",
    )
    workspace = tmp_path / "packages" / "app"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"dependencies": {"real": "1.0.0"}}), encoding="utf-8"
    )
    (workspace / "index.js").write_text("import 'real';", encoding="utf-8")
    assert not any(
        finding.package == "real"
        and finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        for finding in analyze_repo(str(tmp_path), ecosystem="npm")
    )


def test_go_replacement_target_is_not_reported_undeclared(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\ngo 1.20\n\n"
        "require old.example.com/foo v1.0.0\n"
        "replace old.example.com/foo => new.example.com/foo v1.2.0\n",
        encoding="utf-8",
    )
    (tmp_path / "main.go").write_text(
        'package main\nimport _ "old.example.com/foo/pkg"\nfunc main() {}\n',
        encoding="utf-8",
    )
    assert not any(
        finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        for finding in analyze_repo(str(tmp_path), ecosystem="go")
    )


def test_legacy_scanner_ignores_import_text_in_comments_and_strings(tmp_path):
    from impactprism import analysis

    (tmp_path / "package.json").write_text("{\"dependencies\":{}}", encoding="utf-8")
    (tmp_path / "index.js").write_text(
        "// import evil from 'evil'\n"
        "/* import bc from 'bc-evil' */\n"
        "const s = \"require('str-evil')\";\n"
        "const t = `import tpl from 'tpl-evil'`;\n"
        "const r = /import rx from 'rx-evil'/;\n"
        "import real from 'real-pkg';\n",
        encoding="utf-8",
    )
    (tmp_path / "broken.js").write_text(
        "const = ;;;;\n// import fake from 'fake-evil'\n",
        encoding="utf-8",
    )
    assert analysis.scan_imports(str(tmp_path)) == {"real-pkg"}


def test_action_output_dir_cannot_escape_workspace(tmp_path, monkeypatch):
    action = _load_action_module()
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        json.dumps({"name": "demo", "version": "1.0.0", "dependencies": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("INPUT_REPO_PATH", str(repo))
    monkeypatch.setenv("INPUT_OUTPUT_DIR", "../escaped")
    monkeypatch.setenv("INPUT_ECOSYSTEM", "npm")
    monkeypatch.setenv("INPUT_ARTIFACT_NAME", "")
    action.main()
    assert not (workspace.parent / "escaped").exists()


def test_npm_workspace_object_form_not_reported_root_undeclared(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"workspaces": {"packages": ["packages/*"]}, "dependencies": {}}),
        encoding="utf-8",
    )
    workspace = tmp_path / "packages" / "lib"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"dependencies": {"real": "1.0.0"}}), encoding="utf-8"
    )
    (workspace / "index.js").write_text("import 'real';", encoding="utf-8")
    assert not any(
        finding.package == "real"
        and finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        for finding in analyze_repo(str(tmp_path), ecosystem="npm")
    )


def test_npm_workspace_starstar_glob_not_reported_root_undeclared(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"workspaces": ["packages/**"], "dependencies": {}}),
        encoding="utf-8",
    )
    workspace = tmp_path / "packages" / "team" / "app"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"dependencies": {"real": "1.0.0"}}), encoding="utf-8"
    )
    (workspace / "index.js").write_text("import 'real';", encoding="utf-8")
    assert not any(
        finding.package == "real"
        and finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        for finding in analyze_repo(str(tmp_path), ecosystem="npm")
    )


def test_npm_workspace_separate_lockfile_resolves_versions(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"workspaces": ["packages/*"], "dependencies": {}}),
        encoding="utf-8",
    )
    workspace = tmp_path / "packages" / "app"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"dependencies": {"real": "^1.0.0"}}), encoding="utf-8"
    )
    (workspace / "yarn.lock").write_text(
        'real@^1.0.0:\n  version "1.2.0"\n', encoding="utf-8"
    )
    (workspace / "index.js").write_text("import 'real';", encoding="utf-8")
    findings = analyze_repo(str(tmp_path), ecosystem="npm")
    assert not any(
        finding.package == "real"
        and finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        for finding in findings
    )
    assert not any(
        finding.package == "real"
        and finding.finding_type.name == "LOCKFILE_MANIFEST_MISMATCH"
        for finding in findings
    )


def test_go_work_member_import_not_reported_undeclared(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/root\n\ngo 1.22\n", encoding="utf-8")
    (tmp_path / "go.work").write_text("go 1.22\n\nuse (\n\t./app\n\t./lib\n)\n", encoding="utf-8")
    app = tmp_path / "app"
    app.mkdir(parents=True)
    (app / "go.mod").write_text(
        "module example.com/app\n\ngo 1.22\n\nrequire example.com/lib v0.0.0\n",
        encoding="utf-8",
    )
    (app / "main.go").write_text(
        'package main\n\nimport "example.com/lib"\n\nfunc main() {}\n', encoding="utf-8"
    )
    lib = tmp_path / "lib"
    lib.mkdir(parents=True)
    (lib / "go.mod").write_text("module example.com/lib\n\ngo 1.22\n", encoding="utf-8")
    (lib / "lib.go").write_text("package lib\n", encoding="utf-8")
    assert not any(
        finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        and finding.package == "example.com/lib"
        for finding in analyze_repo(str(tmp_path), ecosystem="go")
    )


def test_go_work_undeclared_use_is_not_suppressed(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/root\n\ngo 1.22\n", encoding="utf-8")
    (tmp_path / "go.work").write_text("go 1.22\n\nuse (\n\t./app\n\t./lib\n)\n", encoding="utf-8")
    app = tmp_path / "app"
    app.mkdir(parents=True)
    (app / "go.mod").write_text(
        "module example.com/app\n\ngo 1.22\n\nrequire example.com/lib v0.0.0\n",
        encoding="utf-8",
    )
    (app / "main.go").write_text(
        'package main\n\nimport "example.com/lib"\n\nfunc main() {}\n', encoding="utf-8"
    )
    (app / "extra.go").write_text(
        'package main\n\nimport "example.com/notdeclared"\n\nfunc main() {}\n', encoding="utf-8"
    )
    lib = tmp_path / "lib"
    lib.mkdir(parents=True)
    (lib / "go.mod").write_text("module example.com/lib\n\ngo 1.22\n", encoding="utf-8")
    (lib / "lib.go").write_text("package lib\n", encoding="utf-8")
    notdeclared = tmp_path / "vendor" / "example.com" / "notdeclared"
    notdeclared.mkdir(parents=True)
    (notdeclared / "notdeclared.go").write_text("package notdeclared\n", encoding="utf-8")
    (tmp_path / "vendor" / "modules.txt").write_text(
        "# example.com/notdeclared v0.0.0\n## explicit; go 1.22\nexample.com/notdeclared\n",
        encoding="utf-8",
    )
    assert any(
        finding.finding_type.name == "UNDECLARED_DIRECT_USE"
        and finding.package == "example.com/notdeclared"
        for finding in analyze_repo(str(tmp_path), ecosystem="go")
    )
