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
| Release tag | `v0.4.8` |
| Scanner version | `0.4.8` |
| Scanner commit | `0d66d19163a2b496fc3b4bd972cce62592430e1a` |
| Remote workflow commit | `0d66d19163a2b496fc3b4bd972cce62592430e1a` |
| Remote workflow | [Run 32556871118](https://github.com/bulltickr/impactprism/actions/runs/32556871118) |
| Manifest SHA-256 | `d409c105766d18207a7affa9eda93e049f6a3538d3c8efe02f41e175084ce459` |
| Cases | 10 |
| Result | 10/10 passed |
| Network during scan | No |
| Repository code executed | No |
| Repository dependencies installed | No |
| Repeatability | Exact-tag workflow run; normalized case digests match manifest expectations |
| Durable result | [`compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.8/compatibility-result.json) attached to the v0.4.8 release |
| Result SHA-256 | `8aa41bf8e3b12bb8fe4b3777a727d94abdf217a466a0dec057900cf1314dd51d` |
| Evidence checksum | [`compatibility-result.json.sha256`](https://github.com/bulltickr/impactprism/releases/download/v0.4.8/compatibility-result.json.sha256) |
| Historical prior result | [`v0.4.7 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.7/compatibility-result.json) contains the prior ten-case result |
| Historical prior result | [`v0.4.6 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.6/compatibility-result.json) contains the prior ten-case result |
| Historical earlier result | [`v0.4.4 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.4/compatibility-result.json) contains the earlier ten-case result |
| Historical older result | [`v0.4.3 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.3/compatibility-result.json) contains the earlier ten-case result |
| Historical older result | [`v0.4.2 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.2/compatibility-result.json) contains the earlier ten-case result |
| Historical baseline result | [`v0.4.1 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.1/compatibility-result.json) contains the original seven-case baseline |

The result was produced by preparing disposable checkouts from the manifest,
then running `run.py` against those unchanged checkouts. Preparation is the
only network phase. The machine-readable output contains the manifest
SHA-256, pinned commit and source-tree IDs, counts, and normalized finding
digests. The linked Ubuntu workflow repeated the run from the exact v0.4.8 tag
and attached the machine-readable result to the published release. Its case
digests match the governed manifest expectations. The v0.4.7, v0.4.6, v0.4.4, and
v0.4.3 assets remain historical ten-case results, while the v0.4.1 asset remains the
historical seven-case baseline.

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
| `npm-chalk` | npm | `661317e6` | `ff76edd5` | PASS | 12 | `DECLARED_UNUSED_CANDIDATE=11`, `MISSING_LOCKFILE=1` |
| `python-httpx` | Python | `b5addb64` | `31ba9451` | PASS | 33 | `DIRECT_DEPENDENCY_USED_TRANSITIVELY=6`, `LOCKFILE_MANIFEST_MISMATCH=21`, `SCOPE_MISMATCH=1`, `UNDECLARED_DIRECT_USE=5` |
| `go-chi` | Go | `735ae2b8` | `ec73f018` | PASS | 0 | clean |

The short hashes above are for readability only. The complete 40-character
identities and normalized output digests remain in
[`benchmarks/compatibility/manifest.json`](../benchmarks/compatibility/manifest.json)
and the uploaded JSON result from the workflow.

## What this demonstrates

- The scanner can process these ten pinned npm, Python, and Go repository
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
- security of the ten repositories; or
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
