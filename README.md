# ImpactPrism

Offline dependency-integrity analysis and release-evidence preflight for selected npm, Python, and Go supply-chain controls. ImpactPrism compares supported manifests, lockfiles, and source imports, then produces a CycloneDX SBOM and review-oriented evidence outputs.

[![CI](https://github.com/bulltickr/impactprism/actions/workflows/ci.yml/badge.svg)](https://github.com/bulltickr/impactprism/actions/workflows/ci.yml)

## Quickstart

The fastest way to scan a repository is a one-shot command that analyzes the repo and generates the evidence pack in a single step:

```bash
pipx run impactprism scan .
```

From a brand-new shell to a rendered evidence pack in three commands:

```bash
pipx run impactprism scan .
open evidence.md            # rendered Markdown preflight report
```

`scan` produces, in the current directory:

| File            | Contents |
|-----------------|----------|
| `evidence.md`   | Human-readable release-evidence preflight: findings, statuses, observed inputs, and rationale |
| `evidence.json` | Machine-readable release-evidence preflight (same findings, JSON) |
| `bom.json`      | CycloneDX SBOM — pass `--sbom bom.json` to write it |
| `report.json`   | Raw scan report — pass `--report report.json` to write it |

`pip install impactprism` (or `uv tool run impactprism`) installs the same `impactprism` CLI.

## What it detects

ImpactPrism cross-checks what supported manifests declare, what lockfiles pin, and what scanned source imports. Depending on the ecosystem and available files, selected checks cover drift, undeclared use, transitive use, scope mismatches, missing lockfiles, and manifest/lockfile mismatches. Findings and coverage depend on the inputs and scanner rules; they are not a complete assessment of a repository.

Given this manifest and import:

```json
// package.json
{
  "dependencies": { "react": "^18.2.0" },
  "devDependencies": { "jest": "^29.0.0" }
}
```

```js
// src/index.js
import _ from 'lodash';
import axios from 'axios';
```

| Finding type | One-line definition | In this example |
|--------------|---------------------|-----------------|
| `UNDECLARED_DIRECT_USE` | Imported in source but neither declared in `package.json` nor present in the lockfile. | `lodash` |
| `DECLARED_UNUSED_CANDIDATE` (drift) | Declared in `package.json` but never imported anywhere in the scanned source. | `react` |
| `DIRECT_DEPENDENCY_USED_TRANSITIVELY` | Imported directly in source but only resolvable through the lockfile — not declared. | `axios` (when present in the lockfile only) |
| `SCOPE_MISMATCH` | A dependency used outside its declared scope, e.g. a `devDependency` imported in production code, or a production dependency imported only in tests. | `jest` imported in production code |
| `MISSING_LOCKFILE` | A manifest declares at least one dependency but no effective lockfile (`package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`) exists; emitted once per manifest. | `package.json` without a lockfile |
| `LOCKFILE_MANIFEST_MISMATCH` | The manifest and lockfile disagree: a declared dependency with no locked version, a locked version outside the declared range, or a lockfile-only package that is neither declared nor imported. | `react` pinned to a version outside `^18.2.0` |

Two further findings are emitted but are not part of the core six: `UNRESOLVED_IMPORT` (an import that resolves to no existing file or module) and `SCANNER_ERROR` (a manifest that cannot be parsed, so a clean scan cannot be trusted).

## Demo and screenshots

Ready-made fixture apps with planted findings live in [demo/README.md](demo/README.md): `demo/npm-app` demonstrates drift and an undeclared dependency, `demo/clean-app` demonstrates a clean pass.

- [impactprism-scan-terminal.png](docs/screenshots/impactprism-scan-terminal.png) — `impactprism scan` terminal output with findings
- [evidence-pack-markdown.png](docs/screenshots/evidence-pack-markdown.png) — rendered Markdown evidence pack
- [github-action-pr-comment.png](docs/screenshots/github-action-pr-comment.png) — the GitHub Action posting an evidence summary as a PR comment
- [sample-sbom-snippet.png](docs/screenshots/sample-sbom-snippet.png) — a sample CycloneDX SBOM snippet

## GitHub Action

Add ImpactPrism to your pull requests in four lines:

```yaml
- name: ImpactPrism scan
  uses: bulltickr/impactprism@v0.2.0
  with:
    repo-path: ${{ github.workspace }}
    fail-on: finding
```

The composite action is fully offline (no account, no API key), produces `findings.json`, `bom.json`, `impactprism.sarif`, `evidence.json`/`evidence.md` and `summary.md`, uploads a SARIF report to code scanning, and exits per the `fail-on` policy (`never` | `finding` | `all`). The current action inputs are scoped to npm and Go; the CLI also supports selected Python checks. See [action/README.md](action/README.md) for inputs, outputs and required workflow permissions.

## Supported ecosystems

The CLI auto-detects supported project inputs. npm uses `package.json` and supported lockfiles; Python uses supported `pyproject.toml`, `Pipfile`, or `requirements.txt` inputs and lockfiles; Go uses `go.mod`, `go.work`, `go.sum`, and vendored module metadata. The GitHub Action can force `npm` or `go` via its `ecosystem` input.

- Python checks cover supported manifest/lockfile and import comparisons; coverage varies by packaging format and repository structure.

- Manifest sources: `go.mod` (module, `require`, `replace`), `go.work` (workspace member modules and their `replace` rules), `go.sum` (checksums), and `vendor/modules.txt` for vendored builds.
- A package-level import graph is aggregated to the module level; each module is classified by observed use (`used`/`direct`).
- Go findings: `UNDECLARED_DIRECT_USE` (imported but not declared in `go.mod`), `DECLARED_UNUSED_CANDIDATE` (direct dependency never imported), `DIRECT_DEPENDENCY_USED_TRANSITIVELY` (imported directly but only declared indirect), `LOCKFILE_MANIFEST_MISMATCH` (declared module with no `go.sum` entry) and `UNRESOLVED_IMPORT` (import resolves to no declared module).
- Standard-library and main-module imports are excluded from findings.

## Release-evidence preflight

`impactprism evidence <scan_report.json>` (or the `--evidence` flag on `scan`) turns the scan report into a release-evidence preflight in Markdown and JSON. It records the available inputs, findings, rationale, statuses, and configured reference mappings. `REVIEW_REQUIRED` means a person must examine the finding; `NOT_ASSESSED` means the relevant question was not established by the supported checks. A clean report means no supported check produced a finding in the scanned inputs; it does not establish that evidence is complete or that a project is compliant. See [docs/samples/evidence-sample.md](docs/samples/evidence-sample.md) for a rendered example.

| Evidence category | Reference mappings |
|-------------------|-------------|
| `undeclared` | Art 13(1)(b), Art 14(1), Annex I Part II, Annex VII |
| `drift` | Art 13(1)(a), Annex I Part I |

The repository's optional reference map is stored in [src/impactprism/cra_clauses.yaml](src/impactprism/cra_clauses.yaml) (schema v2, `map_version 1.0.0`). It provides contextual references for the preflight output; it does not determine legal applicability or compliance.

## Output formats

| Output | Format | Contents |
|--------|--------|----------|
| `findings.json` | JSON | Raw scan report produced by the GitHub Action |
| `bom.json` | CycloneDX 1.6 | SBOM with per-component hashes, scope, and `impactprism:direct`/`transitive`/`scope` properties plus a dependency graph |
| `impactprism.sarif` | SARIF 2.1.0 | Findings as code-scanning results with file/line locations |
| `evidence.json` / `evidence.md` | JSON / Markdown | Review-oriented preflight with findings, statuses, rationale, and configured reference mappings |
| `summary.md` | Markdown | Human-readable action outcome summary (also appended to the job step summary) |
| `--json` stdout | JSON | The scan report printed to stdout, including the `sbom` key |

## ImpactPrism vs. the alternatives

ImpactPrism is not a vulnerability scanner. Trivy and Dependency-Check tell you a declared component has a known CVE; ImpactPrism tells you there is a component in your code that nobody declared — the failure mode manifest-only tools cannot see.

| Dimension | ImpactPrism | CycloneDX CLI | Syft | Trivy | OWASP Dependency-Check |
|-----------|-------------|---------------|------|-------|-------------------------|
| SBOM generation | CycloneDX (npm, Python, Go) | CycloneDX (native, ~25 ecosystems) | SPDX + CycloneDX | CycloneDX + SPDX | CycloneDX (SPDX limited) |
| Drift/undeclared detection | Yes — core feature | No | No | No | No |
| Reference mappings | Optional contextual references in the preflight | No (raw SBOM) | No | No | No |
| Evidence preflight | Yes — Markdown + JSON for human review | No | No | No | No |
| Needs vulnerability DB | No | No | No | Yes (OSV/GHSA/trivy-db) | Yes (NVD) |
| Offline | Yes | Yes | Yes | Yes (with DB mirroring caveat) | Yes |

## Exit codes

| Command | 0 | 1 | 2 |
|---------|---|---|---|
| `scan` / `analyze` | Clean — no drift, undeclared or scope findings | Findings present | Error (bad path, missing manifest/lockfile, scanner error) |
| `evidence` / `clauses` | Success | — | Error (missing/invalid input, invalid clause map) |

## CLI reference

```
impactprism scan <repo> [--exclude PAT] [--sbom PATH] [--report PATH] [--evidence PATH] [--json]
impactprism analyze <repo_dir> [--exclude PAT] [--sbom PATH] [--report PATH] [--json]
impactprism evidence <scan_report> [--markdown PATH] [--json PATH] [--stdout]
impactprism clauses [path]
```

| Subcommand | Arguments | Flags |
|------------|-----------|-------|
| `scan` | `<repo>` — repository to scan | `--exclude PAT` (repeatable), `--sbom PATH`, `--report PATH`, `--evidence PATH`, `--json` |
| `analyze` | `<repo_dir>` — repository to analyze | `--exclude PAT` (repeatable), `--sbom PATH`, `--report PATH`, `--json` |
| `evidence` | `<scan_report>` — report JSON | `--markdown PATH` (default `evidence.md`), `--json PATH` (default `evidence.json`), `--stdout` |
| `clauses` | `[path]` — optional clause-map YAML | — |

`--exclude` skips directories by name (defaults: `tests`, `fixtures`, `demo`, `node_modules`, `build`, `dist`, `.git`, `.cache`, `coverage`, `public`). `impactprism scan` runs analyze + evidence in one shot; `python -m impactprism` is equivalent.

## Scope and limitations

ImpactPrism is an offline analysis and release-evidence preflight tool for selected npm, Python, and Go supply-chain controls. Findings require review. Evidence may be incomplete, and scope is unassessed outside the supported checks and the files available to the scan. The tool is not legal advice, certification, an audit opinion, or a compliance determination.

## Tests and development

```bash
pip install -e .[test]
python -m pytest tests -q
```

CI runs on every push and pull request on a Python 3.10 / 3.11 / 3.12 matrix: `pip install -e .[test]`, `python -m pytest -q`, `python -m build`, and an `impactprism scan .` exit-0 self-check.

## License, security, contributing, feedback

- **License** — [MIT](LICENSE), Copyright (c) 2026 ImpactPrism contributors.
- **Security** — report vulnerabilities privately via the [GitHub issues](https://github.com/bulltickr/impactprism/issues) tracker; the scanner itself is offline and never sends source code anywhere.
- **Contributing** — issues and pull requests welcome; run the full test suite before opening a PR.
- **Feedback** — found a dependency your SBOM tool can't see? [Open an issue](https://github.com/bulltickr/impactprism/issues) or join the discussion. ImpactPrism is free and MIT — stars, issues and PRs are the funnel.
