# Trust and verification

ImpactPrism is early-stage open-source software. This page explains what is
verified, what is not yet independently established, and how to check a
published release without treating the project’s own claims as proof.

## Current maturity boundary

The project has:

- deterministic local tests, conformance fixtures, and correctness fixtures;
- cross-platform GitHub Action smoke coverage;
- a Python compatibility matrix and CodeQL workflow;
- a pinned public compatibility corpus with ten reviewed repository shapes; the
  v0.4.2 release asset contains the ten-case result and the v0.4.1 asset remains
  the historical seven-case baseline;
- release checks for metadata, wheel/sdist contents, installed-wheel behavior,
  checksums, artifact attestation, dependency review, and Scorecard analysis;
  and
- explicit threat-model, security, benchmark, and output-contract documents.

The project does not currently claim:

- an independent security audit;
- broad external accuracy, recall, or false-positive performance;
- significant external adoption, customer validation, or community maturity;
- complete discovery of runtime, generated, dynamically loaded, or unsupported
  dependencies; or
- legal compliance, CRA certification, or an audit opinion.

The public compatibility corpus is a regression contract for ten pinned
repository shapes, not an accuracy score. Its ten-case machine-readable result
is attached to the [v0.4.2 release](https://github.com/bulltickr/impactprism/releases/tag/v0.4.2),
produced from that exact tag. The v0.4.1 result remains attached as the
historical seven-case baseline.
The governed real-repository G2 benchmark is intentionally incomplete. Its
blocker report is public in [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md); local
demos and fixtures are not presented as external accuracy evidence.

## Verify a GitHub Release

Download the wheel, source archive, and `SHA256SUMS` from the same release. The
expected v0.4.2 files are available at the
[v0.4.2 release page](https://github.com/bulltickr/impactprism/releases/tag/v0.4.2).

Verify the downloaded files before installation:

```bash
sha256sum -c SHA256SUMS
```

On Windows PowerShell, compare each file’s `Get-FileHash -Algorithm SHA256`
value with the corresponding line in `SHA256SUMS`.

When the GitHub CLI and attestations are available, verify the wheel’s build
provenance:

```bash
gh attestation verify impactprism-0.4.2-py3-none-any.whl \
  -R bulltickr/impactprism
```

Checksums establish that the downloaded files match the release manifest.
Attestation verification adds provenance evidence for the GitHub-built
artifact. Neither check validates scanner correctness or replaces review of
the project’s scope and limitations.

## Offline boundary

“Offline” refers to scan execution after the required package and dependencies
are available locally.

- A normal CLI scan reads the selected repository and writes local outputs; it
  does not contact a registry, GitHub API, hosted ImpactPrism service, or
  vulnerability database.
- GitHub Action `install-mode: offline` performs no Python package installation;
  the caller must provide a compatible runtime and dependencies.
- GitHub Action `install-mode: managed` installs the local package and may need
  access to the configured Python package index during setup.
- Installing a release or preparing the optional external compatibility corpus
  is a separate network boundary from scanning.

## Evidence boundary

ImpactPrism reports are review-oriented static-analysis evidence. They record
observed inputs, findings, rationale, statuses, and contextual reference
mappings. They do not establish that a product is legally subject to a clause,
that every dependency was found, or that a repository is secure or compliant.
See [THREAT_MODEL.md](THREAT_MODEL.md), [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md),
and [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md).

## Building external confidence

The honest path to stronger confidence is reproducible external review:

1. users submit small, sanitized fixtures for real manifest, lockfile, import,
   workspace, generated-code, and dynamic-import shapes;
2. maintainers reproduce each report and add a focused fixture when appropriate;
3. compatibility reports identify exact input commits and output hashes without
   being presented as accuracy scores; and
4. an independently governed benchmark is only published once its corpus,
   labels, environment, adjudication, and result bundle are complete.

The repository currently has one listed CODEOWNER. Additional reviewers or
maintainers should be added only when they have explicitly agreed to that role;
the project does not claim a second maintainer before that happens.
