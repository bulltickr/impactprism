# Public OSS roadmap

This roadmap covers the repository’s public open-source engineering work. It
is deliberately focused on the local scanner, its output contracts, and
portable automation.

## In progress

- Stabilize versioned report, evidence, delta, diagnostic, SARIF, and SBOM
  contracts.
- Expand pinned correctness fixtures for real manifest, lockfile, workspace,
  and optional-dependency shapes.
- Improve incremental scanning and repository-local policy ergonomics.

## Next

- Add more reviewed fixtures for dynamic imports, generated code, and supported
  monorepo layouts.
- Improve remediation guidance for each finding family without applying edits
  implicitly.
- Add portable examples for GitHub, self-hosted runners, and other CI systems
  around the existing provider-neutral commands.
- Document compatibility expectations for Python versions and package-manager
  formats.
- Invite external users to contribute sanitized fixtures and compatibility
  reports without presenting them as accuracy scores or adoption claims.
- Reduce maintainer bus factor through an additional reviewer or maintainer
  before making stronger project-maturity claims.
- Complete the governed real-repository benchmark only when its frozen corpus,
  labels, environment, and adjudication records actually exist.

## Principles

- Keep the scanner offline and usable without an account or API key.
- Treat unsupported behavior as an explicit evidence gap or scanner diagnostic.
- Prefer additive, versioned output changes.
- Keep provider-specific integrations at the adapter boundary.
- Do not make certification, legal, vulnerability, or broad accuracy claims
  from a clean scan.
