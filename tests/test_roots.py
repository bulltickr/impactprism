import json

import pytest

from impactprism.scan_service import scan_repository
from impactprism.scope import normalize_roots


def _workspace_repo(tmp_path):
    repo = tmp_path / "repo"
    app = repo / "apps" / "web"
    shared = repo / "packages" / "shared"
    app.mkdir(parents=True)
    shared.mkdir(parents=True)
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "root",
                "version": "1.0.0",
                "workspaces": ["apps/*", "packages/*"],
                "dependencies": {"root-only": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (app / "package.json").write_text(
        json.dumps(
            {
                "name": "@demo/web",
                "version": "1.0.0",
                "dependencies": {"@demo/shared": "workspace:*", "react": "18.2.0"},
            }
        ),
        encoding="utf-8",
    )
    (shared / "package.json").write_text(
        json.dumps({"name": "@demo/shared", "version": "1.0.0"}),
        encoding="utf-8",
    )
    (repo / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "root", "version": "1.0.0"},
                    "node_modules/react": {"version": "18.2.0"},
                },
            }
        ),
        encoding="utf-8",
    )
    (app / "index.js").write_text(
        "import shared from '@demo/shared';\nimport React from 'react';\n",
        encoding="utf-8",
    )
    (shared / "index.js").write_text(
        "import hidden from 'workspace-only';\n", encoding="utf-8"
    )
    return repo


def test_normalize_roots_is_literal_deterministic_and_rejects_overlap():
    assert normalize_roots(["./packages/shared", "apps\\web", "apps\\web"]) == (
        "apps/web",
        "packages/shared",
    )
    with pytest.raises(ValueError, match="overlap"):
        normalize_roots(["packages", "packages/shared"])
    with pytest.raises(ValueError, match="traversal"):
        normalize_roots(["../outside"])
    with pytest.raises(ValueError, match="at least one"):
        normalize_roots([])


def test_explicit_npm_root_limits_findings_metadata_and_sbom_but_keeps_workspace_resolution(
    tmp_path,
):
    repo = _workspace_repo(tmp_path)

    result = scan_repository(repo, ecosystem="npm", roots=["apps/web"])

    packages = {finding["package"] for finding in result.findings}
    assert "workspace-only" not in packages
    assert not any(finding["finding_type"] == "UNRESOLVED_IMPORT" for finding in result.findings)
    assert result.report["package_name"] == "@demo/web"
    assert result.report["declared"] == ["@demo/shared", "react"]
    assert "root-only" not in result.report["declared"]
    assert result.report["imported"] == ["@demo/shared", "react"]
    assert result.report["scope"]["roots"] == ["apps/web"]
    assert result.report["scope"]["root_selection"] == "explicit"
    assert {component["purl"] for component in result.sbom["components"]} == {
        "pkg:npm/%40demo/shared@workspace:%2A",
        "pkg:npm/react@18.2.0",
    }


@pytest.mark.parametrize(
    "roots, message",
    [
        (["missing"], "directory not found"),
        (["packages"], "must contain package.json"),
        (["apps/web", "apps/web"], None),
    ],
)
def test_explicit_roots_validate_package_boundaries(tmp_path, roots, message):
    repo = _workspace_repo(tmp_path)
    if message is None:
        result = scan_repository(repo, ecosystem="npm", roots=roots)
        assert result.report["scope"]["roots"] == ["apps/web"]
    else:
        with pytest.raises(ValueError, match=message):
            scan_repository(repo, ecosystem="npm", roots=roots)


def test_roots_are_rejected_for_non_npm_ecosystems(tmp_path):
    repo = tmp_path / "python-repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\nversion = '1.0.0'\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="only for npm"):
        scan_repository(repo, ecosystem="python", roots=["."])
