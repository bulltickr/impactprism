# Dependency policy

ImpactPrism keeps its runtime dependency surface deliberately small. The
project is an offline scanner, so dependencies must not introduce telemetry,
an account requirement, or a runtime network call.

## Adding a dependency

Before adding a runtime or build dependency, a change should explain:

1. why the existing standard library or project code is insufficient;
2. the supported Python versions and platforms;
3. the package license and compatibility with MIT distribution;
4. the transitive dependency impact; and
5. how the dependency behaves when the scanner reads untrusted repository
   input.

Keep the dependency declaration in `pyproject.toml`. Do not vendor generated
package trees into the repository. Prefer a bounded compatible version range
when an upstream major release could change the scanner’s output contract.

## Review and verification

Dependency changes require:

- `python -m pip check`;
- the full test suite and conformance fixtures;
- a wheel build and installed-wheel smoke test;
- review of the generated SBOM and package metadata; and
- a changelog note when behavior, supported versions, or artifacts change.

Dependabot proposes updates for Python and GitHub Actions. Maintainers still
review changelogs, licenses, permissions, and output-contract risk before
merging an update. A dependency update is not evidence that the scanner is a
vulnerability scanner or that a repository is compliant.

## Action dependencies

GitHub workflows use full-length commit-SHA Action references with the
intended major release retained in a comment, and disable persisted checkout
credentials. Dependabot monitors those references. A
workflow that needs write permission must keep it at the narrowest job scope
and explain why the write is required; the release-artifacts workflow is the
only workflow that currently needs `contents: write`.
