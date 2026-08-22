# ImpactPrism Action

A reusable composite GitHub Action that runs the ImpactPrism dependency-drift
scan on the checked-out repository and produces a review-oriented evidence pack
with contextual CRA references:
`findings.json` (the canonical scan report plus Action metadata; each finding includes review-first `remediation_guidance`), `bom.json` (a CycloneDX 1.6 SBOM),
`impactprism.sarif` (SARIF 2.1.0 for code scanning), `evidence.json` /
`evidence.md` (each finding annotated with its contextual clause mapping and
rationale), and `summary.md` (the human-readable outcome summary, also
appended to the job's step summary). The analysis step is offline once its
dependencies are available: it makes no source-analysis network requests,
requires no hosted ImpactPrism account or API key, and operates only on the
checked-out commit. The default managed bootstrap may access the configured
Python package index to install dependencies; use `install-mode: offline` when
the caller supplies the runtime and dependencies. Only generated reports under
the output directory are ever uploaded; source file contents are never
embedded in the reports or uploaded.

## Usage

The calling workflow must set the required permissions (see below) and
check out the repository before invoking the action. By default, the action
sets up its own Python 3.12 environment, installs its dependencies, runs the
scan, and uploads the generated reports as an artifact (14-day retention)
unless `artifact-name` is empty. Managed setup may require access to the
configured package index; offline mode skips installation and requires the
caller to provide compatible dependencies.

```yaml
name: Dependency drift scan

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  security-events: write

jobs:
  impactprism:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: ImpactPrism dependency-drift scan
        id: impactprism
        uses: bulltickr/impactprism@v0.4.6
        with:
          repo-path: ${{ github.workspace }}
          ecosystem: auto
          fail-on: finding
          severity-threshold: low

      # Consume the sarif-path output: publish SARIF to GitHub code scanning.
      # if: always() keeps the upload running even when the gate fails.
      - name: Upload SARIF to code scanning
        if: always()
        uses: github/codeql-action/upload-sarif@ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd # v4
        with:
          sarif_file: ${{ steps.impactprism.outputs.sarif-path }}

      # Consume the outcome output: react to a policy failure explicitly.
      - name: Report policy failure
        if: steps.impactprism.outputs.outcome == 'policy-failure'
        run: |
          echo "ImpactPrism policy failure — see findings.json and evidence.json in the artifact"
          exit 1
```

## Required permissions

Composite actions cannot declare `permissions` themselves, so the calling
workflow must grant them (at workflow or job level). The action needs the
following, all set before the step that invokes it:

| Permission          | Level | Why it is needed                                              |
|---------------------|-------|----------------------------------------------------------------|
| `contents: read`    | read  | Read the checked-out repository source so the scan can resolve manifests, lockfiles, and imports |
| `security-events: write` | write | Upload SARIF results to GitHub code scanning (required by the consuming `upload-sarif` step) |

## Inputs

| Name                 | Description                                                                | Required | Default                 |
|----------------------|----------------------------------------------------------------------------|----------|-------------------------|
| `repo-path`          | Path to the repository to scan.                                            | false    | `${{ github.workspace }}` |
| `ecosystem`          | Ecosystem to scan. Valid values: auto\|npm\|python\|go.                  | false    | `auto`                  |
| `fail-on`            | Exit policy. Valid values: never\|finding\|all.                            | false    | `finding`               |
| `severity-threshold` | Minimum finding severity that trips the policy. Valid values: info\|low\|medium\|high\|critical. | false | `low`         |
| `output-dir`         | Directory for generated reports, relative to the workspace.                | false    | `impactprism-reports`   |
| `artifact-name`      | Upload artifact name; an empty string disables the upload.                 | false    | `impactprism-reports`   |
| `install-mode`       | `managed` installs the local package; `offline` uses caller-provided Python dependencies and performs no package installation. | false | `managed` |
| `python-command`     | Python executable used by `offline` mode.                                  | false    | `python`               |
| `exclude`            | Newline-separated directory names or repository-relative directory prefixes added to the built-in exclusions. | false    | empty                  |
| `roots`              | Newline-separated repository-relative npm/pnpm package roots; each must contain `package.json` and globs are not accepted. | false | empty |
| `config-path`        | Optional TOML configuration path; otherwise `.impactprism.toml` is used.   | false    | empty                  |
| `baseline-path`      | Previous canonical report, resolved relative to the scanned repository.     | false    | empty                  |
| `delta-path`         | Baseline delta output path, resolved relative to the scanned repository.    | false    | empty                  |

Notes on the defaults, as implemented:

- `repo-path` resolves to the workspace when unset.
- `ecosystem: auto` detects `package.json` (npm), `go.mod` (Go), or a supported
  Python manifest; if none is present the outcome is `unsupported-ecosystem`.
- `output-dir` is resolved relative to the workspace; a value that escapes the
  workspace (or contains a NUL byte) falls back to `impactprism-reports`.
- `artifact-name: ''` disables the artifact upload step entirely.
- `install-mode: managed` creates a Python 3.12 environment and installs the
  local package; setup may require access to the configured Python package
  index.
- `install-mode: offline` skips Python setup and package installation. The
  caller must provide a compatible Python executable and dependencies; the
  Action verifies them with `PIP_NO_INDEX=1` before scanning.
- In either mode, repository analysis itself does not contact a registry or
  upload source contents.
- `roots` is an opt-in npm/pnpm package selection. The repository remains the
  workspace and lockfile resolution context, while only the selected package
  manifests and source trees are classified. Omit it for the historical
  whole-repository scan.
- Configuration and explicit Action inputs follow this precedence: input value,
  then `.impactprism.toml`, then the built-in default. The Action's generated
  `findings.json` contains the canonical scan-report fields plus Action outcome
  metadata for existing consumers.

## Outputs

| Name            | Description                                                        |
|-----------------|--------------------------------------------------------------------|
| `outcome`       | Classification outcome (clean\|finding\|policy-failure\|unsupported-ecosystem\|scanner-error). |
| `findings-path` | Absolute path to findings.json.                                    |
| `bom-path`      | Absolute path to bom.json (empty when not produced).               |
| `sarif-path`    | Absolute path to impactprism.sarif.                                |
| `evidence-path` | Absolute path to evidence.json.                                    |
| `exit-code`     | Exit code produced by the scan step.                               |
| `output-dir`    | Absolute path to the resolved generated-report directory.          |

`bom-path` is empty when no ecosystem could be resolved or the scanner
errored, since the SBOM is only built after a successful analysis.

`exit-code` follows the `fail-on` policy: `clean` and `finding` always exit 0;
`policy-failure` exits 1 unless `fail-on: never`; `unsupported-ecosystem`
exits 1 only under `fail-on: all`; `scanner-error` always exits 2 because a
scanner failure is not a finding and must not be mistaken for a clean result.

## Versioning

The workflow examples in this README install the current published action as
`bulltickr/impactprism@v0.4.6`. Action releases use git tags matching
`vX.Y.Z`, so pin to a full release tag or a major tag (e.g. `@v0`) in
consuming workflows. The existing `v0.2.0` tag is historical and remains
unchanged. The package and generated artifacts read their runtime version from
`src/impactprism/version.py`; the current synchronized release is `v0.4.6`,
and its release tag matches that value.

## Trust and verification

ImpactPrism is early-stage OSS with local regression coverage but no independent
security audit or broad external accuracy claim. Treat the Action as a focused
analysis and review aid, not as a sole security control or a CRA certification.

For a tagged release, verify the downloaded files against `SHA256SUMS`. When
available, verify the wheel’s GitHub artifact attestation as described in
[Trust and verification](../docs/TRUST_AND_VERIFICATION.md). Review the finding
scope and limitations for the ecosystem and repository shape being scanned.
