# ImpactPrism

ImpactPrism is an early-stage, open-source dependency-integrity analysis and release-evidence preflight tool for selected npm, Python, and Go supply-chain controls. It compares supported manifests, lockfiles, and source imports, then produces a CycloneDX SBOM and review-oriented evidence outputs. Scan execution is offline after installation; dependency installation and the managed GitHub Action bootstrap may require access to configured package artifacts.

[![CI](https://github.com/bulltickr/impactprism/actions/workflows/ci.yml/badge.svg)](https://github.com/bulltickr/impactprism/actions/workflows/ci.yml)

## Quickstart

Install a tagged GitHub Release wheel, then scan the repository:

```bash
python -m pip install \
  https://github.com/bulltickr/impactprism/releases/download/v0.4.3/impactprism-0.4.3-py3-none-any.whl
impactprism scan .
open evidence.md            # rendered Markdown preflight report
```

For source installation and development setup, see
[docs/INSTALLING.md](docs/INSTALLING.md). The GitHub Action requires no local
CLI installation.

For a first-time walkthrough, see [Getting started](docs/GETTING_STARTED.md).

If the command fails before scanning, run the offline diagnostic first:

```text
impactprism doctor .
impactprism doctor . --json
```

`doctor` checks the Python runtime, required local dependencies, supported
repository inputs, and lockfile availability. It never contacts a registry or
uploads repository contents.

For repeatable local settings, add an optional
[`.impactprism.toml`](docs/CONFIGURATION.md) to the repository. It can define
additional exclusions, baseline/delta paths, output paths, and the local
`fail_on` policy; command-line flags always take precedence.

`scan` produces, in the current directory:

| File            | Contents |
|-----------------|----------|
| `evidence.md`   | Human-readable release-evidence preflight: findings, statuses, observed inputs, and rationale |
| `evidence.json` | Machine-readable release-evidence preflight (same findings, JSON) |
| `bom.json`      | CycloneDX SBOM — pass `--sbom bom.json` to write it |
| `report.json`   | Raw scan report — pass `--report report.json` to write it |

For pull-request workflows, compare against a previously accepted report:

```bash
impactprism scan . --baseline baseline.json --delta delta.json --report report.json
impactprism diff report.json baseline.json --json
```

With `--baseline`, exit code `1` means a new finding was introduced; existing
findings do not fail the incremental gate, and resolved findings are listed in
the delta. Scanner errors still return exit code `2`. See
[docs/OUTPUT_CONTRACT.md](docs/OUTPUT_CONTRACT.md) for the versioned report,
evidence, delta, and CLI-error contracts.

GitHub Releases provide the official CLI wheel, source archive, and
`SHA256SUMS`. The project’s distribution source is GitHub. Verify release
integrity and provenance before installing; see
[Trust and verification](docs/TRUST_AND_VERIFICATION.md). Scan execution
remains offline after installation.

## Project status and trust boundaries

ImpactPrism is early-stage software maintained by a small public project. It
has meaningful local regression coverage and a validated release process, but
it has no independent security audit, no claim of broad external accuracy, and
no claim of significant external adoption. Treat it as a focused engineering
tool to evaluate and review, not as a sole security control.

The project is intentionally narrow. A clean result covers only the supported
inputs and rules. The evidence output provides review context, not a legal
conclusion, CRA certification, audit opinion, or proof that every runtime or
generated dependency was discovered.

## What this checks / What it does not

ImpactPrism compares supported manifests, lockfiles, and source imports. Its code emits these finding types:

- `UNDECLARED_DIRECT_USE` — source imports a dependency that is not declared.
- `DECLARED_UNUSED_CANDIDATE` — a declared dependency is not observed in scanned source.
- `DIRECT_DEPENDENCY_USED_TRANSITIVELY` — source uses a dependency available only transitively.
- `LOCKFILE_MANIFEST_MISMATCH` — the manifest and lockfile disagree.
- `MISSING_LOCKFILE` — a dependency manifest has no recognized lockfile.
- `SCOPE_MISMATCH` — a dependency is used outside its declared scope.
- `UNRESOLVED_IMPORT` — a scanned import cannot be resolved.
- `SCANNER_ERROR` — a manifest could not be parsed, so the scan cannot be trusted.

It is not a vulnerability scanner: it does not identify known CVEs or certify that dependencies are safe. A clean result is limited to the supported checks and inputs; ImpactPrism makes no certification claim and is not an audit or compliance determination.

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

Ready-made fixture apps with planted findings live in [demo/README.md](demo/README.md): `demo/npm-app` demonstrates drift and an undeclared dependency, while the npm, Python, and Go clean demos demonstrate successful scans. The provider-neutral verification also runs the complete demo matrix.

- [impactprism-scan-terminal.png](docs/screenshots/impactprism-scan-terminal.png) — `impactprism scan` terminal output with findings
- [evidence-pack-markdown.png](docs/screenshots/evidence-pack-markdown.png) — rendered Markdown evidence pack
- [github-action-pr-comment.png](docs/screenshots/github-action-pr-comment.png) — the GitHub Action posting an evidence summary as a PR comment
- [sample-sbom-snippet.png](docs/screenshots/sample-sbom-snippet.png) — a sample CycloneDX SBOM snippet

## GitHub Action

Add ImpactPrism to your pull requests in four lines:

```yaml
- name: ImpactPrism scan
  uses: bulltickr/impactprism@v0.4.3
  with:
    repo-path: ${{ github.workspace }}
    fail-on: finding
```

The composite action’s analysis step is offline once its dependencies are
available: it requires no hosted account or API key, produces `findings.json`,
`bom.json`, `impactprism.sarif`, `evidence.json`/`evidence.md` and `summary.md`,
uploads a SARIF report to code scanning, and exits per the `fail-on` policy
(`never` | `finding` | `all`). Its default `managed` bootstrap may install
Python dependencies from the configured package index; use
`install-mode: offline` when the caller supplies the runtime and dependencies.
The Action and CLI support selected npm, Python, and Go checks. See
[action/README.md](action/README.md) for inputs, outputs and required workflow
permissions.

## Verify a release

Download the wheel, source archive, and `SHA256SUMS` from the same GitHub
Release. Verify the checksums before installation:

```bash
sha256sum -c SHA256SUMS
```

When the GitHub CLI and artifact attestations are available, verify the wheel’s
build provenance as well:

```bash
gh attestation verify impactprism-0.4.3-py3-none-any.whl \
  -R bulltickr/impactprism
```

For the v0.4.3 compatibility evidence, also verify its published sidecar:

```bash
sha256sum -c compatibility-result.json.sha256
```

Checksums verify that downloaded files match the release manifest. Attestation
verification adds provenance evidence for the GitHub-built artifact; neither
is a substitute for reviewing scanner scope, limitations, or findings.

## Supported ecosystems

The CLI auto-detects supported project inputs. npm uses `package.json` and supported lockfiles; Python uses supported `pyproject.toml`, `Pipfile`, or `requirements.txt` inputs and lockfiles; Go uses `go.mod`, `go.work`, `go.sum`, and vendored module metadata. The GitHub Action can force `npm`, `python`, or `go` via its `ecosystem` input.

- Python checks cover supported manifest/lockfile and import comparisons; coverage varies by packaging format and repository structure.
- Manifest sources: `go.mod` (module, `require`, `replace`), `go.work` (workspace member modules and their `replace` rules), `go.sum` (checksums), and `vendor/modules.txt` for vendored builds.
- A package-level import graph is aggregated to the module level; each module is classified by observed use (`used`/`direct`).
- Go findings: `UNDECLARED_DIRECT_USE` (imported but not declared in `go.mod`), `DECLARED_UNUSED_CANDIDATE` (direct dependency never imported), `DIRECT_DEPENDENCY_USED_TRANSITIVELY` (imported directly but only declared indirect), `LOCKFILE_MANIFEST_MISMATCH` (declared module with no `go.sum` entry) and `UNRESOLVED_IMPORT` (import resolves to no declared module).
- Standard-library and main-module imports are excluded from findings.

The public pinned real-repository compatibility corpus has a separate
[reproducible report](docs/COMPATIBILITY_REPORT.md). It is compatibility
regression evidence, not a broad accuracy claim.

Hard-case limits and reviewed coverage for workspaces, dynamic imports, and
checked-in generated source are documented in
[HARD_CASE_COVERAGE.md](docs/HARD_CASE_COVERAGE.md).

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
| `findings.json` | JSON | Canonical scan report plus GitHub Action outcome metadata |
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
| `scan` / `analyze` | Clean — no supported findings or scanner diagnostics | Any supported finding is present | Error (bad path, unsupported input, or scanner error) |
| `evidence` / `clauses` | Success | — | Error (missing/invalid input, invalid clause map) |

When `scan` or `analyze` is called with `--json`, a bad path or unsupported
input writes a machine-readable error envelope to stdout with `error.kind`
and `exit_code: 2`. A supported repository whose manifest cannot be parsed
instead produces the normal canonical report containing a `SCANNER_ERROR`
finding, with exit code 2; this keeps the failure explainable to automation.

## CLI reference

```
impactprism doctor [repo] [--json]
impactprism scan <repo> [--exclude PAT] [--sbom PATH] [--report PATH] [--evidence PATH] [--json]
impactprism scan <repo> [--baseline PATH] [--delta PATH]
impactprism analyze <repo_dir> [--exclude PAT] [--sbom PATH] [--report PATH] [--json]
impactprism evidence <scan_report> [--markdown PATH] [--json PATH] [--stdout]
impactprism diff <current_report> <baseline_report> [--json]
impactprism clauses [path]
```

| Subcommand | Arguments | Flags |
|------------|-----------|-------|
| `doctor` | `[repo]` — repository to diagnose (default: current directory) | `--json` |
| `scan` | `<repo>` — repository to scan | `--exclude PAT` (repeatable), `--sbom PATH`, `--report PATH`, `--evidence PATH`, `--json` |
| `diff` | `<current_report> <baseline_report>` | `--json` |
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

CI runs on every push and pull request on a Python 3.10 / 3.11 / 3.12 matrix:
`pip install -e .[test]`, the provider-neutral verification commands, package
build checks, and an `impactprism scan .` exit-0 self-check.

The provider-neutral verification entry point is
`python scripts/ci.py verify`; see [docs/CI_PORTABILITY.md](docs/CI_PORTABILITY.md)
for running the same contract outside GitHub Actions.

## License, security, contributing, feedback

- **License** — [MIT](LICENSE), Copyright (c) 2026 ImpactPrism contributors.
- **Security** — see [SECURITY.md](SECURITY.md); scan execution is offline after installation and never sends source code anywhere.
- **Contributing** — see [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); run the full test suite before opening a PR.
- **Threat model** — see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for assets, controls, and explicit limits.
- **Feedback** — found a dependency your SBOM tool can't see? [Open an issue](https://github.com/bulltickr/impactprism/issues) using the compatibility or false-positive template. ImpactPrism is free and MIT — issues and PRs are the feedback funnel.
