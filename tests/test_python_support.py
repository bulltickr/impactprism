import json
import shutil

import pytest

from impactprism import budgets
from impactprism.analysis import generate_sbom
from impactprism.drift import FindingType, analyze_repo, classify_python
from impactprism.manifest import parse_lockfile, parse_manifest
from impactprism.remediation.remediate import _detect_ecosystem
from impactprism.python_imports import ImportRecord, parse_imports, scan_imports


def _copy_fixture(tmp_path):
    source = __import__("pathlib").Path(__file__).parent / "fixtures" / "python_repo"
    destination = tmp_path / "python_repo"
    shutil.copytree(source, destination)
    return destination


def test_python_manifests_and_poetry_lockfile_use_existing_models(tmp_path):
    repo = _copy_fixture(tmp_path)
    manifest = parse_manifest(repo)
    assert manifest.name == "fixture-python-app"
    assert manifest.by_name("requests").locked_version == "2.32.3"
    assert manifest.by_name("pytest").kind == "devDependencies"
    lockfile = parse_lockfile(repo)
    assert lockfile.kind == "poetry"
    assert lockfile.resolved_versions["beautifulsoup4"] == "4.12.3"


def test_python_lockfile_parsers_cover_uv_and_pipenv(tmp_path):
    uv = tmp_path / "uv"
    uv.mkdir()
    (uv / "pyproject.toml").write_text('[project]\ndependencies=["Demo-Pkg"]\n')
    (uv / "uv.lock").write_text('[[package]]\nname="demo-pkg"\nversion="1.0.0"\n')
    assert parse_lockfile(uv).kind == "uv"
    assert parse_manifest(uv).by_name("Demo-Pkg").locked_version == "1.0.0"

    pipenv = tmp_path / "pipenv"
    pipenv.mkdir()
    (pipenv / "Pipfile").write_text('[packages]\nrequests="*"\n[dev-packages]\npytest="==8.0.0"\n')
    (pipenv / "Pipfile.lock").write_text(json.dumps({
        "default": {"requests": {"version": "==2.31.0"}},
        "develop": {"pytest": {"version": "==8.0.0"}},
    }))
    assert parse_lockfile(pipenv).kind == "pipenv"
    assert parse_manifest(pipenv).by_name("requests").locked_version == "2.31.0"

    requirements = tmp_path / "requirements"
    requirements.mkdir()
    (requirements / "requirements.txt").write_text("requests==2.31.0\n-r extra.txt\n")
    (requirements / "extra.txt").write_text("pytest>=8\n")
    assert parse_lockfile(requirements).kind == "requirements"
    assert parse_manifest(requirements).by_name("requests").locked_version == "2.31.0"


def test_python_import_parser_covers_static_dynamic_and_malformed():
    records = parse_imports(
        "import requests\nfrom bs4 import BeautifulSoup\n"
        "__import__('yaml')\nimportlib.import_module('toml')\n"
    )
    assert [(record.kind, record.specifier) for record in records] == [
        ("static", "requests"),
        ("static", "bs4"),
        ("dynamic", "yaml"),
        ("dynamic", "toml"),
    ]
    assert parse_imports("def broken(:\n") == []


def test_python_import_parser_covers_importlib_imported_alias():
    records = parse_imports(
        "from importlib import import_module as load_module\n"
        "load_module('runtime_pkg')\n"
    )

    assert [(record.kind, record.specifier) for record in records] == [
        ("static", "importlib"),
        ("dynamic", "runtime_pkg"),
    ]


def test_python_non_literal_dynamic_module_names_are_not_guessed():
    records = parse_imports(
        "from importlib import import_module\n"
        "import_module(module_name)\n"
    )

    assert [(record.kind, record.specifier) for record in records] == [
        ("static", "importlib")
    ]


def test_python_import_scan_enforces_budgets(tmp_path):
    (tmp_path / "app.py").write_text("import requests\n")
    with pytest.raises(budgets.ScannerBudgetError):
        scan_imports(tmp_path, max_files=0)
    with pytest.raises(budgets.ScannerBudgetError):
        scan_imports(tmp_path, max_file_bytes=1)


def test_classify_python_finding_types_provenance_and_commit(tmp_path):
    repo = _copy_fixture(tmp_path)
    report = analyze_repo(repo, ecosystem="python", commit_sha="abc123")
    by_type = {finding.finding_type for finding in report}
    assert FindingType.UNDECLARED_DIRECT_USE in by_type
    assert FindingType.UNRESOLVED_IMPORT in by_type
    undeclared = next(
        finding for finding in report if finding.finding_type == FindingType.UNDECLARED_DIRECT_USE
    )
    assert undeclared.ecosystem == "python"
    assert undeclared.commit_sha == "abc123"
    assert undeclared.file.endswith("app.py")
    assert undeclared.line == 5
    assert undeclared.column is not None
    assert "dynamic" in undeclared.explanation


def test_python_sbom_uses_pypi_purls(tmp_path):
    repo = _copy_fixture(tmp_path)
    sbom = generate_sbom(repo)
    purls = {component["purl"] for component in sbom["components"]}
    assert "pkg:pypi/requests@2.32.3" in purls
    assert "pkg:pypi/beautifulsoup4@4.12.3" in purls


def test_python_detection_dispatches_in_remediation(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    assert _detect_ecosystem(tmp_path) == "python"
