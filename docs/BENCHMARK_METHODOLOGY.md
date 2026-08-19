# ImpactPrism G2 Benchmark Methodology

> **PUBLIC — INCOMPLETE — VERSION-CONTROLLED EVALUATION SPECIFICATION**
>
> This document describes a planned evaluation protocol. It is not a
> performance claim, certification, audit opinion, marketing material, or
> evidence that the evaluation has passed.

## Status at this checkout

**INCOMPLETE. G2 has not been run and must not be represented as passed.**

No 20-repository benchmark manifest, frozen ground-truth labels, adjudication
record, or G2 result artifact is present in this checkout. The repository has
implementation fixtures, demos, samples, and tests, but those are not a
real-repository benchmark and cannot be used as G2 evidence.

This specification defines the required manifest and run procedure without
inventing repositories, commit SHAs, labels, results, or pass claims.

## Purpose and scope

The planned evaluation requires a frozen, adjudicated benchmark of 20 real repositories
with at least 6 JavaScript, 7 Python, 5 Go, 5 monorepo, and 4
dynamic/generated-code repositories. It also requires two independent labelers,
precision and recall reported separately by finding type, undeclared-use recall
of at least 90%, precision of at least 95%, false positives below 5%, zero
critical false negatives, and file/line/commit provenance.

This gate validates dependency-integrity findings, principally
UNDECLARED_DIRECT_USE. It does not validate CRA, AI Act, NIS2, vulnerability
prevention, or legal compliance. The product's public/evidence language remains
limited to supporting evidence, with PASS, FAIL, EVIDENCE_GAP, NOT_ASSESSED,
and REVIEW_REQUIRED used as appropriate.

### Reconciled source material

- The public README, Action documentation, scanner source, and tests establish
  the finding vocabulary, current CLI behavior, default exclusions, and known
  dynamic-import/workspace limitations.
- Local demos and fixtures are not substituted for the required real-repository
  manifest.

## 1. Required 20-repository manifest

The canonical, version-controlled input is:

~~~text
benchmarks/g2/manifest.yaml
~~~

The manifest is complete only when all of these conditions hold:

1. It contains exactly 20 entries, with unique IDs and unique URL plus full
   commit-SHA pairs.
2. Every entry has a canonical clone URL, an immutable 40-character lowercase
   Git commit SHA, and license evidence. A branch, floating URL, or short SHA
   is not sufficient.
3. The primary-ecosystem counts are at least 6 javascript, 7 python, and 5 go.
   Counts are by primary ecosystem, so one repository cannot satisfy two of
   these language quotas. Optional secondary ecosystems are recorded but do
   not inflate quota counts.
4. At least 5 entries have is_monorepo: true and at least 4 have
   has_dynamic_or_generated_code: true. These quotas may overlap with each
   other and with language quotas.
5. Every quota claim has checkable evidence in the entry. It may not be
   inferred from a repository name.
6. Each pinned commit is cloneable by the authorized runner, resolves to the
   recorded SHA, and remains unchanged for the run. Failed clone, missing
   commit, unavailable submodule, or license ambiguity makes the manifest
   incomplete; it is not silently substituted.
7. The manifest records the exact scanner commit, benchmark specification
   version, label schema version, and frozen dependency/environment lock
   references used by the run.

Required YAML schema:

~~~yaml
schema_version: "1.0"
benchmark_id: "g2-YYYY-MM-DD-rN"
status: "incomplete" # complete only after validation
created_at_utc: "YYYY-MM-DDThh:mm:ssZ"
owner: "name-or-team"
scanner:
  repository: "https://..."
  commit_sha: "40 lowercase hex characters"
  requirements_lock: "benchmarks/g2/requirements-lock.txt"
  environment_ref: "benchmarks/g2/environment.json"
repositories:
  - id: "r01"
    url: "https://host/org/repository"
    default_branch: "main"
    commit_sha: "40 lowercase hex characters"
    license_spdx: ["MIT"]
    license_evidence_url: "https://host/org/repository/blob/<sha>/LICENSE"
    license_verified_at_utc: "YYYY-MM-DDThh:mm:ssZ"
    primary_ecosystem: "javascript" # javascript | python | go
    secondary_ecosystems: []
    scan_subpath: "."
    manifest_paths: ["package.json"]
    lockfile_paths: ["package-lock.json"]
    selection_rationale: "pre-registered eligibility and quota rationale"
    is_monorepo: false
    monorepo_evidence:
      markers: [] # workspaces, go.work, multiple package roots, etc.
      paths: []
    has_dynamic_or_generated_code: false
    dynamic_generated_evidence:
      categories: [] # dynamic-import, reflection, eval, template, generated
      paths: []
      lines: []
    source_snapshot_sha256: "64 lowercase hex characters"
    ground_truth_ref: "benchmarks/g2/ground-truth/r01.json"
    notes: ""
~~~

license_spdx must contain the SPDX identifier(s) applicable at the pinned
commit. NOASSERTION is not license evidence; a repository with no determinable
license is ineligible until an explicit exclusion and replacement are approved.
source_snapshot_sha256 is a hash of the exact source archive used by the
runner, not a fabricated value.

Quota classification rules:

- javascript means the scan unit has JavaScript/TypeScript source and an
  npm-compatible manifest/lockfile supported by the pinned scanner.
- python means the scan unit has Python source and a supported Python
  dependency manifest/lockfile.
- go means the scan unit has Go source and go.mod or applicable workspace
  metadata.
- monorepo requires two or more independently managed package/module roots in
  one repository, evidenced by workspace configuration, multiple manifests,
  go.work, or equivalent checked-in structure. src plus tests is not enough.
- dynamic/generated code requires checked-in evidence of a runtime/dynamic
  import, reflection/evaluation path, template/code generation path, or
  generated source artifact in the selected scan unit. Non-literal dynamic
  imports must be labeled explicitly because the quality review identifies
  them as an existing limitation.

A validator must print the 20-row total and each quota count. Any missing field,
unverifiable evidence, or failed quota check makes the manifest unusable.

## 2. Ground truth and labeling

The companion, version-controlled label files are:

~~~text
benchmarks/g2/ground-truth/<repository-id>.json
~~~

Each file identifies the repository ID, pinned commit SHA, label-schema version,
and one row per adjudicated candidate. Required row shape:

~~~json
{
  "label_id": "r01-l0001",
  "repository_id": "r01",
  "commit_sha": "40 lowercase hex characters",
  "finding_type": "UNDECLARED_DIRECT_USE",
  "package": "canonical-package-name-or-null",
  "status": "present",
  "ecosystem": "javascript",
  "source_file": "relative/path/to/file.js",
  "line": 42,
  "column": 7,
  "manifest": "relative/path/package.json",
  "lockfile": "relative/path/package-lock.json",
  "rationale": "evidence-based explanation",
  "evidence_sha256": "hash of the cited evidence record"
}
~~~

status is one of present, absent, unsupported, or not_assessable. The finding
vocabulary is the scanner vocabulary: UNDECLARED_DIRECT_USE,
DECLARED_UNUSED_CANDIDATE, DIRECT_DEPENDENCY_USED_TRANSITIVELY, SCOPE_MISMATCH,
LOCKFILE_MANIFEST_MISMATCH, MISSING_LOCKFILE, and UNRESOLVED_IMPORT, plus
SCANNER_ERROR and UNSUPPORTED as non-scored outcomes. A present label requires
file, line, and commit provenance. Paths are repository-relative.

The comparison unit is a finding instance keyed canonically by:

~~~text
(repository_id, finding_type, normalized_package, source_file, line,
 manifest, lockfile, scope)
~~~

Package-name normalization must follow the scanner's ecosystem rules. One
prediction can match at most one gold label. Duplicate predictions for the
same gold instance count as one true positive plus each additional duplicate as
a false positive.

Labelers consider manifests, lockfiles, source, workspace configuration, and
checked-in generated artifacts at the pinned commit. They must not infer a
finding from a README or package reputation. A non-resolvable dynamic import is
not automatically positive; it is unsupported or not_assessable with reasons.

## 3. Deterministic environment and scan command

The benchmark runner uses a clean, network-disabled environment with:

- Ubuntu 24.04 LTS x86_64, or an exact equivalent container digest recorded in
  environment.json;
- Python 3.12.8, UTF-8 locale, UTC timezone, and PYTHONHASHSEED=0;
- the scanner checked out at scanner.commit_sha;
- dependencies installed only from hash-pinned requirements-lock.txt; and
- no registry, GitHub API, hosted ImpactPrism account, or credentials during
  analysis. Network is permitted only for the pre-run clone, then disabled.

For each repository, verify the detached checkout first:

~~~sh
git clone --no-tags --filter=blob:none "$URL" "$REPO_DIR"
git -C "$REPO_DIR" checkout --detach "$COMMIT_SHA"
test "$(git -C "$REPO_DIR" rev-parse HEAD)" = "$COMMIT_SHA"
~~~

With the pinned scanner installed, the canonical scan is:

~~~sh
set -eu
export LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=UTC PYTHONHASHSEED=0
mkdir -p "$OUT"
set +e
python -m impactprism scan "$REPO_DIR" \
  --report "$OUT/report.json" \
  --sbom "$OUT/bom.json" \
  --evidence "$OUT/evidence.json" \
  --json > "$OUT/stdout.json"
RC=$?
set -e
printf '%s\n' "$RC" > "$OUT/exit_code.txt"
test "$RC" -eq 0 -o "$RC" -eq 1
python -m impactprism evidence "$OUT/report.json" \
  --markdown "$OUT/evidence.md" \
  --json "$OUT/evidence.json"
~~~

Exit code 0 means no scored finding was emitted and 1 means findings were
emitted; neither exit code is a G2 metric. Exit code 2, a scanner error, a
different checkout SHA, a changed dependency lock, or a network request is a
failed run for that repository and must be retained, not retried until it
looks favorable. Record the exact command, sorted default/extra excludes,
environment fingerprint, scanner commit, and hashes of every output.

Metrics use normalized JSON finding rows sorted by repository ID, finding type,
package, file, line, and finding ID. Timestamps and absolute paths are excluded
from comparison but retained in raw artifacts.

The current CLI does not expose a commit-SHA flag. The run harness must verify
the detached checkout first, associate that verified manifest SHA with every
normalized prediction, and reject any prediction that lacks the association.
This is provenance from the checked-out commit, not an invented scanner result;
the raw CLI output remains retained unchanged.

## 4. Unsupported findings and evidence gaps

UNSUPPORTED, SCANNER_ERROR, and not_assessable are not evidence of absence and
never count as true positives, true negatives, or false positives. Retain each
with the affected file or feature, reason, and commit.

When unsupported behavior prevents evaluating a gold candidate, exclude that
candidate from the metric denominator and mark it NOT_ASSESSED; never convert
it into a negative label. A core G2 candidate affected by unsupported behavior
blocks complete G2 sign-off until the scanner supports it or the manifest is
changed in a separately versioned, pre-registered revision. Unsupported code
outside all gold candidates may be reported separately, but remains in the
coverage report.

In particular, dynamic non-literal imports, runtime-only resolution, and npm
workspace behavior must not be silently scored as clean. The quality review
lists these as limitations. Such a result is an evidence gap, not a product
or regulatory pass.

## 5. Blinding, adjudication, and tie-breaks

Two independent labelers, A and B, label every repository from the pinned
checkout. They may see the manifest entry and rubric, but not scanner version,
scanner outputs, metric code, or the other labeler's work. Their label files
are sealed with timestamps and hashes before unblinding.

Agreement is exact on the canonical finding key and status. Disagreements go
to one senior adjudicator who sees source and both rationales, but not the
scanner prediction. The adjudicator's written decision is final; this is not
a majority vote. If the adjudicator cannot establish a determinate answer, the
row is not_assessable with a reason and follows the evidence-gap rule. A
labeler or adjudicator must not sign off on a run they altered.

The metrics owner unblinds predictions only after labels and adjudications are
frozen. Any post-unblinding label change creates a new label-set hash and
requires recalculation and renewed sign-off.

## 6. Metrics and pass rule

After excluding only unsupported and not_assessable rows, calculate per finding
type:

~~~text
TP = predicted finding matched to one present gold instance
FN = present gold instance with no matched prediction
FP = predicted finding with no present gold match, including extra duplicates

recall = TP / (TP + FN) * 100
false-positive share (FP%) = FP / (TP + FP) * 100
precision = TP / (TP + FP) * 100
~~~

A zero denominator is N/A, never zero and never a pass. Report micro (pooled)
and per-repository/per-finding-type counts. Because all possible non-findings
are not enumerable, FP% here is explicitly the false-positive share of emitted
finding instances; it is the metric paired with the planned evaluation's precision
target. If a fully enumerated negative-opportunity set exists, also report
conventional FPR = FP / (FP + TN) * 100 and define that candidate universe.

The G2 numerical pass rule is exactly:

~~~text
UNDECLARED_DIRECT_USE recall >= 90.00%
and
UNDECLARED_DIRECT_USE false-positive share < 5.00%
~~~

The thresholds are evaluated on pooled eligible gold rows across all 20
repositories, not a hand-picked subset. Report precision and recall separately
for every other finding type. The planned evaluation's precision-at-least-95% target
and zero-critical-false-negative expectation are release-readiness checks and
must be shown; they must not be hidden by the pooled result.

A G2 result is PASS only when the two numeric conditions, complete manifest,
complete labels/adjudication, zero unresolved core evidence gaps, reproducible
artifacts, and all sign-offs are present. Otherwise it is FAIL or INCOMPLETE.
An absent result is not a pass. No performance claim may be made from this
incomplete evaluation.

## 7. Artifact retention and privacy

The immutable run bundle contains at minimum:

- manifest and content hash;
- scanner commit, dependency lock, environment fingerprint, clone/checkout
  verification, exact command, exit code, run timestamp;
- raw report.json, bom.json, evidence.json, evidence.md, stdout/stderr,
  normalized predictions, and output hashes for each repository;
- both blinded label sets, adjudication decisions, label-set hashes, and metric
  calculation inputs/outputs; and
- signed review and sign-off record.

Keep generated bundles for 24 months after they are superseded in an encrypted,
access-controlled store when they contain private repository data. Keep the methodology, manifest, ground-truth
labels, result index, and sign-off metadata in version control indefinitely
unless an approved retention decision requires removal. Do not commit source
snapshots, credentials, tokens, or customer code. Scrub secrets from raw logs.
Do not commit private repository source, credentials, tokens, or customer data.

## 8. Reruns and change control

Every result is identified by:

~~~text
(methodology_version, manifest_hash, ground_truth_hash,
 scanner_commit_sha, requirements_lock_hash, environment_hash)
~~~

Scanner code/configuration, dependency/environment, parser/exclusion, rubric,
any manifest row or commit/license, repository replacement, or any post-
unblinding gold-label correction requires a new revision and a full rerun of
all 20 repositories. A partial rerun cannot be spliced into a prior result.

An infrastructure retry may reuse a revision only when checkout, inputs,
environment, and command hashes are identical and the failed attempt is
retained. If a URL or SHA becomes unavailable, mark the revision INCOMPLETE;
do not replace the repository in place. A new manifest revision must revalidate
all quotas and rerun the full gate. Methodology-only wording changes that do
not alter labels, scoring, or execution are recorded as documentation changes
and do not retroactively change results.

## 9. Required sign-off

Before recording G2: PASS, the version-controlled result index must include
dated approvals from:

1. the benchmark owner, attesting that the 20-row manifest, quotas, licenses,
   pinned SHAs, environment, and artifacts are complete;
2. the maintainer, attesting that the exact command ran against the
   recorded scanner commit and that recall/FP calculations match frozen inputs;
3. an independent reviewer/adjudicator, attesting that blinding, disagreement
   handling, unsupported-result treatment, and critical false-negative review
   were followed.

Each approval records role, date, benchmark revision, manifest hash, result
hash, and any exception. Until all three approvals exist, the only permitted
status is INCOMPLETE, FAIL, or NOT_RUN. No result in this document authorizes
a performance claim, compliance claim, or regulatory conclusion.
