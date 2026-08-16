import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from impactprism.cra_clauses import load_cra_clauses
from impactprism.evidence import CLAUSE_MAP, EVIDENCE_STATUSES, main

UNDECLARED_CLAUSES = ["Art 13(1)(b)", "Art 14(1)", "Annex I Part II", "Annex VII"]
DRIFT_CLAUSES = ["Art 13(1)(a)", "Annex I Part I"]


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


def test_clause_map_exact():
    assert CLAUSE_MAP["undeclared"] == UNDECLARED_CLAUSES
    assert CLAUSE_MAP["drift"] == DRIFT_CLAUSES


def test_clause_map_derived_from_canonical():
    clause_map = load_cra_clauses()
    expected = {
        category: entry["clauses"]
        for category, entry in clause_map["categories"].items()
    }
    assert CLAUSE_MAP == expected
    for clauses in CLAUSE_MAP.values():
        for clause_id in clauses:
            assert clause_id in clause_map["clauses"]


def test_main_defaults_write_evidence_files(tmp_path, monkeypatch):
    report_path = make_report(tmp_path, drift=["react"], undeclared=["lodash"])
    monkeypatch.chdir(tmp_path)
    assert main([str(report_path)]) == 0
    md_path = tmp_path / "evidence.md"
    json_path = tmp_path / "evidence.json"
    assert md_path.is_file()
    assert json_path.is_file()
    markdown = md_path.read_text(encoding="utf-8")
    assert "lodash" in markdown
    assert "react" in markdown
    for clause in UNDECLARED_CLAUSES + DRIFT_CLAUSES:
        assert clause in markdown
    evidence = json.loads(json_path.read_text(encoding="utf-8"))
    assert evidence["generator"] == "impactprism-evidence"
    assert evidence["package_name"] == "repo"
    assert evidence["package_version"] == "1.0.0"
    assert evidence["summary"]["total_findings"] == 2
    assert evidence["summary"]["undeclared_count"] == 1
    assert evidence["summary"]["drift_count"] == 1
    assert evidence["summary"]["clean"] is False
    by_name = {finding["name"]: finding for finding in evidence["findings"]}
    assert by_name["lodash"]["category"] == "undeclared"
    assert by_name["lodash"]["clauses"] == UNDECLARED_CLAUSES
    assert by_name["react"]["category"] == "drift"
    assert by_name["react"]["clauses"] == DRIFT_CLAUSES


def test_evidence_metadata_and_statuses(tmp_path, monkeypatch):
    report_path = make_report(tmp_path, drift=["react"], undeclared=["lodash"])
    monkeypatch.chdir(tmp_path)
    assert main([str(report_path)]) == 0
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    clause_map = load_cra_clauses()
    assert evidence["schema_version"] == 2
    assert evidence["map_version"]
    assert evidence["legal_source"]
    assert evidence["schema_version"] == clause_map["schema_version"]
    assert evidence["map_version"] == clause_map["map_version"]
    assert evidence["legal_source"] == clause_map["legal_source"]
    assert list(evidence["statuses"]) == list(EVIDENCE_STATUSES)
    assert evidence["overall_status"] == "REVIEW_REQUIRED"
    status_counts = evidence["summary"]["status_counts"]
    assert sum(status_counts.values()) == evidence["summary"]["total_findings"]
    assert set(status_counts) == set(EVIDENCE_STATUSES)
    assert status_counts["REVIEW_REQUIRED"] == 2
    for finding in evidence["findings"]:
        assert finding["status"] in EVIDENCE_STATUSES
        assert finding["status"] == "REVIEW_REQUIRED"
        assert finding["status"] != "FAIL"


def test_main_markdown_and_json_flags(tmp_path):
    report_path = make_report(tmp_path, undeclared=["lodash"])
    md_path = tmp_path / "custom-evidence.md"
    json_path = tmp_path / "custom-evidence.json"
    code = main([str(report_path), "--markdown", str(md_path), "--json", str(json_path)])
    assert code == 0
    assert md_path.is_file()
    assert json_path.is_file()
    assert "Art 14(1)" in md_path.read_text(encoding="utf-8")
    assert not (tmp_path / "evidence.md").is_file()
    assert not (tmp_path / "evidence.json").is_file()


def test_main_stdout_prints_json(tmp_path, monkeypatch, capsys):
    report_path = make_report(tmp_path, drift=["react"], undeclared=["lodash"])
    monkeypatch.chdir(tmp_path)
    assert main([str(report_path), "--stdout"]) == 0
    captured = capsys.readouterr()
    evidence = json.loads(captured.out)
    assert evidence["summary"]["total_findings"] == 2
    assert evidence["clause_map"] == CLAUSE_MAP
    assert evidence["overall_status"] == "REVIEW_REQUIRED"
    assert not (tmp_path / "evidence.json").is_file()


def test_main_clean_report(tmp_path, monkeypatch):
    report_path = make_report(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main([str(report_path)]) == 0
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["findings"] == []
    assert evidence["summary"]["clean"] is True
    assert evidence["overall_status"] == "PASS"
    assert evidence["summary"]["status_counts"] == {
        status: 0 for status in EVIDENCE_STATUSES
    }
    markdown = (tmp_path / "evidence.md").read_text(encoding="utf-8")
    assert (
        "No supported dependency findings were detected; this is not a compliance determination."
        in markdown
    )
    assert "evidence of compliant dependency management (PASS)" not in markdown


def test_main_missing_report_exit_2(tmp_path):
    missing = tmp_path / "nope.json"
    assert main([str(missing)]) == 2


def test_main_invalid_report_exit_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert main([str(bad)]) == 2

    array = tmp_path / "array.json"
    array.write_text("[1, 2, 3]", encoding="utf-8")
    assert main([str(array)]) == 2

    wrong_type = tmp_path / "wrong-type.json"
    wrong_type.write_text(json.dumps({"undeclared": "not-a-list"}), encoding="utf-8")
    assert main([str(wrong_type)]) == 2


def test_clause_strings_appear_in_outputs(tmp_path, monkeypatch):
    report_path = make_report(tmp_path, drift=["react"], undeclared=["lodash"])
    monkeypatch.chdir(tmp_path)
    assert main([str(report_path)]) == 0
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "evidence.md").read_text(encoding="utf-8")
    assert evidence["clause_map"] == CLAUSE_MAP
    assert "CRA references" in markdown
    for clause in UNDECLARED_CLAUSES + DRIFT_CLAUSES:
        assert clause in markdown


def test_markdown_header_and_status_lines(tmp_path, monkeypatch):
    report_path = make_report(tmp_path, drift=["react"], undeclared=["lodash"])
    monkeypatch.chdir(tmp_path)
    assert main([str(report_path)]) == 0
    markdown = (tmp_path / "evidence.md").read_text(encoding="utf-8")
    assert "Schema version: 2" in markdown
    assert "Map version: 1.0.0" in markdown
    assert "Legal source: " in markdown
    assert "Overall status: REVIEW_REQUIRED" in markdown
    assert "Status: REVIEW_REQUIRED" in markdown
