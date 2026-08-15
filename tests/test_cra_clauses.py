import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cra_clauses import DEFAULT_PATH, load_cra_clauses, main

MAIN_CLAUSES = [
    "Art 13(1)(a)",
    "Art 13(1)(b)",
    "Art 14(1)",
    "Annex I Part I",
    "Annex I Part II",
    "Annex VII",
]
ANALYSIS_DETECTORS = {"dependency_drift", "undeclared_dependency"}


def write_yaml(tmp_path, content, name="cra_clauses.yaml"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def data():
    return load_cra_clauses()


def test_default_file_exists():
    assert DEFAULT_PATH.is_file()


def test_loads_default_file(data):
    assert isinstance(data, dict)
    assert data["schema_version"] == 1
    assert data["description"]
    assert isinstance(data["clauses"], dict)


def test_main_clauses_present(data):
    for clause_id in MAIN_CLAUSES:
        assert clause_id in data["clauses"]


def test_clause_shape(data):
    for clause_id, clause in data["clauses"].items():
        assert clause["id"] == clause_id
        assert clause["title"]
        checks = clause["checks"]
        assert isinstance(checks, list) and checks
        for check in checks:
            assert check["detector"]
            assert check["requirement"]


def test_detectors_unique_per_clause(data):
    for clause in data["clauses"].values():
        detectors = [check["detector"] for check in clause["checks"]]
        assert len(detectors) == len(set(detectors))


def test_analysis_detectors_covered(data):
    detectors = {
        check["detector"]
        for clause in data["clauses"].values()
        for check in clause["checks"]
    }
    assert ANALYSIS_DETECTORS <= detectors


def test_explicit_path_equals_default():
    assert load_cra_clauses(DEFAULT_PATH) == load_cra_clauses()


def test_load_from_temp_copy(tmp_path):
    copy = write_yaml(tmp_path, DEFAULT_PATH.read_text(encoding="utf-8"))
    assert load_cra_clauses(copy) == load_cra_clauses()


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cra_clauses(tmp_path / "nope.yaml")


def test_invalid_yaml_raises(tmp_path):
    bad = write_yaml(
        tmp_path,
        "schema_version: 1\nclauses:\n\t\"Art 13(1)(a)\":\n",
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_duplicate_detector_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        "schema_version: 1\n"
        "clauses:\n"
        '  "Art 13(1)(a)":\n'
        '    id: "Art 13(1)(a)"\n'
        '    title: "T"\n'
        "    checks:\n"
        '      - detector: "dup"\n'
        '        requirement: "one"\n'
        '      - detector: "dup"\n'
        '        requirement: "two"\n',
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_missing_checks_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        "schema_version: 1\n"
        "clauses:\n"
        '  "Art 13(1)(a)":\n'
        '    id: "Art 13(1)(a)"\n'
        '    title: "T"\n',
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_id_mismatch_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        "schema_version: 1\n"
        "clauses:\n"
        '  "Art 13(1)(a)":\n'
        '    id: "Art 99"\n'
        '    title: "T"\n'
        "    checks:\n"
        '      - detector: "x"\n'
        '        requirement: "y"\n',
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_cli_default_returns_zero(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "Loaded " in output
    for clause_id in MAIN_CLAUSES:
        assert clause_id in output


def test_cli_missing_path_returns_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope.yaml")]) == 2
    assert "error:" in capsys.readouterr().err


def test_roundtrip_equal(data):
    assert load_cra_clauses() == data
