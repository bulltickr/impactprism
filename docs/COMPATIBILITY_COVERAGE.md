# Ten-case compatibility coverage

This document records the ten-case compatibility selection and its published
release verification. It is a supplementary view of the published
[v0.4.7 compatibility report](COMPATIBILITY_REPORT.md). The v0.4.1
machine-readable release asset remains the original seven-case baseline and
does not claim to contain these later additions.

## Published release verification

| Field | Value |
|---|---|
| Scanner version in published result | `0.4.7` |
| Corpus | `impactprism-public-compatibility-2026-08` |
| Manifest SHA-256 | `d409c105766d18207a7affa9eda93e049f6a3538d3c8efe02f41e175084ce459` |
| Cases | 10 |
| Result | 10/10 passed |
| Exact-tag workflow run | PASS |
| Network during scan | No |
| Repository code executed | No |
| Repository dependencies installed | No |
| Durable release result | [`v0.4.7 compatibility-result.json`](https://github.com/bulltickr/impactprism/releases/download/v0.4.7/compatibility-result.json) |
| Evidence checksum | [`compatibility-result.json.sha256`](https://github.com/bulltickr/impactprism/releases/download/v0.4.7/compatibility-result.json.sha256) |

The release run was performed after disposable snapshots were prepared from
the exact manifest commits. The scan phase did not fetch repositories, install
their dependencies, execute their code, or contact a package registry. The
expected finding-family counts and normalized digests are stored in the
manifest.

## Selection additions

| Case | Ecosystem | Shape represented | Result | Findings |
|---|---|---|---|---:|
| `npm-chalk` | npm | Single package, manifest without lockfile | PASS | 12 |
| `python-httpx` | Python | `pyproject.toml` plus requirements-based development layout | PASS | 33 |
| `go-chi` | Go | `go.mod` without `go.sum` | PASS | 0 |

These cases were selected because they add repository shapes rather than merely
another popular project in an already-covered shape. `npm-yargs` was evaluated
but not promoted: its pinned tree produced a large unresolved/build-path-heavy
output that needs a separate boundary contract. `nestjs/nest` was not promoted
because its monorepo scan exceeded a reasonable candidate runtime. Those are
selection decisions, not claims that either project is unsupported in general.

## Full case set

The existing baseline remains:

- `npm-express`
- `npm-p-map`
- `python-requests`
- `python-flask`
- `python-click`
- `go-cobra`
- `go-logrus`

The three additions above bring the public manifest to ten cases: three npm,
four Python, and three Go cases. This remains a regression contract for pinned
repository shapes, not a precision, recall, or broad accuracy benchmark.

The v0.4.7 release-artifacts workflow ran this exact ten-case corpus from the
release tag and uploaded the resulting machine-readable JSON with the release
assets. The durable result is linked above. The v0.4.6, v0.4.4, and v0.4.3
assets remain available as historical ten-case release baselines.
