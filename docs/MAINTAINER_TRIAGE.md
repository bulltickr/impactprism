# Maintainer triage

This is the lightweight triage protocol for the public issue queue. It keeps
reports actionable without turning the project into a promise of support for
every package manager or runtime pattern.

## First pass

1. Remove secrets or proprietary data from the report and issue comments.
2. Confirm the report identifies a commit/version, ecosystem, command, and
   minimal reproduction.
3. Run `python scripts/validate_reproduction.py` when a reproduction bundle is
   provided, then reproduce with the smallest available fixture.
4. Classify the report as behavior, documentation, feature request, security,
   or duplicate.
5. Add an ecosystem label (`ecosystem:npm`, `ecosystem:python`, or
   `ecosystem:go`) when applicable.

Recommended labels are:

- `bug`, `false-positive`, `feature`, `documentation`, `security`;
- `ecosystem:npm`, `ecosystem:python`, `ecosystem:go`;
- `needs-reproduction`, `good-first-issue`, `breaking-change`.

Labels are triage aids, not severity or compliance determinations.

The validator checks bundle structure and basic hygiene only. It is not a
secret scanner, does not execute submitted code, and does not establish that a
reported expectation is correct. A `sanitized-external` bundle must still be
reviewed by a maintainer before it becomes public regression coverage.

## Scanner findings

For an unexpected finding, compare the report with the supported manifest,
lockfile, source-import, and scope rules before changing the classifier. A
regression should add a fixture and a focused test. A limitation should be
documented with the affected ecosystem, file shape, and confidence boundary.

Do not silently weaken a finding to make a clean fixture pass. Parser failures
must remain visible as scanner errors, and static evidence must not be
described as proof of legal compliance.

## Release and security routing

- Security reports follow [SECURITY.md](../SECURITY.md).
- Release changes follow [docs/RELEASING.md](RELEASING.md).
- Output-contract changes require fixture coverage, schema review, and a
  changelog entry.
- Benchmark claims require the governed methodology and evidence boundary in
  [docs/BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md).
