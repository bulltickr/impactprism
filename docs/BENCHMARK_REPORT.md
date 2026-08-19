# ImpactPrism G2 Benchmark Report

> **PUBLIC — INCOMPLETE — NOT A PERFORMANCE, COMPLIANCE, OR CUSTOMER CLAIM**

## Status

**INCOMPLETE / NOT_RUN**

The frozen 20-repository G2 benchmark could not be executed from this checkout.
The methodology itself records that the benchmark is incomplete and that no
manifest, frozen ground truth, adjudication record, or G2 result artifact is
present. This report records that blocker rather than substituting local
fixtures, demos, samples, or invented repositories.

Run date: 2026-08-16  
Methodology: `docs/BENCHMARK_METHODOLOGY.md`  
Benchmark revision: **unavailable**  
Network/browser use: **none**

## Preflight findings

The required inputs and runner were not available:

| Required item | Expected location or requirement | Observed result |
|---|---|---|
| Frozen 20-repository manifest | `benchmarks/g2/manifest.yaml` | Missing; the benchmark directory and preflight validator exist, but no frozen repository input set is present |
| Pinned repository identities | 20 canonical URLs, lowercase 40-character commit SHAs, license evidence | Missing because the manifest is missing |
| Ground truth | `benchmarks/g2/ground-truth/<repository-id>.json` | Missing; no label files are present |
| Two independent labeler sets | Blinded labeler A and B files | Missing |
| Adjudication | Frozen disagreement decisions and sign-off | Missing |
| Frozen dependency lock | `benchmarks/g2/requirements-lock.txt` | Missing |
| Recorded benchmark environment | `benchmarks/g2/environment.json` | Missing |
| Canonical G2 runner/harness | Runner capable of clone, detached-SHA verification, scan, normalization, and scoring | Partial; `benchmarks/g2/validate.py` validates the required package but does not provide the missing repository input set |
| Result bundle | Raw outputs, hashes, normalized predictions, metric inputs/outputs | Missing |

The project-supported environment was checked and is usable:

```text
the project-supported Python executable
Python 3.11.x
impactprism 0.3.0 (editable install from this checkout)
```

That environment is not sufficient to claim methodology compliance: the frozen
specification requires Python 3.12.8 or an exact equivalent recorded in
`environment.json`, plus hash-pinned dependencies. No such environment record
or lock file is available.

## Per-repository outcomes

No repository-level outcome rows can be produced. The manifest contains zero
entries, so there are no authorized repository IDs, URLs, commit SHAs, clone
checkouts, scanner exit codes, or per-repository output hashes to report.

| Measure | Result |
|---|---:|
| Required repositories | 20 |
| Manifest entries available | 0 |
| Repositories cloned and detached-checked | 0 |
| Repository scans executed | 0 |
| Repository scan failures | 0 runs attempted; preflight blocked execution |
| Eligible repositories scored | 0 |

The local implementation fixtures, demos, samples, and tests were not treated
as repository outcomes because the frozen methodology explicitly says they are
not a real-repository benchmark and cannot be used as G2 evidence.

## Metrics

No predictions or adjudicated gold rows exist. Per the methodology, metrics
with a zero denominator are `N/A`, never zero and never a pass.

| Metric | Result | Reason |
|---|---:|---|
| `UNDECLARED_DIRECT_USE` TP / FN / FP | N/A | No manifest, labels, or predictions |
| `UNDECLARED_DIRECT_USE` recall | N/A | No eligible present gold rows |
| `UNDECLARED_DIRECT_USE` false-positive share | N/A | No emitted finding instances |
| `UNDECLARED_DIRECT_USE` precision | N/A | No emitted finding instances |
| Conventional false-positive rate | N/A | No enumerated negative-opportunity set and no predictions |
| Other finding-type precision/recall | N/A | No predictions or scored labels |
| Critical false negatives | Not assessable | No gold set exists |
| G2 numerical gate | Not evaluated | Required inputs and run artifacts are absent |

This report therefore makes no recall, false-positive, precision, pass, or
compliance claim.

## Failures and evidence gaps

- **Blocking preflight failure:** the required frozen manifest is absent.
- **Blocking input failure:** all repository pins, license evidence, and source
  snapshot hashes are absent.
- **Blocking labeling failure:** frozen ground truth, independent labels, and
  adjudication are absent.
- **Blocking reproducibility failure:** the required lock, environment record,
  scanner commit reference, canonical runner, and result bundle are absent.
- **No scan failure was induced:** no repository was cloned or scanned, so there
  are no scanner exit codes or repository-specific failures to characterize.

## Limitations

This is an execution-blocker report, not a benchmark result. It cannot assess
scanner recall, false-positive behavior, precision, critical false negatives,
dynamic or generated code coverage, npm workspace behavior, or any other
finding-type performance. Those questions require the complete frozen input
set, two-labeler/adjudication process, and reproducible artifact bundle defined
by the methodology.

The existing CLI is not itself a substitute for the G2 runner: the methodology
requires detached commit verification, commit association with normalized
predictions, network-disabled analysis, exact exclusion recording, output
hashes, and frozen scoring inputs. None of those G2 artifacts are available in
this checkout.

## Required unblock before a rerun

Provide and version-control a complete G2 revision containing the 20-entry
manifest, all pinned repositories and license evidence, frozen ground-truth and
labeler/adjudication records, scanner commit, hash-pinned lock, recorded
environment, canonical runner, and sign-offs. Then run all 20 repositories as a
single revision and retain the complete raw and normalized artifact bundle.

Until that occurs, the only permitted status is `INCOMPLETE`, `FAIL`, or
`NOT_RUN`; this report records `INCOMPLETE / NOT_RUN`.
