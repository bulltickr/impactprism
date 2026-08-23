# ImpactPrism OSS next-phase plan

Status: planning baseline for the work immediately after the v0.4.8 release
line.

This is the public engineering plan. It covers the scanner, its contracts, the
Action, portable automation, documentation, and the project’s open-source
operating model. Private commercial strategy is intentionally not described
here; local-only material belongs under `.private/`, which is excluded by the
repository’s tracked `.gitignore`.

## Decision

The next major chunk should be **release governance plus external validation**.

ImpactPrism already has a substantial technical foundation: offline scanning,
cross-ecosystem analysis for npm/Python/Go, structured findings, SBOM and SARIF
output, a provider-neutral Action, compatibility evidence, sanitized
reproduction intake, and a 515-test local verification gate. The highest-value
remaining work is therefore not another broad parser. It is proving that the
existing contract is trustworthy, repeatable, easy to adopt, and responsive to
real repository shapes.

This sequencing follows the maturity pattern used by adjacent projects: review
and reproducible releases first, a documented compatibility surface second, and
feature expansion only when external evidence identifies the need. The OpenSSF
[OSPS Baseline](https://baseline.openssf.org/) is a useful checklist for that
progression, while GitHub’s [artifact attestation
documentation](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
describes the provenance model already used by the release workflow.

## Current baseline

### Already in good shape

- Local test and governed verification gates are comprehensive and green.
- The CLI and Action are usable without an account, API key, or source upload.
- Findings have stable identifiers, provenance, severity, confidence, and
  documented output schemas.
- npm, Python, and Go manifest/lockfile handling has a reviewed correctness
  corpus, including workspace, alias, dynamic, generated-source, and optional
  dependency boundaries.
- Release artifacts are built, checked, checksummed, and attested for future
  releases.
- Security policy, support routing, contribution guidance, public compatibility
  evidence, and sanitized reproduction review are present.
- CI dependencies are hash-locked and the GitHub CI, CodeQL, and Action smoke
  checks pass on the current hardening branch.

### Evidence gaps to close

- `main` still needs repository-owner rulesets for pull requests, required
  checks, review approval, and protected `v*` tags.
- A public-documentation consistency pass is still needed: the trust and
  verification guide contains older release references, and the root
  `package.json` still advertises an obsolete `0.4.0` JavaScript package
  version even though ImpactPrism is currently released as Python `0.4.8`.
- The next release needs one end-to-end draft-first rehearsal on the current
  release workflow, including attestation verification and non-overwrite
  behavior.
- The compatibility corpus is useful regression evidence, but it is not a
  broad accuracy benchmark and needs more externally sourced shapes.
- The first-five-minutes path can be made more explicit for CI users, JSON/SARIF
  consumers, unsupported boundaries, and self-hosted runners.
- Maintainer capacity and external review are still thin; project maturity
  claims should remain conservative until independent users exercise the tool.

## Ordered work packages

### P0 — Merge and lock repository governance

Owner actions and code-side work:

1. Merge the current dependency-analysis and CI hardening branch.
2. Add a `main` ruleset requiring pull requests, at least one approval,
   dismissal of stale approvals, required green checks, and no direct branch
   deletion.
3. Add a `v*` tag ruleset preventing deletion and force-updates.
4. Add or confirm a second reviewer/Code Owner for security-sensitive and
   release-workflow changes.
5. Record the exact required-check names in the maintainer documentation.

Exit gate: a normal contribution cannot bypass review or green verification,
and release tags cannot be silently rewritten.

### P0.5 — Remove public metadata drift

Before the next release, reconcile every public version and release URL in
`README.md`, `action/README.md`, `docs/INSTALLING.md`,
`docs/RELEASING.md`, `docs/TRUST_AND_VERIFICATION.md`, compatibility reports,
the changelog, and package metadata. Decide whether the root `package.json` is
still part of the project surface; if it is not, remove it, and if it is,
define its role and keep its version synchronized. Add a consistency test so a
future release cannot silently publish mixed version claims.

Exit gate: a clean search of tracked public files finds one intentional current
release identity, with older versions appearing only in historical changelog,
compatibility, or migration context.

### P1 — Rehearse and document release integrity

1. Run the release workflow against a disposable candidate tag.
2. Verify draft creation, exact artifact set, checksums, compatibility evidence,
   attestations, and final publication.
3. Verify a rerun against an already published tag fails without overwriting
   assets.
4. Add a short public release checklist to `docs/RELEASING.md` with the
   commands and URLs a maintainer must record.
5. Publish the next release only after the checklist has been exercised.

Exit gate: another maintainer can reproduce the release decision from the tag,
workflow run, assets, checksums, and attestation without private context.

### P2 — Build the external-validation loop

1. Grow the corpus from reviewed synthetic shapes toward at least ten
   externally sourced, sanitized or explicitly licensed repository shapes.
2. Record provenance, license, ecosystem, package manager, workspace shape,
   expected boundary, and review date for every case.
3. Promote every confirmed compatibility regression into a minimal public
   fixture before changing the parser or resolver.
4. Keep false positives, false negatives, unresolved imports, and unsupported
   boundaries as separate measures.
5. Attach versioned compatibility results to releases and explain changes in
   plain language.

Do not turn a clean scan of a small corpus into an accuracy or compliance
claim. The public compatibility report must continue to state what it does and
does not demonstrate.

Exit gate: the project can show repeatable evidence across materially different
repository shapes and can explain the limits of that evidence.

### P3 — Make adoption and support self-service

1. Refine the README and getting-started path around one clean scan, one
   finding, one GitHub Action example, and one interpretation guide.
2. Add copyable provider-neutral examples for GitHub-hosted, self-hosted,
   GitLab, Azure, and Jenkins-style runners.
3. Add explicit JSON, SARIF, evidence-pack, delta, and SBOM consumption examples.
4. Improve diagnostics for unsupported monorepo roots, dynamic/generated code,
   missing lockfiles, and unresolved imports.
5. Make the compatibility matrix generated from the governed corpus, rather
   than maintaining overlapping hand-written lists.
6. Invite external maintainers to review wording and findings using the public
   sanitized reproduction contract.

Exit gate: an outside maintainer can install, scan, interpret, and report a
compatibility issue without a private briefing.

### P4 — Stabilize the public contract before expansion

1. Define the compatibility and deprecation policy for report, evidence, delta,
   diagnostic, SARIF, and SBOM schemas.
2. Add contract tests for additive changes and clear migration notes for any
   breaking change.
3. Publish an explicit support matrix for Python versions, manifest formats,
   lockfile formats, and CI entry points.
4. Review the threat model and privacy statements against the actual code and
   workflows.
5. Consider machine-readable posture metadata only after the repository
   governance and release evidence are complete; Security Insights and OSPS
   controls are useful references, not badges to claim prematurely.

Exit gate: users can safely automate against the outputs and understand the
support boundary before upgrading.

### P4.5 — Add a bounded quality and portability gate

The current suite is strong, but the repository does not yet have a dedicated
lint/type/coverage/property-testing policy. Decide deliberately, rather than
adding tools for badges alone:

- add a lightweight formatter/linter gate for changed Python code;
- choose a modest type-checking boundary or document why it is not yet useful;
- publish coverage as a trend signal, never as an accuracy claim;
- add parser/property tests for malformed manifests, hostile imports, oversized
  files, and deep directory structures covered by the threat model;
- add at least one native Windows or macOS smoke path in addition to Ubuntu
  CI, while preserving provider-neutral examples.

Exit gate: quality checks catch a distinct class of regressions, have bounded
runtime, and are documented as engineering signals rather than guarantees.

### P5 — Choose the next technical depth from evidence

Only after P0–P4 should the project choose one primary engineering bet. Rank
options by external demand, reduction in unresolved findings, correctness
evidence, and maintenance cost:

- deeper static resolution for a repeatedly observed bundler or workspace;
- richer lockfile-aware provenance and transitive impact explanations;
- baseline/delta governance for recurring scans;
- policy-as-code improvements;
- another ecosystem only when it has a clear evidence and maintainer owner.

Do not pursue all options concurrently and do not add an ecosystem merely to
make the project look broader.

## Release-readiness gates before monetization work

Monetization discussions should start after these OSS gates are true:

- the `main` and `v*` rulesets are active;
- one draft-first release has been rehearsed and independently verified;
- future artifacts have checksums and attestations;
- the external compatibility corpus has at least ten reviewed shapes;
- the first-five-minutes path and provider-neutral examples are complete;
- output schemas and support boundaries are versioned and documented;
- at least one additional maintainer or reviewer can run the release and triage
  flow;
- no known high-severity CI or release-integrity issue is unresolved.

These gates protect the OSS project from using private product pressure to hide
unfinished public reliability work.

## Explicit non-goals for this phase

- Do not add PyPI solely for legitimacy; GitHub releases remain a deliberate
  distribution choice.
- Do not add telemetry, a hosted dependency, source upload, or an account
  requirement to the scanner.
- Do not claim broad accuracy, certification, legal compliance, or vulnerability
  coverage from the current corpus.
- Do not add every ecosystem before the existing provenance and review model is
  strong.
- Do not place pricing, customer names, sales material, or private product
  strategy in this repository.

## Repository organization

Public OSS planning and evidence belong in `docs/`, with the durable project
contracts kept beside the code and tests. Local-only snapshots, research,
administrative exports, and commercial planning belong under `.private/`.
That directory is now explicitly ignored in the tracked `.gitignore`; it must
never be included in source distributions, release assets, public issues, or
pull requests.

The existing `docs/ROADMAP.md` remains the short public index. This document is
the detailed execution plan and should be updated when a work-package exit gate
changes.
