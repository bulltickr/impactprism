# Changelog

## Unreleased

### OSS operations

- Established explicit GitHub Release artifacts with SHA-256 checksums.
- Published versioned scan, evidence, delta, doctor, and CLI-error schemas with
  compatibility guidance.
- Added offline first-run diagnostics through `impactprism doctor`.
- Added opt-in baseline/delta scanning and a strict repository-local
  `.impactprism.toml` configuration file.
- Expanded governed correctness coverage with pnpm and Python optional-
  dependency fixtures.
- Sanitized public benchmark and sample artifacts so they contain no local
  workstation paths or internal-only references.
- Added installation, support, security, contributor, and maintainer-triage
  guidance for an external open-source project.
- Added CodeQL analysis and Dependabot coverage for Python and GitHub Actions.

## 0.3.0 - 2026-08-18

### Reliability

- Added a canonical normalized scan-report contract for CLI and evidence
  consumers.
- Propagated modern classifier findings through `scan` and evidence output.
- Added canonical Go SBOM generation to the analysis service and Action path.
- Made remediation plan-only by default and added rollback protection for apply
  failures.
- Added clean-runner dependency installation to the reusable Action and CRA
  workflow.
- Centralized the runtime version used by package metadata, evidence, SBOM,
  and Action artifacts.
- Added a repository-local conformance suite and tag-checked release workflow.
- Preserved Go manifest indirectness while recording imported indirect modules
  as application-root SBOM dependencies when source evidence supports it.
- Added Python support to the reusable GitHub Action and its clean-runner smoke
  matrix.
- Added deterministic npm, Python, and Go conformance fixtures with stable
  repository-relative finding signatures.
- Added installed-wheel smoke coverage for clean and finding-producing
  projects across all three supported ecosystems.

### Compatibility notes

- `scan` now treats all canonical findings, including missing lockfiles and
  unresolved imports, as findings for exit-code purposes.
- Legacy category-only report JSON remains readable by the evidence command.
- The package, CLI, SBOM, evidence, and Action artifact version is synchronized
  at `0.3.0`; the existing historical `v0.2.0` tag is unchanged.
