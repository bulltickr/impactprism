# Contributing to ImpactPrism

Thank you for helping improve ImpactPrism. The project is intentionally
narrow: it analyzes dependency integrity from manifests, lockfiles, and source
imports, then produces review-oriented artifacts.

## Before opening a pull request

1. Read the relevant architecture and limitation notes in `docs/`.
2. Add or update a focused fixture for behavior changes.
3. Add a regression test covering the public surface affected by the change.
4. Run:

   ```text
   python -m pytest -q
   python -m build
   python -m impactprism scan demo/clean-app
   ```

5. Explain parser limitations, ecosystem assumptions, and output-schema changes
   in the pull request description.

## Design expectations

- Prefer canonical scanner and reporting services over parallel logic.
- Keep output deterministic and provenance-preserving.
- Never turn a parser failure into a clean result.
- Treat static findings as review signals, not legal conclusions.
- Keep remediation plan-only by default and test rollback behavior.
- Do not add telemetry, network calls, or hosted-service requirements to the OSS
  scanner without a separate design discussion.

## Pull requests

Small, focused pull requests are easier to review. Include the problem, the
behavioral contract, verification performed, and compatibility impact.

Changes to JSON, SARIF, SBOM, evidence, or Action outputs require explicit
fixture coverage and a note in `CHANGELOG.md`.

Dependency changes must follow [docs/DEPENDENCY_POLICY.md](docs/DEPENDENCY_POLICY.md)
and include license, transitive-risk, and output-contract review.

For a tagged release, follow [docs/RELEASING.md](docs/RELEASING.md). The
release workflow verifies metadata, tests the tag, builds distributions, and
attaches them to the explicitly published GitHub Release. It does not publish
to a package registry.

## Support and triage

Read [SUPPORT.md](SUPPORT.md) for issue routing and the information that makes
scanner reports reproducible. Maintainers use the protocol in
[docs/MAINTAINER_TRIAGE.md](docs/MAINTAINER_TRIAGE.md).

## Reporting security issues

Please follow [SECURITY.md](SECURITY.md) rather than opening a public issue for
a potentially exploitable vulnerability.
