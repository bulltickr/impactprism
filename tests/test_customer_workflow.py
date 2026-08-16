import json
from pathlib import Path

from impactprism.cli import main
from impactprism.drift import FindingType, classifier


def test_public_remediate_plans_offline_demo_without_mutating_fixture(tmp_path, capsys):
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

    result = main(
        [
            "remediate",
            str(repo),
            "--finding",
            str(finding_path),
            "--offline",
            "--json",
        ]
    )

    assert result == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["proposed_only"] is True
    assert plan["manifest_patch"] is not None
    assert plan["manifest_patch"]["package"] == "missingpkg"

    after = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_public_remediate_returns_nonzero_for_remediation_error(tmp_path, capsys):
    repo = Path(__file__).parents[1] / "demo" / "npm-app"
    finding_path = tmp_path / "unsupported-finding.json"
    finding_path.write_text(
        json.dumps(
            {
                "finding_type": FindingType.DECLARED_UNUSED_CANDIDATE.name,
                "ecosystem": "npm",
                "package": "missingpkg",
            }
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "remediate",
            str(repo),
            str(finding_path),
            "--no-update-lockfile",
            "--no-verify",
        ]
    )

    assert result != 0
    assert "error:" in capsys.readouterr().err
