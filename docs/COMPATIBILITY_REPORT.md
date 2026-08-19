# Public compatibility corpus report

This report records one reproducible run of the public compatibility corpus.
It is compatibility evidence for pinned repository shapes, not an accuracy
benchmark, vulnerability study, ranking, or claim about the quality of any
repository or finding family.

## Run identity

| Field | Value |
|---|---|
| Corpus | `impactprism-public-compatibility-2026-08` |
| Corpus status | Pinned |
| Scanner version | `0.4.0` |
| Scanner commit | `8d75e85154cb05dd8d4d9de58ad505bcdd177271` |
| Manifest SHA-256 | `16d584d9435aea87ad0d29ab9c86fffd4d55e254c0de922368a9bf57708d077c` |
| Cases | 7 |
| Result | 7/7 passed |
| Network during scan | No |
| Repository code executed | No |
| Repository dependencies installed | No |
| Repeatability | Two same-context runs; byte-identical JSON |

The result was produced by preparing disposable checkouts from the manifest,
then running `run.py` twice against those unchanged checkouts. Preparation is
the only network phase. The machine-readable output contains the manifest
SHA-256, pinned commit and source-tree IDs, counts, and normalized finding
digests.

## Case results

| Case | Ecosystem | Pinned commit | Source tree | Result | Findings | Finding-family counts |
|---|---|---|---|---|---:|---|
| `npm-express` | npm | `a3714473` | `134de344` | PASS | 15 | `DECLARED_UNUSED_CANDIDATE=13`, `MISSING_LOCKFILE=1`, `UNDECLARED_DIRECT_USE=1` |
| `npm-p-map` | npm | `bc26cf03` | `10297443` | PASS | 9 | `DECLARED_UNUSED_CANDIDATE=1`, `MISSING_LOCKFILE=1`, `SCOPE_MISMATCH=7` |
| `python-requests` | Python | `8f8b212d` | `19e4272a` | PASS | 18 | `DECLARED_UNUSED_CANDIDATE=8`, `MISSING_LOCKFILE=1`, `UNDECLARED_DIRECT_USE=9` |
| `python-flask` | Python | `d318b683` | `a8da09a5` | PASS | 87 | `DECLARED_UNUSED_CANDIDATE=17`, `DIRECT_DEPENDENCY_USED_TRANSITIVELY=2`, `LOCKFILE_MANIFEST_MISMATCH=55`, `SCOPE_MISMATCH=2`, `UNDECLARED_DIRECT_USE=11` |
| `python-click` | Python | `61b69e96` | `9a54368b` | PASS | 77 | `DECLARED_UNUSED_CANDIDATE=16`, `DIRECT_DEPENDENCY_USED_TRANSITIVELY=2`, `LOCKFILE_MANIFEST_MISMATCH=57`, `SCOPE_MISMATCH=1`, `UNDECLARED_DIRECT_USE=1` |
| `go-cobra` | Go | `adbc8813` | `5a3b2c8e` | PASS | 0 | clean |
| `go-logrus` | Go | `134c80f8` | `a81865d2` | PASS | 0 | clean |

The short hashes above are for readability only. The complete 40-character
identities and normalized output digests remain in
[`benchmarks/compatibility/manifest.json`](../benchmarks/compatibility/manifest.json)
and the uploaded JSON result from the workflow.

## What this demonstrates

- The scanner can process these seven pinned npm, Python, and Go repository
  shapes without emitting `SCANNER_ERROR`.
- The normalized outputs are stable across two same-context runs.
- The harness can distinguish expected clean cases from expected finding cases.
- The checkout identity and required input files are verified before analysis.
- The scan phase is separable from network-bound repository preparation.

## What this does not demonstrate

- precision, recall, false-positive rate, or false-negative rate;
- complete discovery of runtime, generated, dynamically loaded, or unsupported
  dependencies;
- legal compliance, CRA certification, or an audit opinion;
- security of the seven repositories; or
- broad external adoption or community validation.

The governed G2 benchmark remains incomplete until its frozen corpus, labels,
adjudication, environment, and result bundle exist. See
[`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md).

## Reproduce

```bash
python benchmarks/compatibility/prepare.py \
  benchmarks/compatibility/manifest.json /tmp/impactprism-compatibility
python benchmarks/compatibility/run.py \
  benchmarks/compatibility/manifest.json /tmp/impactprism-compatibility --json
```

Preparation downloads only the exact public commits named by the manifest.
The second command does not fetch, install, execute, or contact a registry for
the prepared repositories.
