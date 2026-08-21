# Changelog

## Unreleased

## 0.4.4 - 2026-08-22

### Remediation guidance

- Added deterministic, review-first `remediation_guidance` to canonical
  findings, evidence output, Action findings, and SARIF properties.
- Documented the guidance contract and its non-automatic safety boundary.

### Reproduction intake

- Added a read-only metadata contract and validator for small, explicitly
  declared sanitized reproduction bundles.
- Added a public example, CI coverage, and maintainer review guidance without
  presenting reproductions as accuracy or adoption evidence.

### Resolution coverage

- Added governed fixtures for Vite alias arrays, nested webpack aliases in an
  npm workspace, and a clean two-module Go workspace.
- Kept the coverage limited to literal, repository-contained targets; dynamic
  bundler configuration remains an explicit boundary.

### Adoption

- Added a provider-neutral demo matrix covering the npm finding example and
  clean npm, Python, and Go examples.
- Added first-run and sanitized-fixture contribution guides for external users
  and contributors.

## 0.4.3 - 2026-08-21

### Release integrity

- Added an offline checksum sidecar for the durable compatibility result so
  evidence assets can be verified independently from the distribution files.
- Documented the release-evidence verification path alongside wheel and source
  archive checksums.

## 0.4.2 - 2026-08-21

### Compatibility evidence

- Expanded the pinned public compatibility corpus from seven to ten reviewed
  real-repository shapes across npm, Python, and Go.
- Made the release-artifacts workflow run the pinned compatibility corpus from
  the exact release tag and attach its machine-readable result to the GitHub
  Release.

### Documentation

- Published the expanded compatibility selection and its evidence boundaries.
- Corrected the public corpus coverage counts to match the ten-case manifest.

## 0.4.1 - 2026-08-20

### Resolution coverage

- Added bounded, non-executing support for workspace package `exports`,
  package-local `imports`, and static TypeScript `paths`/`baseUrl` aliases.
- Added explicit unresolved findings when a configured local target is missing
  or a workspace package subpath is not exported.
- Added bounded pnpm workspace discovery and non-executing literal Vite/webpack
  alias coverage, with repository-root containment checks.

## 0.4.0 - 2026-08-19

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
- Aligned the public composite Action, CodeQL workflow, and integration examples
  with pinned Node24-era Action majors.
- Made the pull-request CRA gate use an explicit, trusted scan scope so
  intentional demo and fixture findings do not block workflow-only changes;
  evidence comments now remain available when findings fail the gate.

### Reliability

- Unified CLI and GitHub Action repository scanning through one provider-neutral
  scan service.
- Added canonical report fields, configuration, exclusions, and baseline/delta
  support to the GitHub Action while preserving its existing outcome envelope.
- Made explicit ecosystem selection reach SBOM generation for mixed-manifest
  repositories.
- Removed stale Action-owned artifacts before reruns and made uploaded paths use
  the runner-resolved output directory.
- Added CLI severity-threshold policy handling and release-artifact validation.
- Added direct CLI/Action parity tests covering schemas, evidence digests,
  configuration, baselines, repeated runs, and clean artifact behavior.

### Release boundary

- Release distributions are checked for exact wheel/sdist contents, package
  data, version metadata, and installed-wheel smoke behavior before checksums
  and upload.

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
  at `0.4.0`; the existing historical `v0.2.0` tag is unchanged.
