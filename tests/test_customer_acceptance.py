import json
import subprocess
from pathlib import Path

from impactprism.cli import main
from impactprism.drift import FindingType, classifier


def test_customer_remediation_acceptance_is_proposed_only_and_immutable(
    tmp_path, capsys, monkeypatch
):
    repo = Path(__file__).parents[1] / "demo" / "npm-app"
    report = classifier.analyze_repo(str(repo), ecosystem="npm")
    finding = next(
        item
        for item in report.findings
        if item.finding_type == FindingType.UNDECLARED_DIRECT_USE
        and item.package == "missingpkg"
    )
    finding_path = tmp_path / "finding.json"
    finding_path.write_text(json.dumps(finding.as_dict()), encoding="utf-8")

    before = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file()
    }

    def fail_if_subprocess_called(*args, **kwargs):
        raise AssertionError("offline proposed-only remediation must not invoke subprocess")

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess_called)
    result = main(
        [
            "remediate",
            str(repo),
            "--finding",
            str(finding_path),
            "--offline",
            "--no-update-lockfile",
            "--json",
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    plan = json.loads(output)
    assert plan["proposed_only"] is True
    assert plan["manifest_patch"]["package"] == "missingpkg"
    assert plan["lockfile_plan"] is None
    assert all(term not in output.lower() for term in ("publish", "deploy", "contact", "network"))

    after = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file()
    }
    assert after == before
