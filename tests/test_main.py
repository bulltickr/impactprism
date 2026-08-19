import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from impactprism.cli import main
from impactprism.cra_clauses import DEFAULT_PATH


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, name="repo", dependencies=None, dev_dependencies=None, source=""):
    repo = tmp_path / name
    package = {
        "name": name,
        "version": "1.0.0",
        "dependencies": dependencies or {},
    }
    if dev_dependencies:
        package["devDependencies"] = dev_dependencies
    write_file(repo, "package.json", json.dumps(package, indent=2))
    lock_packages = {
        "": {
            "name": name,
            "version": "1.0.0",
            "dependencies": dependencies or {},
        }
    }
    for dependency_name, dependency_version in (dependencies or {}).items():
        lock_packages["node_modules/" + dependency_name] = {
            "version": str(dependency_version).lstrip("^")
        }
    for dependency_name, dependency_version in (dev_dependencies or {}).items():
        lock_packages["node_modules/" + dependency_name] = {
            "version": str(dependency_version).lstrip("^")
        }
    write_file(
        repo,
        "package-lock.json",
        json.dumps({"name": name, "version": "1.0.0", "lockfileVersion": 3, "packages": lock_packages}, indent=2),
    )
    write_file(repo, "src/App.jsx", source)
    return repo


def make_go_repo(tmp_path, name="go-repo", go_mod="", source=""):
    repo = tmp_path / name
    write_file(repo, "go.mod", go_mod)
    if source:
        write_file(repo, "main.go", source)
    return repo


def make_report(tmp_path, name="repo", drift=None, undeclared=None):
    drift = sorted(drift or [])
    undeclared = sorted(undeclared or [])
    report = {
        "repo": str(tmp_path / name),
        "package_name": name,
        "package_version": "1.0.0",
        "declared": sorted(set(drift) | set(undeclared)),
        "imported": sorted(set(drift) | set(undeclared)),
        "drift": drift,
        "undeclared": undeclared,
    }
    path = tmp_path / (name + "-report.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def test_clauses_default_and_explicit_path(capsys):
    assert main(["clauses"]) == 0
    output = capsys.readouterr().out
    assert "Art 13(1)(a)" in output
    assert "Art 13(1)(b)" in output
    assert "Art 14(1)" in output
    assert "dependency_drift" in output

    assert main(["clauses", str(DEFAULT_PATH)]) == 0
    assert "Loaded " in capsys.readouterr().out


def test_analyze_routing_and_flags(tmp_path, capsys):
    clean = make_repo(
        tmp_path,
        "clean",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    assert main(["analyze", str(clean)]) == 0

    drift = make_repo(
        tmp_path,
        "drift",
        dependencies={"react": "18.2.0"},
        source="const value = 1;\n",
    )
    assert main(["analyze", str(drift)]) == 1

    report_path = tmp_path / "scan.json"
    sbom_path = tmp_path / "sbom.json"
    assert main(
        [
            "analyze",
            str(clean),
            "--report",
            str(report_path),
            "--sbom",
            str(sbom_path),
        ]
    ) == 0
    assert report_path.is_file()
    assert sbom_path.is_file()
    capsys.readouterr()

    assert main(["analyze", str(clean), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["package_name"] == "clean"


def test_analyze_missing_directory(tmp_path):
    assert main(["analyze", str(tmp_path / "missing")]) == 2


def test_json_input_error_is_machine_readable(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "missing"), "--json"]) == 2

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "schema_version": 1,
        "generator": "impactprism-cli",
        "error": {
            "kind": "input-error",
            "message": "repository directory not found: "
            + str((tmp_path / "missing").resolve()),
        },
        "exit_code": 2,
    }


def test_json_input_error_matches_published_schema(tmp_path, capsys):
    from jsonschema import validate

    assert main(["scan", str(tmp_path / "missing"), "--json"]) == 2
    output = json.loads(capsys.readouterr().out)
    schema_path = Path(ROOT) / "docs" / "schemas" / "cli-error.schema.json"
    validate(output, json.loads(schema_path.read_text(encoding="utf-8")))


def test_scan_json_preserves_manifest_scanner_error_report(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "malformed"
    repo.mkdir()
    write_file(repo, "package.json", "{\"name\": \n")
    monkeypatch.chdir(tmp_path)

    assert main(["scan", str(repo), "--json"]) == 2

    report = json.loads(capsys.readouterr().out)
    assert report["ecosystem"] == "npm"
    assert report["sbom"] is None
    assert report["counts"]["by_type"] == {"SCANNER_ERROR": 1}
    assert report["findings"][0]["finding_type"] == "SCANNER_ERROR"


def test_scan_clean_repo_exits_zero(tmp_path, monkeypatch, capsys):
    clean = make_repo(
        tmp_path,
        "scan-clean",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(clean)]) == 0
    capsys.readouterr()


def test_scan_undeclared_exits_one(tmp_path, monkeypatch, capsys):
    repo = make_repo(
        tmp_path,
        "scan-undeclared",
        source="import missingpkg from 'missingpkg';\n",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo)]) == 1
    capsys.readouterr()


def test_scan_exclude_skips_test_dirs(tmp_path, monkeypatch, capsys):
    repo = make_repo(
        tmp_path,
        "scan-exclude",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    write_file(repo, "tests/leak.js", "import missingpkg from 'missingpkg';\n")
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo)]) == 0
    assert main(["analyze", str(repo)]) == 1
    capsys.readouterr()


def test_analyze_behavior_unchanged(tmp_path, capsys):
    clean = make_repo(
        tmp_path,
        "behavior-clean",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    drift = make_repo(
        tmp_path,
        "behavior-drift",
        dependencies={"react": "18.2.0"},
        source="const value = 1;\n",
    )
    assert main(["analyze", str(clean)]) == 0
    assert main(["analyze", str(drift)]) == 1
    capsys.readouterr()


def test_evidence_routing_defaults_and_stdout(tmp_path, monkeypatch, capsys):
    report_path = make_report(tmp_path, drift=["react"], undeclared=["lodash"])
    monkeypatch.chdir(tmp_path)
    assert main(["evidence", str(report_path)]) == 0
    assert (tmp_path / "evidence.md").is_file()
    assert (tmp_path / "evidence.json").is_file()

    stdout_tmp = tmp_path / "stdout"
    stdout_tmp.mkdir()
    stdout_report = make_report(stdout_tmp, undeclared=["lodash"])
    monkeypatch.chdir(stdout_tmp)
    assert main(["evidence", str(stdout_report), "--stdout"]) == 0
    evidence = json.loads(capsys.readouterr().out)
    assert evidence["summary"]["total_findings"] == 1
    assert not (stdout_tmp / "evidence.json").is_file()


def test_evidence_missing_report(tmp_path):
    assert main(["evidence", str(tmp_path / "missing.json")]) == 2


def test_subprocess_clauses_smoke():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "main.py"), "clauses"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0
    assert "Art 13(1)(a)" in result.stdout
    assert "Art 14(1)" in result.stdout


def test_subprocess_help_smoke():
    for command in ("analyze", "evidence", "doctor"):
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"), command, "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0
        assert command in result.stdout


def test_doctor_reports_supported_repo_and_json_contract(tmp_path, capsys):
    from jsonschema import validate

    repo = make_repo(
        tmp_path,
        "doctor-clean",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    assert main(["doctor", str(repo), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    schema_path = Path(ROOT) / "docs" / "schemas" / "doctor.schema.json"
    validate(report, json.loads(schema_path.read_text(encoding="utf-8")))
    assert report["ecosystem"] == "npm"
    assert report["status"] in ("pass", "warn")


def test_doctor_fails_for_unsupported_repository(tmp_path, capsys):
    repo = tmp_path / "unsupported"
    repo.mkdir()
    assert main(["doctor", str(repo), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "fail"
    assert any(check["id"] == "ecosystem" for check in report["checks"])


def test_module_entry_clauses():
    cwd = tempfile.mkdtemp()
    result = subprocess.run(
        [sys.executable, "-m", "impactprism", "clauses"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert result.returncode == 0
    assert "Art 13(1)(a)" in result.stdout


def test_module_entry_scan_exit_codes(tmp_path):
    clean = make_repo(
        tmp_path,
        "entry-clean",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    result = subprocess.run(
        [sys.executable, "-m", "impactprism", "scan", str(clean)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0

    drift = make_repo(
        tmp_path,
        "entry-drift",
        dependencies={"react": "18.2.0"},
        source="const value = 1;\n",
    )
    result = subprocess.run(
        [sys.executable, "-m", "impactprism", "scan", str(drift)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 1

    result = subprocess.run(
        [sys.executable, "-m", "impactprism", "scan", str(tmp_path / "missing")],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 2


def test_scan_scope_mismatch_emits_bucket_and_exit_one(tmp_path, monkeypatch, capsys):
    repo = make_repo(
        tmp_path,
        "scan-scope",
        dependencies={"react": "18.2.0"},
        dev_dependencies={"chai": "5.0.0"},
        source="import React from 'react';\n",
    )
    write_file(repo, "src/lib.js", 'import chai from "chai";\nexport default chai;\n')
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    for key in (
        "repo",
        "package_name",
        "package_version",
        "declared",
        "imported",
        "drift",
        "undeclared",
        "sbom",
    ):
        assert key in report
    assert report["ecosystem"] == "npm"
    assert report["scope-mismatch"] == ["chai"]
    assert report["drift"] == []
    assert report["undeclared"] == []


def test_scan_scope_mismatch_clean_exit_zero(tmp_path, monkeypatch, capsys):
    repo = make_repo(
        tmp_path,
        "scan-scope-clean",
        dependencies={"react": "18.2.0"},
        source="import React from 'react';\n",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ecosystem"] == "npm"
    assert report["scope-mismatch"] == []


def test_scan_go_clean_json_shape_and_exit_zero(tmp_path, monkeypatch, capsys):
    repo = make_go_repo(
        tmp_path,
        "go-clean",
        go_mod="module example.com/demo\n\ngo 1.22\n\nrequire github.com/foo/bar v1.0.0\n",
        source='package main\n\nimport "github.com/foo/bar"\n\nfunc main() {}\n',
    )
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    for key in (
        "repo",
        "package_name",
        "package_version",
        "declared",
        "imported",
        "drift",
        "undeclared",
        "sbom",
    ):
        assert key in report
    assert report["ecosystem"] == "go"
    assert report["package_name"] == "example.com/demo"
    assert report["declared"] == ["github.com/foo/bar"]
    assert report["imported"] == ["github.com/foo/bar"]
    assert report["drift"] == []
    assert report["undeclared"] == []
    assert report["scope-mismatch"] == []
    assert report["sbom"]["specVersion"] == "1.6"


def test_scan_go_drift_exit_one(tmp_path, monkeypatch, capsys):
    repo = make_go_repo(
        tmp_path,
        "go-drift",
        go_mod="module example.com/demo\n\ngo 1.22\n\nrequire github.com/foo/bar v1.0.0\n",
        source="package main\n\nfunc main() {}\n",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ecosystem"] == "go"
    assert report["drift"] == ["github.com/foo/bar"]
    assert report["undeclared"] == []
    assert report["scope-mismatch"] == []


def test_scan_go_transitive_used_directly_exit_one(tmp_path, monkeypatch, capsys):
    repo = make_go_repo(
        tmp_path,
        "go-transitive",
        go_mod=(
            "module example.com/demo\n\ngo 1.22\n\n"
            "require github.com/foo/bar v1.0.0 // indirect\n"
        ),
        source='package main\n\nimport "github.com/foo/bar"\n\nfunc main() {}\n',
    )
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ecosystem"] == "go"
    assert report["undeclared"] == ["github.com/foo/bar"]
    assert report["drift"] == []
    assert report["scope-mismatch"] == []


def test_scan_missing_manifest_exit_two(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["scan", str(empty)]) == 2


def test_scan_go_report_flag_writes_report(tmp_path, monkeypatch):
    repo = make_go_repo(
        tmp_path,
        "go-report",
        go_mod="module example.com/demo\n\ngo 1.22\n",
        source="package main\n\nfunc main() {}\n",
    )
    report_path = tmp_path / "go-scan-report.json"
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(repo), "--report", str(report_path)]) == 0
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ecosystem"] == "go"
    assert "scope-mismatch" in report
    assert report["package_name"] == "example.com/demo"


def test_module_entry_scan_go_json(tmp_path):
    repo = make_go_repo(
        tmp_path,
        "entry-go",
        go_mod="module example.com/demo\n\ngo 1.22\n\nrequire github.com/foo/bar v1.0.0\n",
        source='package main\n\nimport "github.com/foo/bar"\n\nfunc main() {}\n',
    )
    result = subprocess.run(
        [sys.executable, "-m", "impactprism", "scan", str(repo), "--json"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["ecosystem"] == "go"
    assert report["package_name"] == "example.com/demo"
    assert report["scope-mismatch"] == []
    assert report["sbom"]["specVersion"] == "1.6"


def test_scan_repo_root_exit_zero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert main(["scan", ROOT]) == 0


def test_console_script_registered():
    from importlib.metadata import entry_points

    eps = entry_points()
    if hasattr(eps, "select"):
        console = eps.select(group="console_scripts")
    else:
        console = eps.get("console_scripts", [])
    impactprism_eps = [ep for ep in console if ep.name == "impactprism"]
    assert impactprism_eps
    assert impactprism_eps[0].value == "impactprism.cli:main"


def test_module_entry_help(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "impactprism", "scan", "--help"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0
    assert "scan" in result.stdout
