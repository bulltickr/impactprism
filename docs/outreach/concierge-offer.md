# ImpactPrism Concierge Paid Pilot

> **Internal sales draft — unpublished.** Do not publish, post, or send without approval.

## Offer

ImpactPrism is a founder-assisted, paid pilot for teams that need a clearer release-evidence trail for selected software-supply-chain controls.

- **Price:** EUR 750–1,500 per month
- **Term:** 4–6 weeks
- **Scope:** 3–5 customer-selected repositories
- **Delivery:** Customer-run CI plus a manually reviewed evidence pack

The pilot is scoped around a specific release or dependency-evidence question. It is not a general-purpose compliance assessment or an autonomous remediation service.

## What the pilot includes

- Kickoff to select repositories, releases, evidence questions, and success criteria.
- Customer-run checks for agreed dependency, manifest, lockfile, SBOM, and release-evidence inputs.
- Reconciliation of the agreed inputs, with provenance such as commit or artifact digests, lockfile hashes, and applicable tool or rule versions where available.
- A manually reviewed evidence pack with explicit statuses: `PASS`, `FAIL`, `EVIDENCE_GAP`, `NOT_ASSESSED`, and `REVIEW_REQUIRED`.
- Plain-language notes on observed mismatches, missing evidence, and suggested follow-up actions.
- A closeout review with the customer’s technical or security owner.

Where separately agreed, the pilot may include proposed dependency-remediation pull requests. Every proposed change remains subject to customer review, customer CI, and required human approval.

## Customer-controlled operating model

- The customer runs CI and the checks in its own environment.
- Customer source code is not uploaded to ImpactPrism infrastructure and is not retained by ImpactPrism.
- No auto-merge, unattended production change, or autonomous release decision is included.
- A customer-authorized human must review and approve every pull request or change before merge or release.
- The customer controls repository permissions, runner configuration, credentials, CI results, and final merge decisions.

## Boundaries and exclusions

This pilot does not provide legal advice, certification, an audit opinion, a security guarantee, or a determination that a customer is compliant with the CRA, AI Act, NIS2, or any other law. It provides supporting evidence for the specifically agreed controls and repositories only. It does not claim that a finding is a legal breach.

The pilot excludes broad regulatory coverage, unscoped repositories, auto-merge, source retention, and public benchmark, recall, false-positive, or performance claims. Evidence gaps and unassessed areas are reported explicitly rather than treated as passes.

## Working process

1. Agree the repositories, release or commit scope, evidence questions, access model, and pilot success criteria.
2. Configure the customer-run CI workflow and confirm the customer’s review and approval path.
3. Run the agreed checks and assemble evidence from the customer-controlled workflow.
4. Manually review the results, classify findings and evidence gaps, and prepare the pack.
5. Walk through the pack with the customer and record follow-up actions or a next-release scope.

## Pilot success criteria

The pilot is successful when the agreed repositories and release scope have been processed, the evidence pack is traceable to the available inputs, mismatches and gaps are clearly classified, and the customer can use the reviewed pack to make its own documented technical and release decisions.

## Internal close

“Would a 4–6 week, founder-assisted pilot across 3–5 repositories, priced at EUR 750–1,500 per month, help you answer a specific release-evidence question? Your team would run the checks in its own CI, and we would manually review the resulting evidence pack. You retain control of the source, CI, approvals, and merges.”
