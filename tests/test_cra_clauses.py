import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from impactprism.cra_clauses import DEFAULT_PATH, load_cra_clauses, main

MAIN_CLAUSES = [
    "Art 13(1)(a)",
    "Art 13(1)(b)",
    "Art 14(1)",
    "Annex I Part I",
    "Annex I Part II",
    "Annex VII",
]
EXPECTED_CATEGORIES = {
    "undeclared": ["Art 13(1)(b)", "Art 14(1)", "Annex I Part II", "Annex VII"],
    "drift": ["Art 13(1)(a)", "Annex I Part I"],
}
ANALYSIS_DETECTORS = {"dependency_drift", "undeclared_dependency"}
VALID_STATUSES = {"ACTIVE", "PLANNED", "DEPRECATED"}

_TOP_HEADER = (
    "schema_version: 2\n"
    "map_version: \"1.0.0\"\n"
    "legal_source: \"Regulation (EU) 2024/2847\"\n"
    "description: \"Test map\"\n"
)

VALID_CLAUSE = (
    '  "Art 13(1)(a)":\n'
    '    id: "Art 13(1)(a)"\n'
    '    legal_reference: "Article 13(1)(a)"\n'
    '    title: "Secure by default"\n'
    '    applicability: "All digital products"\n'
    "    detectors:\n"
    '      - "dependency_drift"\n'
    "    evidence_requirements:\n"
    '      - "Unused dependencies are removed."\n'
    "    limitations:\n"
    '      - "Static analysis cannot prove runtime usage."\n'
    '    status: "ACTIVE"\n'
)


def write_yaml(tmp_path, content, name="cra_clauses.yaml"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def clause_map_yaml(clause=VALID_CLAUSE):
    return _TOP_HEADER + "clauses:\n" + clause


def with_replacement(text, old, new):
    assert old in text, repr(old)
    return text.replace(old, new)


@pytest.fixture
def data():
    return load_cra_clauses()


def test_default_file_exists():
    assert DEFAULT_PATH.is_file()


def test_loads_default_file(data):
    assert isinstance(data, dict)
    assert data["schema_version"] == 2
    assert data["map_version"]
    assert data["legal_source"]
    assert data["description"]
    assert isinstance(data["clauses"], dict)


def test_main_clauses_present(data):
    for clause_id in MAIN_CLAUSES:
        assert clause_id in data["clauses"]


def test_categories_map_to_existing_clauses(data):
    categories = data["categories"]
    assert categories["undeclared"]["clauses"] == EXPECTED_CATEGORIES["undeclared"]
    assert categories["drift"]["clauses"] == EXPECTED_CATEGORIES["drift"]
    for entry in categories.values():
        for clause_id in entry["clauses"]:
            assert clause_id in data["clauses"]


def test_clause_shape(data):
    for clause_id, clause in data["clauses"].items():
        assert clause["id"] == clause_id
        assert clause["legal_reference"]
        assert clause["title"]
        assert clause["applicability"]
        detectors = clause["detectors"]
        assert isinstance(detectors, list) and detectors
        assert all(isinstance(detector, str) and detector for detector in detectors)
        assert len(detectors) == len(set(detectors))
        evidence_requirements = clause["evidence_requirements"]
        assert isinstance(evidence_requirements, list) and evidence_requirements
        assert all(
            isinstance(requirement, str) and requirement
            for requirement in evidence_requirements
        )
        limitations = clause["limitations"]
        assert isinstance(limitations, list)
        assert all(isinstance(limitation, str) for limitation in limitations)
        assert clause["status"] in VALID_STATUSES


def test_detectors_unique_per_clause(data):
    for clause in data["clauses"].values():
        detectors = clause["detectors"]
        assert len(detectors) == len(set(detectors))


def test_analysis_detectors_covered(data):
    detectors = {
        detector
        for clause in data["clauses"].values()
        for detector in clause["detectors"]
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
        "schema_version: 2\nclauses:\n\t\"Art 13(1)(a)\":\n",
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_wrong_schema_version_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(clause_map_yaml(), "schema_version: 2", "schema_version: 1"),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_missing_legal_source_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(
            clause_map_yaml(),
            'legal_source: "Regulation (EU) 2024/2847"\n',
            "",
        ),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_duplicate_detector_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(
            clause_map_yaml(),
            '      - "dependency_drift"\n',
            '      - "dup"\n'
            '      - "dup"\n',
        ),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_missing_detectors_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(
            clause_map_yaml(),
            "    detectors:\n"
            '      - "dependency_drift"\n',
            "",
        ),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_empty_evidence_requirements_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(
            clause_map_yaml(),
            "    evidence_requirements:\n"
            '      - "Unused dependencies are removed."\n',
            "    evidence_requirements:\n",
        ),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_invalid_clause_status_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(clause_map_yaml(), '    status: "ACTIVE"', '    status: "WAT"'),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_id_mismatch_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(clause_map_yaml(), '    id: "Art 13(1)(a)"', '    id: "Art 99"'),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_categories_unknown_clause_rejected(tmp_path):
    categories_block = (
        "categories:\n"
        "  undeclared:\n"
        "    clauses:\n"
        '      - "Art 99"\n'
    )
    bad = write_yaml(
        tmp_path,
        with_replacement(clause_map_yaml(), "clauses:\n", categories_block + "clauses:\n"),
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


def test_inline_yaml_comments_are_ignored(tmp_path):
    yaml_text = clause_map_yaml()
    yaml_text = with_replacement(
        yaml_text,
        'map_version: "1.0.0"\n',
        'map_version: "1.0.0" # c\n',
    )
    yaml_text = with_replacement(
        yaml_text,
        'legal_source: "Regulation (EU) 2024/2847"\n',
        'legal_source: "Regulation (EU) 2024/2847" # cite\n',
    )
    path = write_yaml(tmp_path, yaml_text)
    data = load_cra_clauses(path)
    assert data["map_version"] == "1.0.0"
    assert data["legal_source"] == "Regulation (EU) 2024/2847"


def test_duplicate_top_level_key_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(
            clause_map_yaml(),
            'map_version: "1.0.0"\n',
            'map_version: "1.0.0"\nmap_version: "2.0.0"\n',
        ),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)


def test_duplicate_clause_key_rejected(tmp_path):
    bad = write_yaml(
        tmp_path,
        with_replacement(
            clause_map_yaml(),
            '  "Art 13(1)(a)":\n',
            '  "Art 13(1)(a)":\n  "Art 13(1)(a)":\n',
        ),
    )
    with pytest.raises(ValueError):
        load_cra_clauses(bad)
