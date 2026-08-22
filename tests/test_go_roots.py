from __future__ import annotations

import json
from pathlib import Path

import pytest

from impactprism.go_imports import build_import_graph, scan_go_imports
from impactprism.go_mod import parse_go_manifest, validate_go_module_roots
from impactprism.cli import main as cli_main
from impactprism.scan_service import detect_ecosystem, scan_repository


def write_file(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def workspace_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "workspace"
    write_file(
        repo,
        "go.work",
        "go 1.22\n\nuse (\n\t./apps/app\n\t./libs/shared\n)\n",
    )
    write_file(
        repo,
        "apps/app/go.mod",
        "module example.com/app\n\ngo 1.22\n\n"
        "require (\n"
        "\texample.com/shared v0.0.0\n"
        "\texample.com/appdep v1.2.3\n"
        ")\n",
    )
    write_file(
        repo,
        "apps/app/main.go",
        "package main\n\nimport (\n\t\"example.com/shared/pkg\"\n\t\"example.com/appdep/api\"\n\t\"example.com/missing/api\"\n)\n\nvar _ = pkg.Value\nvar _ = api.Value\n",
    )
    write_file(
        repo,
        "libs/shared/go.mod",
        "module example.com/shared\n\ngo 1.22\n\n"
        "require example.com/shared-only v2.0.0\n",
    )
    write_file(
        repo,
        "libs/shared/pkg/shared.go",
        "package pkg\n\nconst Value = 1\n",
    )
    return repo


def test_go_workspace_without_root_go_mod_is_detected_and_parsed(tmp_path):
    repo = workspace_repo(tmp_path)

    assert detect_ecosystem(repo) == "go"
    manifest = parse_go_manifest(repo)

    assert manifest.main_modules == ("example.com/app", "example.com/shared")
    assert manifest.module_roots["example.com/app"] == (repo / "apps/app").resolve()
    assert manifest.module_roots["example.com/shared"] == (repo / "libs/shared").resolve()
    graph = build_import_graph(repo)
    assert graph.selected_module_paths is None
    assert graph.unresolved == ["example.com/missing/api"]


def test_explicit_go_root_limits_source_declarations_and_sbom(tmp_path):
    repo = workspace_repo(tmp_path)

    result = scan_repository(repo, ecosystem="go", roots=["apps/app"])

    assert result.report["scope"]["roots"] == ["apps/app"]
    assert result.report["scope"]["root_selection"] == "explicit"
    assert "example.com/appdep" in result.report["declared"]
    assert "example.com/shared-only" not in result.report["declared"]
    assert result.report["counts"]["total"] == 1
    assert result.findings[0]["package"] == "example.com/missing/api"
    assert {
        component["purl"] for component in result.sbom["components"]
    } == {"pkg:golang/example.com/appdep@v1.2.3"}

    graph = build_import_graph(repo, roots=["apps/app"])
    assert all(
        path.resolve().is_relative_to((repo / "apps/app").resolve())
        for path in graph.sources
    )
    assert graph.selected_module_paths == ("example.com/app",)


def test_go_root_selection_preserves_workspace_resolution_context(tmp_path):
    repo = workspace_repo(tmp_path)

    sources = scan_go_imports(repo, roots=["apps/app"])
    imports = [item.module_path for records in sources.values() for item in records]
    assert "example.com/shared/pkg" in imports

    graph = build_import_graph(repo, roots=["apps/app"])
    shared_edges = [
        edge for edge in graph.package_edges if edge.import_path == "example.com/shared/pkg"
    ]
    assert len(shared_edges) == 1
    assert shared_edges[0].resolved is not None
    assert shared_edges[0].resolved.module_path == "example.com/shared"
    assert graph.unresolved == ["example.com/missing/api"]


@pytest.mark.parametrize(
    "roots, message",
    [
        (["."], "must contain go.mod"),
        (["apps/app/main.go"], "directory not found"),
        (["../outside"], "parent-directory traversal"),
        (["missing"], "directory not found"),
        (["libs"], "must contain go.mod"),
    ],
)
def test_go_roots_reject_non_module_or_unsafe_selection(tmp_path, roots, message):
    repo = workspace_repo(tmp_path)

    with pytest.raises(ValueError, match=message):
        validate_go_module_roots(repo, roots)


def test_go_roots_reject_excluded_and_duplicate_module_selection(tmp_path):
    repo = workspace_repo(tmp_path)
    write_file(repo, "apps/other/go.mod", "module example.com/shared\ngo 1.22\n")

    with pytest.raises(ValueError, match="excluded"):
        validate_go_module_roots(repo, ["apps/app"], exclude={"apps/app"})
    with pytest.raises(ValueError, match="same module twice"):
        validate_go_module_roots(repo, ["apps/other", "libs/shared"])


def test_go_root_report_remains_json_serializable(tmp_path):
    result = scan_repository(workspace_repo(tmp_path), ecosystem="go", roots=["libs/shared"])
    json.dumps(result.report)
    json.dumps(result.sbom)


def test_explicit_go_root_uses_selected_module_go_sum(tmp_path):
    repo = workspace_repo(tmp_path)
    write_file(repo, "apps/app/go.sum", "example.com/other v1.0.0 h1:not-appdep\n")

    result = scan_repository(repo, ecosystem="go", roots=["apps/app"])

    mismatches = [
        finding
        for finding in result.findings
        if finding["finding_type"] == "LOCKFILE_MANIFEST_MISMATCH"
    ]
    assert [finding["package"] for finding in mismatches] == ["example.com/appdep"]
    assert mismatches[0]["lockfile"] == str((repo / "apps/app/go.sum").resolve())


def test_configured_go_roots_match_explicit_scan_scope(tmp_path, capsys):
    repo = workspace_repo(tmp_path)
    (repo / ".impactprism.toml").write_text(
        '[scan]\nroots = ["apps/app"]\n',
        encoding="utf-8",
    )
    report_path = repo / "configured-go-roots.json"

    assert cli_main(
        [
            "scan",
            str(repo),
            "--ecosystem",
            "go",
            "--fail-on",
            "never",
            "--report",
            str(report_path),
        ]
    ) == 0
    capsys.readouterr()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scope"]["roots"] == ["apps/app"]
    assert report["scope"]["root_selection"] == "explicit"
    assert "example.com/shared-only" not in report["declared"]
