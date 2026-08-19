"""Run the GitHub Action runner through a provider-neutral local contract.

This is intentionally a normal Python process rather than a GitHub-specific
test. It exercises the same ``action/run.py`` entry point used by the
composite Action and checks the files a caller would consume: canonical JSON,
CycloneDX, SARIF, evidence, and GitHub step outputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cyclonedx.output import OutputFormat
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation import make_schemabased_validator
from jsonschema import validate


ROOT = Path(__file__).resolve().parents[1]
SCAN_SCHEMA = ROOT / "docs" / "schemas" / "scan-report.schema.json"
EVIDENCE_SCHEMA = ROOT / "docs" / "schemas" / "evidence-pack.schema.json"
ACTION_RUNNER = ROOT / "action" / "run.py"
SARIF_LEVELS = {"error", "warning", "note", "none"}


def _fail(message: str) -> None:
    raise AssertionError(message)


def _load(path: Path) -> dict:
    if not path.is_file():
        _fail(f"missing expected output: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"invalid JSON in {path}: {exc}")


def _run_action(
    repo: Path,
    workspace: Path,
    *,
    ecosystem: str = "npm",
    output_dir: str,
    fail_on: str = "finding",
    artifact_name: str = "",
) -> subprocess.CompletedProcess[str]:
    workspace.mkdir(parents=True, exist_ok=True)
    output_file = workspace / "github-output.txt"
    summary_file = workspace / "github-summary.md"
    env = os.environ.copy()
    env.update(
        {
            "GITHUB_WORKSPACE": str(workspace),
            "GITHUB_REPOSITORY": "bulltickr/impactprism",
            "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
            "GITHUB_OUTPUT": str(output_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
            "INPUT_REPO_PATH": str(repo),
            "INPUT_ECOSYSTEM": ecosystem,
            "INPUT_FAIL_ON": fail_on,
            "INPUT_SEVERITY_THRESHOLD": "low",
            "INPUT_OUTPUT_DIR": output_dir,
            "INPUT_ARTIFACT_NAME": artifact_name,
            "INPUT_CONFIG_PATH": "",
            "INPUT_BASELINE_PATH": "",
            "INPUT_DELTA_PATH": "",
            "INPUT_EXCLUDE": "",
        }
    )
    return subprocess.run(
        [sys.executable, str(ACTION_RUNNER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_output_contract(
    workspace: Path, *, require_bom: bool, output_name: str = "reports"
) -> dict:
    output_dir = workspace / output_name
    report = _load(output_dir / "findings.json")
    evidence = _load(output_dir / "evidence.json")
    sarif = _load(output_dir / "impactprism.sarif")

    validate(report, _load(SCAN_SCHEMA))
    validate(evidence, _load(EVIDENCE_SCHEMA))

    if require_bom:
        bom_path = output_dir / "bom.json"
        bom = _load(bom_path)
        if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.6":
            _fail("SBOM is not a CycloneDX 1.6 document")
        bom_error = make_schemabased_validator(
            OutputFormat.JSON, SchemaVersion.V1_6
        ).validate_str(json.dumps(bom))
        if bom_error is not None:
            _fail(f"SBOM schema validation failed: {bom_error}")
        if not report.get("bom_validated"):
            _fail("successful scan did not mark the SBOM as validated")
    elif (output_dir / "bom.json").exists():
        _fail("scanner-error output retained a stale SBOM")

    if sarif.get("version") != "2.1.0" or len(sarif.get("runs", [])) != 1:
        _fail("SARIF root contract is invalid")
    run = sarif["runs"][0]
    driver = run.get("tool", {}).get("driver", {})
    if not isinstance(driver.get("name"), str) or not isinstance(driver.get("rules"), list):
        _fail("SARIF driver contract is invalid")
    rule_ids = {rule.get("id") for rule in driver["rules"]}
    results = run.get("results")
    if not isinstance(results, list) or len(results) != len(report["findings"]):
        _fail("SARIF result count does not match findings")
    for result in results:
        if result.get("level") not in SARIF_LEVELS:
            _fail("SARIF result has an invalid level")
        if not isinstance(result.get("ruleId"), str) or result["ruleId"] not in rule_ids:
            _fail("SARIF result references a missing rule")
        if not isinstance(result.get("message", {}).get("text"), str):
            _fail("SARIF result has no message text")
        for location in result.get("locations", []):
            uri = location.get("physicalLocation", {}).get("artifactLocation", {}).get("uri")
            if not isinstance(uri, str) or uri.startswith(("/", "\\")) or "\\" in uri:
                _fail("SARIF location is not a portable relative URI")
            if uri == ".." or uri.startswith("../") or "/../" in uri:
                _fail("SARIF location escapes the repository")

    expected_hash = hashlib.sha256(
        (output_dir / "findings.json").read_bytes()
    ).hexdigest()
    if evidence.get("source_report_sha256") != expected_hash:
        _fail("evidence does not hash the emitted findings report")

    output_lines = (workspace / "github-output.txt").read_text(encoding="utf-8").splitlines()
    outputs = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output_lines if "=" in line}
    for key in ("outcome", "findings-path", "sarif-path", "evidence-path", "output-dir", "exit-code"):
        if key not in outputs:
            _fail(f"GitHub output is missing {key}")
    if Path(outputs["output-dir"]).resolve() != output_dir.resolve():
        _fail("GitHub output reported the wrong output directory")
    return report


def _copy_fixture(parent: Path, source: str, name: str | None = None) -> Path:
    destination = parent / (name or source)
    shutil.copytree(ROOT / "demo" / source, destination)
    return destination


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="impactprism-action-smoke-") as raw_root:
        root = Path(raw_root)

        clean_repo = _copy_fixture(root, "clean-app", "clean-repo")
        clean_workspace = root / "clean-workspace"
        clean = _run_action(clean_repo, clean_workspace, output_dir="reports")
        if clean.returncode != 0:
            _fail(f"clean Action run failed:\n{clean.stdout}\n{clean.stderr}")
        clean_report = _assert_output_contract(clean_workspace, require_bom=True)
        if clean_report.get("outcome") != "clean":
            _fail("clean fixture did not produce clean outcome")

        for ecosystem in ("python", "go"):
            repo = _copy_fixture(root, f"{ecosystem}-clean", f"{ecosystem}-repo")
            workspace = root / f"{ecosystem}-workspace"
            result = _run_action(
                repo,
                workspace,
                ecosystem=ecosystem,
                output_dir="reports",
            )
            if result.returncode != 0:
                _fail(
                    f"{ecosystem} Action run failed:\n"
                    f"{result.stdout}\n{result.stderr}"
                )
            report = _assert_output_contract(workspace, require_bom=True)
            if report.get("ecosystem") != ecosystem:
                _fail(f"{ecosystem} fixture resolved to the wrong ecosystem")

        finding_repo = root / "finding-repo"
        shutil.copytree(ROOT / "demo" / "npm-app", finding_repo)
        finding_workspace = root / "finding-workspace"
        finding = _run_action(finding_repo, finding_workspace, output_dir="reports")
        if finding.returncode != 1:
            _fail(f"finding Action run returned {finding.returncode}, expected 1")
        finding_report = _assert_output_contract(finding_workspace, require_bom=True)
        if finding_report.get("outcome") != "policy-failure":
            _fail("finding fixture did not produce policy-failure outcome")

        broken_repo = _copy_fixture(root, "clean-app", "broken-repo")
        (broken_repo / "package.json").write_text("{ not valid json\n", encoding="utf-8")
        broken_workspace = root / "broken-workspace"
        broken = _run_action(
            broken_repo,
            broken_workspace,
            output_dir="reports",
            fail_on="never",
        )
        if broken.returncode != 2:
            _fail(f"scanner-error Action run returned {broken.returncode}, expected 2")
        broken_report = _assert_output_contract(broken_workspace, require_bom=False)
        if broken_report.get("outcome") != "scanner-error":
            _fail("malformed manifest did not produce scanner-error outcome")

        escaped_repo = _copy_fixture(root, "clean-app", "escaped-repo")
        escaped_workspace = root / "escaped-workspace"
        escaped = _run_action(escaped_repo, escaped_workspace, output_dir="../outside")
        if escaped.returncode != 0:
            _fail(f"path-containment Action run failed:\n{escaped.stdout}\n{escaped.stderr}")
        _assert_output_contract(
            escaped_workspace,
            require_bom=True,
            output_name="impactprism-reports",
        )
        if (root / "outside").exists():
            _fail("output-dir traversal created files outside the workspace")

    print(
        "Action smoke: PASS (npm/python/go clean, finding, "
        "scanner-error, and path containment)"
    )


if __name__ == "__main__":
    try:
        run()
    except AssertionError as exc:
        print(f"Action smoke: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
