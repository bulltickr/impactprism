import json
import os
import re
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "cra-check.yml")
COMPATIBILITY_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "compatibility.yml")
CRA_SCAN_EXCLUDES = (
    "tests",
    "fixtures",
    "demo",
    "node_modules",
    "build",
    "dist",
    ".git",
    ".cache",
    "coverage",
    "public",
)


def _step_blocks(raw):
    headers = list(re.finditer(r"(?m)^ {6}- name: ", raw))
    return [
        raw[match.start() : next_match.start() if next_match else len(raw)]
        for match, next_match in zip(headers, headers[1:] + [None])
    ]


def _job_block(raw, job_name):
    header = re.search(rf"(?m)^  {re.escape(job_name)}:\s*$", raw)
    assert header is not None, f"job {job_name!r} was not found"
    following = re.search(r"(?m)^  \S.*$", raw[header.end() :])
    end = header.end() + following.start() if following else len(raw)
    return raw[header.start() : end]


def _permissions_block(raw):
    header = re.search(r"(?m)^permissions:\s*$", raw)
    assert header is not None, "file-level permissions block was not found"
    following = re.search(r"(?m)^\S.*$", raw[header.end() :])
    end = header.end() + following.start() if following else len(raw)
    return raw[header.start() : end]


def _workflow_text():
    return open(WORKFLOW, encoding="utf-8").read()


def _compatibility_workflow_text():
    return open(COMPATIBILITY_WORKFLOW, encoding="utf-8").read()


def _cra_analyze_command(repo):
    command = [
        sys.executable,
        os.path.join(ROOT, "main.py"),
        "analyze",
        str(repo),
        "--ecosystem",
        "npm",
    ]
    for directory in CRA_SCAN_EXCLUDES:
        command.extend(("--exclude", directory))
    command.append("--json")
    return command


def test_compatibility_corpus_is_maintainer_triggered_and_read_only():
    raw = _compatibility_workflow_text()

    assert "workflow_dispatch:" in raw
    assert "pull_request:" not in raw
    assert "push:" not in raw
    assert "contents: read" in raw
    assert "contents: write" not in raw
    assert "persist-credentials: false" in raw


def test_compatibility_workflow_prepares_then_runs_the_offline_runner():
    raw = _compatibility_workflow_text()
    steps = _step_blocks(raw)
    prepare_index = next(
        index for index, block in enumerate(steps) if "compatibility/prepare.py" in block
    )
    run_index = next(
        index for index, block in enumerate(steps) if "compatibility/run.py" in block
    )

    assert prepare_index < run_index
    assert "--json" in steps[run_index]


def test_every_checkout_disables_persisted_credentials():
    raw = _workflow_text()
    checkout_blocks = [
        block for block in _step_blocks(raw) if "uses: actions/checkout@" in block
    ]
    assert checkout_blocks, "workflow must contain at least one checkout step"
    assert all(
        "persist-credentials: false" in block for block in checkout_blocks
    ), "every checkout step must set persist-credentials: false"
    assert "persist-credentials: true" not in raw, (
        "workflow must not enable persisted checkout credentials"
    )


def test_checkout_refs_trusted_base_sha():
    raw = _workflow_text()
    assert any(
        "github.event.pull_request.base.sha" in block for block in _step_blocks(raw)
    ), "a checkout step must use the trusted pull request base SHA"


def test_scanner_runs_from_trusted_base_with_read_only_token():
    raw = _workflow_text()
    analyze = next(
        (
            block
            for block in _step_blocks(raw)
            if "python main.py analyze" in block
        ),
        None,
    )
    assert analyze is not None, "analyze step was not found"
    assert "working-directory: scanner" in analyze, (
        "analyze step must run from the trusted scanner checkout"
    )
    assert '"${{ github.workspace }}/pr"' in analyze, (
        "analyze step must scan the pull request checkout"
    )
    job = _job_block(raw, "cra-check")
    assert "pull-requests: write" not in job, (
        "scanner job must not have pull-requests write permission"
    )
    permissions = _permissions_block(raw)
    assert "contents: read" in permissions, (
        "file-level permissions must grant contents read access"
    )
    assert "pull-requests: write" not in permissions, (
        "file-level permissions must not grant pull-requests write access"
    )


def test_cra_scan_scope_is_explicit_and_matches_repository_defaults():
    raw = _workflow_text()
    analyze = next(
        block for block in _step_blocks(raw) if "python main.py analyze" in block
    )

    assert "--ecosystem npm" in analyze, (
        "the pull-request gate must not change ecosystem based on PR contents"
    )
    for directory in CRA_SCAN_EXCLUDES:
        assert f"--exclude {directory}" in analyze, (
            f"CRA scan must explicitly preserve the repository exclusion: {directory}"
        )


def test_cra_scan_scope_is_clean_for_this_repository():
    result = subprocess.run(
        _cra_analyze_command(ROOT), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["findings"] == []


def test_cra_scan_scope_still_fails_for_a_production_finding(tmp_path):
    repo = tmp_path / "production-repo"
    source = repo / "src"
    source.mkdir(parents=True)
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "production-repo",
                "version": "1.0.0",
                "dependencies": {"react": "18.2.0"},
            }
        ),
        encoding="utf-8",
    )
    (repo / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "production-repo",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "packages": {
                    "": {
                        "name": "production-repo",
                        "version": "1.0.0",
                        "dependencies": {"react": "18.2.0"},
                    },
                    "node_modules/react": {"version": "18.2.0"},
                },
            }
        ),
        encoding="utf-8",
    )
    (source / "index.js").write_text(
        'import React from "react";\nimport missingPackage from "missing-package";\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        _cra_analyze_command(repo), capture_output=True, text=True, check=False
    )
    assert result.returncode == 1, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert [finding["package"] for finding in report["findings"]] == [
        "missing-package"
    ]


def test_cra_evidence_comment_runs_when_findings_fail_the_gate():
    raw = _workflow_text()
    post_comment = _job_block(raw, "post-comment")

    assert "always()" in post_comment, (
        "evidence posting must not be skipped when the finding gate fails"
    )
    assert "needs.cra-check.outputs.exit_code == '0'" in post_comment
    assert "needs.cra-check.outputs.exit_code == '1'" in post_comment


def test_evidence_is_bounded():
    raw = _workflow_text()
    steps = _step_blocks(raw)
    upload_index = next(
        (
            index
            for index, block in enumerate(steps)
            if "actions/upload-artifact@" in block
        ),
        None,
    )
    assert upload_index is not None, "workflow must contain an evidence upload step"
    assert any(
        "[:65536]" in block and "ord(" in block
        for block in steps[:upload_index]
    ), "evidence must be bounded and filtered before upload"
    comment = next(
        (
            block
            for block in steps
            if "uses: actions/github-script@" in block
        ),
        None,
    )
    assert comment is not None, "workflow must contain a github-script comment step"
    assert ".slice(0, 65536)" in comment, (
        "posted comment content must be limited to 65536 characters"
    )
    assert raw.count("65536") >= 2, (
        "workflow must apply the evidence size bound in at least two places"
    )
