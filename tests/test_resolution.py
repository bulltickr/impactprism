import json

from impactprism.drift.classifier import analyze_repo


def _write(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _finding_types(report):
    return [finding.finding_type.value for finding in report]


def test_tsconfig_jsonc_aliases_are_local_and_missing_targets_are_explicit(tmp_path):
    repo = tmp_path / "tsconfig-aliases"
    _write(repo, "package.json", json.dumps({"name": "aliases", "version": "1.0.0"}))
    _write(
        repo,
        "tsconfig.json",
        '''{
          // JSONC is accepted because tsconfig files commonly contain comments.
          "compilerOptions": {
            "baseUrl": ".",
            "paths": {
              "@/*": ["src/*"],
            },
          },
        }''',
    )
    _write(repo, "src/value.ts", "export default 1;\n")
    _write(
        repo,
        "src/index.ts",
        'import value from "@/value";\nimport missing from "@/missing";\n',
    )

    report = analyze_repo(str(repo), ecosystem="npm")

    assert _finding_types(report) == ["UNRESOLVED_IMPORT"]
    finding = report.findings[0]
    assert finding.package == "@/missing"
    assert "tsconfig path alias" in finding.explanation


def test_workspace_exports_and_package_imports_are_local(tmp_path):
    repo = tmp_path / "workspace-resolution"
    _write(
        repo,
        "package.json",
        json.dumps(
            {
                "name": "workspace-root",
                "version": "1.0.0",
                "private": True,
                "workspaces": ["packages/*"],
            }
        ),
    )
    _write(repo, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {}}))
    _write(
        repo,
        "packages/app/package.json",
        json.dumps(
            {
                "name": "workspace-app",
                "version": "1.0.0",
                "imports": {"#local/*": "./src/*"},
            }
        ),
    )
    _write(repo, "packages/app/src/value.js", "export default 1;\n")
    _write(
        repo,
        "packages/app/src/index.js",
        'import shared from "@scope/shared/feature";\n'
        'import local from "#local/value";\n',
    )
    _write(
        repo,
        "packages/shared/package.json",
        json.dumps(
            {
                "name": "@scope/shared",
                "version": "1.0.0",
                "exports": {
                    ".": "./src/index.js",
                    "./feature": {
                        "import": "./src/feature.js",
                        "default": "./src/feature.js",
                    },
                },
            }
        ),
    )
    _write(repo, "packages/shared/src/index.js", "export default 1;\n")
    _write(repo, "packages/shared/src/feature.js", "export default 1;\n")

    report = analyze_repo(str(repo), ecosystem="npm")

    assert list(report) == []


def test_workspace_export_boundary_is_reported(tmp_path):
    repo = tmp_path / "workspace-export-boundary"
    _write(
        repo,
        "package.json",
        json.dumps(
            {
                "name": "workspace-root",
                "version": "1.0.0",
                "private": True,
                "workspaces": ["packages/*"],
            }
        ),
    )
    _write(repo, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {}}))
    _write(
        repo,
        "packages/app/package.json",
        json.dumps({"name": "workspace-app", "version": "1.0.0"}),
    )
    _write(
        repo,
        "packages/app/src/index.js",
        'import hidden from "@scope/shared/private";\n',
    )
    _write(
        repo,
        "packages/shared/package.json",
        json.dumps(
            {
                "name": "@scope/shared",
                "version": "1.0.0",
                "exports": {".": "./src/index.js"},
            }
        ),
    )
    _write(repo, "packages/shared/src/index.js", "export default 1;\n")

    report = analyze_repo(str(repo), ecosystem="npm")

    assert _finding_types(report) == ["UNRESOLVED_IMPORT"]
    assert report.findings[0].package == "@scope/shared/private"
    assert "does not export" in report.findings[0].explanation


def test_unmapped_package_import_is_not_misclassified_as_a_third_party_package(tmp_path):
    repo = tmp_path / "package-import-boundary"
    _write(
        repo,
        "package.json",
        json.dumps(
            {
                "name": "package-import-boundary",
                "version": "1.0.0",
                "imports": {"#local/*": "./src/*"},
            }
        ),
    )
    _write(repo, "src/index.js", 'import missing from "#missing";\n')

    report = analyze_repo(str(repo), ecosystem="npm")

    assert _finding_types(report) == ["UNRESOLVED_IMPORT"]
    assert report.findings[0].package == "#missing"
    assert "not declared" in report.findings[0].explanation


def test_tsconfig_alias_cannot_resolve_outside_repository(tmp_path):
    repo = tmp_path / "contained"
    outside = tmp_path / "outside"
    _write(repo, "package.json", json.dumps({"name": "contained", "version": "1.0.0"}))
    _write(
        repo,
        "tsconfig.json",
        json.dumps({"compilerOptions": {"paths": {"@outside/*": ["../outside/*"]}}}),
    )
    _write(outside, "secret.js", "export default 'outside';\n")
    _write(repo, "src/index.js", 'import secret from "@outside/secret";\n')

    report = analyze_repo(str(repo), ecosystem="npm")

    assert _finding_types(report) == ["UNRESOLVED_IMPORT"]
    assert "no existing target" in report.findings[0].explanation
