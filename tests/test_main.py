import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import main


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_file(root, relpath, content):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_repo(tmp_path, name="repo", dependencies=None, source=""):
    repo = tmp_path / name
    package = {
        "name": name,
        "version": "1.0.0",
        "dependencies": dependencies or {},
    }
    write_file(repo, "package.json", json.dumps(package, indent=2))
    write_file(repo, "src/App.jsx", source)
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

    assert main(["clauses", os.path.join(ROOT, "cra_clauses.yaml")]) == 0
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
    for command in ("analyze", "evidence"):
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"), command, "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0
        assert command in result.stdout
