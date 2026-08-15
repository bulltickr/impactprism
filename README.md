# ImpactPrism

[![CI](https://github.com/bulltickr/impactprism/actions/workflows/ci.yml/badge.svg)](https://github.com/bulltickr/impactprism/actions/workflows/ci.yml)

A CLI that generates a CycloneDX SBOM from a Create React App / JS-TS repo's
package.json and lockfile, then cross-checks declared dependencies against the
imports actually used in the source, flagging drift (declared but unused) and
undeclared dependencies (used but not declared).

## Requirements

- Python 3.9+ — standard library only, no third-party runtime dependencies
- `pytest` — required only to run the test suite

## Usage

## CLI (main.py)

```text
python main.py analyze <repo_dir> [--sbom PATH] [--report PATH] [--json]
python main.py evidence <scan_report> [--markdown PATH] [--json PATH] [--stdout]
python main.py clauses [path]
```

- `analyze` analyzes a repository and optionally writes an SBOM or scan report.
- `evidence` generates Markdown and JSON evidence from a scan report.
- `clauses` loads, validates, and prints the CRA clause map.

Each command mirrors the corresponding module's standalone usage and exit codes: `analyze` returns 0 for clean, 1 for findings, or 2 for an error; `evidence` returns 0 for success or 2 for an error; and `clauses` returns 0 for success or 2 for an error.

```
python analysis.py <repo_dir> [--sbom PATH] [--report PATH] [--json]
```

| Option                    | Description                                                           |
|---------------------------|-----------------------------------------------------------------------|
| `<repo_dir>` (positional) | Path to the repo to analyze; must contain a `package.json`            |
| `--sbom <path>`           | Write the CycloneDX 1.5 SBOM JSON to this path (default: not written) |
| `--report <path>`         | Write the report JSON to this path (default: not written)             |
| `--json`                  | Print the report JSON to stdout instead of the human summary          |

With no flags, only the human-readable summary goes to stdout — nothing is
written into the repo dir.

## Exit codes

| Code | Meaning                                                        |
|------|----------------------------------------------------------------|
| 0    | Clean — no drift and no undeclared dependencies                |
| 1    | Findings — drift and/or undeclared dependencies present        |
| 2    | Invalid repo path, missing `package.json`, or analysis error   |

## Human summary

With `--json` absent, stdout shows the repository, the package, the declared
dependency count, the imported package count, the drift list, and the
undeclared list:

```
Repository: /path/to/repo
Package: my-app@1.0.0
Declared dependencies: 3
Imported packages: 2
Drift (declared but unused): 1
  react
Undeclared dependencies: 1
  lodash
```

Each finding list is capped at 50 entries; beyond that, a `... and N more` line
is appended.

## Report JSON

Written by `--report <path>`, or printed to stdout by `--json`:

| Key               | Contents                                             |
|-------------------|------------------------------------------------------|
| `repo`            | Absolute path of the analyzed repo                   |
| `package_name`    | `name` from package.json (fallback `"unknown"`)      |
| `package_version` | `version` from package.json (fallback `"0.0.0"`)     |
| `declared`        | Sorted names from `dependencies` + `devDependencies` |
| `imported`        | Sorted bare package names found in source            |
| `drift`           | Sorted names declared but never imported             |
| `undeclared`      | Sorted names imported but not declared               |

All name lists are sorted.

## SBOM

Written by `--sbom <path>` as CycloneDX 1.5 JSON:

- `bomFormat` `"CycloneDX"`, `specVersion` `"1.5"`, `version` 1
- `metadata.timestamp` — current time in UTC, `Z` suffix
- `metadata.tools` — impactprism-analysis 0.1.0
- `metadata.component` — the app itself
- `components` — one `type: "library"` entry per declared dependency
  (`dependencies` + `devDependencies`), each with a purl of
  `pkg:npm/<name>@<version>`, the name percent-encoded (`@` -> `%40`,
  `/` -> `%2F`)

Version resolution order:

1. `package-lock.json` — `packages["node_modules/<name>"]`, then
   `packages["<name>"]`, then `dependencies["<name>"]`
2. `npm-shrinkwrap.json` — same lookups
3. Declared version range from `package.json`
4. `0.0.0`

## Drift vs undeclared

- **Drift** — declared in `package.json` but never imported in source.
- **Undeclared** — imported in source but absent from `package.json`.

Example: `package.json` declares only `react` (`"react": "^18.2.0"`), and a
source file imports `lodash`:

```json
{ "dependencies": { "react": "^18.2.0" } }
```

```js
import _ from 'lodash';
```

- `react` -> drift (declared but unused)
- `lodash` -> undeclared (used but not declared)

## Scan scope

- Scans `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs` files
- Recognizes ES module imports (default, named, namespace, bare), dynamic
  `import()`, and CommonJS `require()`
- Skips `node_modules`, `build`, `dist`, `.git`, `.cache`, `coverage`, `public`,
  and dot-directories
- Ignores relative and absolute specifiers (`./x`, `../x`, `/x`), `node:`
  specifiers, and Node built-ins (`fs`, `path`, ...) — built-ins are NOT
  counted as imports
- Subpaths are reduced to the package root (`lodash/map` -> `lodash`)
- Scoped packages are kept as `@scope/pkg`

## Samples and demo

Canonical sample outputs live under `docs/samples/`, generated from the demo
sources in `demo/`:

| File | Description |
|------|-------------|
| [docs/samples/evidence-sample.md](docs/samples/evidence-sample.md) | CRA evidence pack for a repo with findings — overall status `REVIEW_REQUIRED` |
| [docs/samples/sample-bom.json](docs/samples/sample-bom.json) | CycloneDX 1.6 SBOM |
| [docs/samples/sample-sarif.json](docs/samples/sample-sarif.json) | SARIF 2.1.0 report |
| [docs/samples/clean-evidence.md](docs/samples/clean-evidence.md) | CRA evidence pack for a clean repo — overall status `PASS` |

The demo sources are reproducible fixtures:

- [demo/npm-app](demo/npm-app) — repo with findings (drift and/or undeclared dependencies)
- [demo/clean-app](demo/clean-app) — clean repo (no findings)

Regenerate the samples from the demo sources with the documented CLI:

```
python main.py analyze demo/npm-app --sbom docs/samples/sample-bom.json --report report.json
python main.py evidence report.json --markdown docs/samples/evidence-sample.md
python main.py analyze demo/clean-app --report clean-report.json
python main.py evidence clean-report.json --markdown docs/samples/clean-evidence.md
```

## Evidence pack

`evidence.py` turns a scan report JSON (as produced by
`python analysis.py <repo_dir> --report report.json`) into a clause-grounded
evidence pack, in both Markdown and JSON, annotating each finding with CRA
article IDs.

### Usage

```
python evidence.py <scan_report.json> [--markdown PATH] [--json PATH] [--stdout]
```

| Option                      | Description                                                       |
|-----------------------------|-------------------------------------------------------------------|
| `<scan_report>` (positional) | Input report JSON to convert; must exist, else exit code 2      |
| `--markdown <path>`         | Write the Markdown evidence pack to this path (default: `evidence.md`) |
| `--json <path>`             | Write the JSON evidence pack to this path (default: `evidence.json`)   |
| `--stdout`                  | Print the JSON evidence to stdout, skipping the JSON file         |

### Exit codes

| Code | Meaning                            |
|------|------------------------------------|
| 0    | Success                            |
| 2    | Missing or invalid input report    |

### CRA clause mapping

| Category     | CRA clauses                                              |
|--------------|----------------------------------------------------------|
| `undeclared` | Art 13(1)(b), Art 14(1), Annex I Part II, Annex VII      |
| `drift`      | Art 13(1)(a), Annex I Part I                             |

### Output JSON

Written by `--json <path>`, or printed to stdout by `--stdout`:

```json
{
  "generator": "impactprism-evidence",
  "version": "0.1.0",
  "timestamp": "2026-08-15T12:00:00Z",
  "source_report": "report.json",
  "package_name": "my-app",
  "package_version": "1.0.0",
  "clause_map": { "undeclared": ["Art 13(1)(b)", "Art 14(1)", "Annex I Part II", "Annex VII"], "drift": ["Art 13(1)(a)", "Annex I Part I"] },
  "findings": [
    {
      "category": "undeclared",
      "name": "lodash",
      "clauses": ["Art 13(1)(b)", "Art 14(1)", "Annex I Part II", "Annex VII"],
      "rationale": "Undeclared dependencies fall outside the SBOM/component transparency required by Art 13(1)(b) and evade the vulnerability-handling obligations of Art 14(1)/Annex VII."
    }
  ],
  "summary": { "total_findings": 1, "undeclared_count": 1, "drift_count": 0, "clean": false }
}
```

### Output Markdown

Written by `--markdown <path>`:

- H1 title: `ImpactPrism Evidence Pack`
- A metadata block (generator, version, timestamp, source report, package)
- One `## Findings` subsection per finding, each with its category, name,
  clauses, and rationale
- A `## CRA references` table listing the mapped article IDs

A clean report yields `clean: true`, `findings: []`, and a "No findings" line
in the markdown.

## CRA CI check

The workflow in `.github/workflows/cra-check.yml` runs on every pull request.
It checks out the PR branch, runs `python main.py analyze . --report report.json`
(exit 1 means drift and/or undeclared dependencies—critical findings that map
to CRA clauses), then runs
`python main.py evidence report.json --markdown evidence.md --json evidence.json`.
The generated Markdown evidence pack is posted as a PR comment using the default
`GITHUB_TOKEN` with `pull-requests: write`, and the check fails when the analyze
exit code is non-zero (1 = critical findings, 2 = error).

| Exit code | Result |
|-----------|--------|
| 0 | Green — clean |
| 1 | Red — critical findings (drift and/or undeclared dependencies) |
| 2 | Red — error |

On fork PRs, the token is read-only until a maintainer approves the workflow, so
the comment may be skipped but the gate still fails.

## Missing lockfile policy

An npm manifest that declares at least one dependency must have an effective
lockfile. `MISSING_LOCKFILE` fires once per manifest when none of
`package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, or `pnpm-lock.yaml`
exists for the manifest directory or an ancestor workspace root — one finding
per manifest, not per dependency:

| Field      | Value                |
|------------|----------------------|
| finding    | `MISSING_LOCKFILE`   |
| severity   | MEDIUM               |
| confidence | HIGH                 |
| status     | OPEN                 |
| ecosystem  | npm                  |

A lockfile that exists but cannot be parsed is NOT treated as missing: each
declared dependency then produces a `LOCKFILE_MANIFEST_MISMATCH` finding, and
`MISSING_LOCKFILE` is never also emitted for that manifest.

Without a lockfile the resolved dependency tree is unreproducible and
vulnerability tracking is impossible, undermining the obligations of CRA
Art 14(1) and Annex VII — the finding's clause mapping.

The action gate treats the finding by severity threshold:

| `severity-threshold` | Outcome          | Exit code |
|----------------------|------------------|-----------|
| `low` (default)      | `policy-failure` | 1         |
| `high`               | `finding`        | 0         |

Note: this section documents the intended policy; the implementation had not
landed in the working tree when it was written — re-verify once it does.

## Tests

```
python -m pytest tests -q
```

Run from the repo root.

CI runs on every push and pull request, executing on a Python 3.9/3.11/3.12
matrix: `pip install -e .[test]`, `pytest -q`, `python -m build`, and an
`impactprism scan .` exit-0 self-check.

## License

Released under the [MIT License](LICENSE).

Copyright (c) 2026 ImpactPrism contributors.
