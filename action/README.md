# ImpactPrism Action

A reusable composite GitHub Action that runs the ImpactPrism dependency-drift
scan on the checked-out repository and produces a CRA-grounded evidence pack:
`findings.json` (the raw scan report), `bom.json` (a CycloneDX 1.5 SBOM),
`impactprism.sarif` (SARIF 2.1.0 for code scanning), `evidence.json` /
`evidence.md` (each finding annotated with its CRA clause mapping and
rationale), and `summary.md` (the human-readable outcome summary, also
appended to the job's step summary). The scan is fully offline — it makes no
network requests, requires no hosted ImpactPrism account and no API key, and
operates only on the checked-out commit. Only the generated reports under the
output directory are ever uploaded; source file contents are never embedded
in the reports or uploaded.

## Usage

The calling workflow must set the required permissions (see below) and
check out the repository before invoking the action. The action sets up its
own Python 3.12 environment, installs its dependencies, runs the scan, and
uploads the generated reports as an artifact (14-day retention) unless
`artifact-name` is empty.

```yaml
name: Dependency drift scan

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  pull-requests: read
  checks: write
  security-events: write

jobs:
  impactprism:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: ImpactPrism dependency-drift scan
        id: impactprism
        uses: bulltickr/impactprism@v0.2.0
        with:
          repo-path: ${{ github.workspace }}
          ecosystem: auto
          fail-on: finding
          severity-threshold: low

      # Consume the sarif-path output: publish SARIF to GitHub code scanning.
      # if: always() keeps the upload running even when the gate fails.
      - name: Upload SARIF to code scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
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
| `pull-requests: read` | read | Read the pull request ref and metadata so the scan runs against the PR's checked-out commit |
| `checks: write`     | write | Create and update check runs that report the scan outcome in the GitHub UI |
| `security-events: write` | write | Upload SARIF results to GitHub code scanning (required by the consuming `upload-sarif` step) |

## Inputs

| Name                 | Description                                                                | Required | Default                 |
|----------------------|----------------------------------------------------------------------------|----------|-------------------------|
| `repo-path`          | Path to the repository to scan.                                            | false    | `${{ github.workspace }}` |
| `ecosystem`          | Ecosystem to scan. Valid values: auto\|npm\|go.                            | false    | `auto`                  |
| `fail-on`            | Exit policy. Valid values: never\|finding\|all.                            | false    | `finding`               |
| `severity-threshold` | Minimum finding severity that trips the policy. Valid values: info\|low\|medium\|high\|critical. | false | `low`         |
| `output-dir`         | Directory for generated reports, relative to the workspace.                | false    | `impactprism-reports`   |
| `artifact-name`      | Upload artifact name; an empty string disables the upload.                 | false    | `impactprism-reports`   |

Notes on the defaults, as implemented:

- `repo-path` resolves to the workspace when unset.
- `ecosystem: auto` detects `package.json` (npm) or `go.mod` (go); if neither
  is present the outcome is `unsupported-ecosystem`.
- `output-dir` is resolved relative to the workspace; a value that escapes the
  workspace (or contains a NUL byte) falls back to `impactprism-reports`.
- `artifact-name: ''` disables the artifact upload step entirely.

## Outputs

| Name            | Description                                                        |
|-----------------|--------------------------------------------------------------------|
| `outcome`       | Classification outcome (clean\|finding\|policy-failure\|unsupported-ecosystem\|scanner-error). |
| `findings-path` | Absolute path to findings.json.                                    |
| `bom-path`      | Absolute path to bom.json (empty when not produced).               |
| `sarif-path`    | Absolute path to impactprism.sarif.                                |
| `evidence-path` | Absolute path to evidence.json.                                    |
| `exit-code`     | Exit code produced by the scan step.                               |

`bom-path` is empty when no ecosystem could be resolved or the scanner
errored, since the SBOM is only built after a successful analysis.

`exit-code` follows the `fail-on` policy: `clean` and `finding` always exit 0;
`policy-failure` exits 1 unless `fail-on: never`; `unsupported-ecosystem`
exits 1 only under `fail-on: all`; `scanner-error` exits 1 unless
`fail-on: never`. With `fail-on: never` the step always exits 0.

## Versioning

The workflow examples in this README install the action as
`bulltickr/impactprism@v0.2.0`. Action releases use git tags matching
`vX.Y.Z`, so pin to a full release tag (e.g. `@v0.2.0`) or a major tag
(e.g. `@v0`) in consuming workflows. Note that `pyproject.toml` currently
declares the Python package version as `0.1.0`; the action's release tags are
independent git tags and may lead the package version.
