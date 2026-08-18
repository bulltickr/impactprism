# Changelog

## Unreleased

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

### Compatibility notes

- `scan` now treats all canonical findings, including missing lockfiles and
  unresolved imports, as findings for exit-code purposes.
- Legacy category-only report JSON remains readable by the evidence command.
- The package and Action version will be synchronized at the next release tag.
