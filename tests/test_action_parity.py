import json
from pathlib import Path

from jsonschema import validate

from action.run import main as action_main
from impactprism.cli import main as cli_main


ROOT = Path(__file__).resolve().parents[1]


def _write_npm_repo(root: Path, source: str) -> Path:
    repo = root / "repo"
    repo.mkdir()
    package = {
        "name": "parity-demo",
        "version": "1.0.0",
        "dependencies": {"react": "18.2.0"},
    }
    (repo / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    lock = {
        "name": "parity-demo",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "parity-demo", "version": "1.0.0", "dependencies": package["dependencies"]},
            "node_modules/react": {"version": "18.2.0"},
        },
    }
    (repo / "package-lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "app.js").write_text(source, encoding="utf-8")
    return repo


def _write_go_workspace_repo(root: Path) -> Path:
    repo = root / "go-repo"
    (repo / "apps" / "app").mkdir(parents=True)
    (repo / "libs" / "shared").mkdir(parents=True)
    (repo / "go.work").write_text(
        "go 1.22\n\nuse (\n\t./apps/app\n\t./libs/shared\n)\n",
        encoding="utf-8",
    )
    (repo / "apps" / "app" / "go.mod").write_text(
        "module example.com/app\n\ngo 1.22\n\n"
        "require (\n"
        "\texample.com/shared v0.0.0\n"
        "\texample.com/appdep v1.2.3\n"
        ")\n",
        encoding="utf-8",
    )
    (repo / "apps" / "app" / "main.go").write_text(
        'package main\n\nimport (\n'
        '\t"example.com/shared/pkg"\n'
        '\t"example.com/appdep/api"\n'
        ')\n\nvar _ = pkg.Value\nvar _ = api.Value\n',
        encoding="utf-8",
    )
    (repo / "libs" / "shared" / "go.mod").write_text(
        "module example.com/shared\n\ngo 1.22\n",
        encoding="utf-8",
    )
    (repo / "libs" / "shared" / "pkg.go").write_text(
        "package pkg\n\nconst Value = 1\n",
        encoding="utf-8",
    )
    return repo


def _run_action(repo, workspace, monkeypatch, **inputs):
    values = {
        "GITHUB_WORKSPACE": str(workspace),
        "INPUT_REPO_PATH": str(repo),
        "INPUT_ECOSYSTEM": "npm",
        "INPUT_FAIL_ON": "finding",
        "INPUT_SEVERITY_THRESHOLD": "low",
        "INPUT_OUTPUT_DIR": "reports",
        "INPUT_ARTIFACT_NAME": "",
        "INPUT_CONFIG_PATH": "",
        "INPUT_BASELINE_PATH": "",
        "INPUT_DELTA_PATH": "",
        "INPUT_EXCLUDE": "",
        "INPUT_ROOTS": "",
    }
    values.update(inputs)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return action_main()


def _canonical_fields(report):
    names = (
        "schema_version",
        "repo",
        "package_name",
        "package_version",
        "ecosystem",
        "declared",
        "imported",
        "drift",
        "undeclared",
        "scope-mismatch",
        "integrity",
        "unresolved",
        "findings",
        "counts",
    )
    return {name: report.get(name) for name in names}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_cli_and_action_share_canonical_report_and_evidence_contract(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    cli_report = tmp_path / "cli-report.json"

    assert cli_main(["scan", str(repo), "--report", str(cli_report)]) == 0
    action_workspace = tmp_path / "workspace"
    action_workspace.mkdir()
    assert _run_action(repo, action_workspace, monkeypatch) == 0

    cli = _load(cli_report)
    action = _load(action_workspace / "reports" / "findings.json")
    assert _canonical_fields(action) == _canonical_fields(cli)

    scan_schema = _load(ROOT / "docs" / "schemas" / "scan-report.schema.json")
    evidence_schema = _load(ROOT / "docs" / "schemas" / "evidence-pack.schema.json")
    validate(action, scan_schema)
    validate(_load(action_workspace / "reports" / "evidence.json"), evidence_schema)
    assert action["generator"] == "impactprism-action"
    assert action["bom_validated"] is True


def test_action_exposes_remediation_guidance_in_all_finding_outputs(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import missing from "missing-package";\n')
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _run_action(repo, workspace, monkeypatch) == 1
    report = _load(workspace / "reports" / "findings.json")
    finding = report["findings"][0]
    assert finding["remediation_guidance"]["steps"]

    sarif = _load(workspace / "reports" / "impactprism.sarif")
    result = sarif["runs"][0]["results"][0]
    assert result["properties"]["remediation_guidance"]["steps"]
    summary = (workspace / "reports" / "summary.md").read_text(encoding="utf-8")
    assert "next step" in summary


def test_action_baseline_gates_only_new_findings(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _run_action(repo, workspace, monkeypatch) == 0
    baseline = workspace / "reports" / "findings.json"

    (repo / "src" / "app.js").write_text(
        'import React from "react";\nimport missingPackage from "missing-package";\n',
        encoding="utf-8",
    )
    assert (
        _run_action(
            repo,
            workspace,
            monkeypatch,
            INPUT_BASELINE_PATH=str(baseline),
            INPUT_DELTA_PATH="delta.json",
        )
        == 1
    )
    report = _load(workspace / "reports" / "findings.json")
    delta = _load(repo / "delta.json")
    assert report["delta"]["counts"]["new"] == delta["counts"]["new"]
    assert delta["counts"]["new"] >= 1

    # A repeat against the current report has no new findings, even though the
    # report still contains the finding for consumers that want full context.
    assert (
        _run_action(
            repo,
            workspace,
            monkeypatch,
            INPUT_BASELINE_PATH=str(workspace / "reports" / "findings.json"),
            INPUT_DELTA_PATH="delta.json",
        )
        == 0
    )
    assert _load(repo / "delta.json")["counts"]["new"] == 0


def test_action_config_and_explicit_exclude_are_applied(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    generated = repo / "generated"
    generated.mkdir()
    (generated / "generated.js").write_text(
        'import missingPackage from "missing-package";\n', encoding="utf-8"
    )
    (repo / ".impactprism.toml").write_text(
        '[scan]\nexclude = ["generated"]\n', encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _run_action(repo, workspace, monkeypatch) == 0
    report = _load(workspace / "reports" / "findings.json")
    assert all(finding.get("package") != "missing-package" for finding in report["findings"])


def test_cli_and_action_apply_explicit_npm_root_selection(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import rootLeak from "root-only";\n')
    package_root = repo / "packages" / "app"
    package_root.mkdir(parents=True)
    (package_root / "package.json").write_text(
        json.dumps(
            {
                "name": "selected-app",
                "version": "1.0.0",
                "dependencies": {"react": "18.2.0"},
            }
        ),
        encoding="utf-8",
    )
    (package_root / "app.js").write_text(
        'import React from "react";\n', encoding="utf-8"
    )
    cli_report = tmp_path / "cli-root-report.json"
    assert (
        cli_main(
            ["scan", str(repo), "--root", "packages/app", "--report", str(cli_report)]
        )
        == 0
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert _run_action(repo, workspace, monkeypatch, INPUT_ROOTS="packages/app") == 0
    cli = _load(cli_report)
    action = _load(workspace / "reports" / "findings.json")
    assert cli["scope"]["roots"] == ["packages/app"]
    assert action["scope"]["roots"] == ["packages/app"]
    assert cli["findings"] == action["findings"]
    assert all(finding.get("package") != "root-only" for finding in action["findings"])


def test_cli_and_action_apply_explicit_go_module_root_selection(tmp_path, monkeypatch):
    repo = _write_go_workspace_repo(tmp_path)
    cli_report = tmp_path / "cli-go-root-report.json"
    cli_bom = tmp_path / "cli-go-root-bom.json"
    assert (
        cli_main(
            [
                "scan",
                str(repo),
                "--ecosystem",
                "go",
                "--root",
                "apps/app",
                "--report",
                str(cli_report),
                "--sbom",
                str(cli_bom),
            ]
        )
        == 0
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert (
        _run_action(
            repo,
            workspace,
            monkeypatch,
            INPUT_ECOSYSTEM="go",
            INPUT_ROOTS="apps/app",
        )
        == 0
    )
    cli = _load(cli_report)
    action = _load(workspace / "reports" / "findings.json")
    assert cli["scope"]["roots"] == ["apps/app"]
    assert action["scope"]["roots"] == ["apps/app"]
    assert cli["findings"] == action["findings"]
    assert _load(workspace / "reports" / "bom.json")["components"] == _load(cli_bom)["components"]


def test_action_rejects_invalid_policy_inputs(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _run_action(repo, workspace, monkeypatch, INPUT_FAIL_ON="unexpected") == 2
    assert _run_action(repo, workspace, monkeypatch, INPUT_SEVERITY_THRESHOLD="urgent") == 2


def test_action_scanner_error_cannot_reuse_a_previous_sbom(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert _run_action(repo, workspace, monkeypatch) == 0
    bom = workspace / "reports" / "bom.json"
    assert bom.is_file()

    (repo / "package.json").write_text("{ not valid json\n", encoding="utf-8")
    assert _run_action(repo, workspace, monkeypatch) == 2
    report = _load(workspace / "reports" / "findings.json")
    assert report["outcome"] == "scanner-error"
    assert report["bom_validated"] is False
    assert not bom.exists()


def test_forced_python_scan_uses_python_sbom_in_a_mixed_repository(tmp_path, monkeypatch):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "python-side"\nversion = "2.0.0"\ndependencies = ["requests==2.31.0"]\n',
        encoding="utf-8",
    )
    (repo / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (repo / "app.py").write_text("import requests\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _run_action(repo, workspace, monkeypatch, INPUT_ECOSYSTEM="python") == 0
    report = _load(workspace / "reports" / "findings.json")
    assert report["ecosystem"] == "python"
    assert report["package_name"] == "python-side"
    assert report["sbom"]["components"][0]["purl"].startswith("pkg:pypi/")


def test_cli_severity_threshold_gates_without_removing_findings(tmp_path):
    repo = _write_npm_repo(tmp_path, 'import React from "react";\n')
    (repo / "package-lock.json").unlink()
    report_path = tmp_path / "report.json"

    assert (
        cli_main(
            [
                "scan",
                str(repo),
                "--severity-threshold",
                "high",
                "--report",
                str(report_path),
            ]
        )
        == 0
    )
    report = _load(report_path)
    assert report["counts"]["total"] == 1
    assert report["findings"][0]["finding_type"] == "MISSING_LOCKFILE"


def test_action_unsupported_input_is_not_an_empty_evidence_pass(tmp_path, monkeypatch):
    repo = tmp_path / "unsupported"
    repo.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert _run_action(repo, workspace, monkeypatch, INPUT_FAIL_ON="never") == 0
    report = _load(workspace / "reports" / "findings.json")
    evidence = _load(workspace / "reports" / "evidence.json")
    assert report["outcome"] == "unsupported-ecosystem"
    assert report["findings"][0]["finding_type"] == "SCANNER_ERROR"
    assert report["findings"][0]["remediation_guidance"]["summary"]
    assert evidence["overall_status"] == "REVIEW_REQUIRED"
