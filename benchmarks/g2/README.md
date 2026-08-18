# G2 benchmark preflight

This directory contains internal, offline tooling for the frozen G2 benchmark
specified in [the methodology](../../docs/BENCHMARK_METHODOLOGY.md). The
validator checks the manifest shape, the 20-repository and quota requirements,
one structurally valid ground-truth file per repository, and the declared
adjudication/output metadata. It never clones repositories, opens URLs, runs
the scanner, computes scores, or claims that G2 passed.

Run it from the repository root:

```bash
python benchmarks/g2/validate.py
```

Use `--json` for a score-free machine-readable result. Exit code `0` means
`READY`; exit code `1` means `INCOMPLETE` and includes actionable diagnostics.
`READY` only means the frozen inputs are shaped for a future benchmark run.

When a separately governed frozen manifest and local repository corpus exist,
verify the checkout boundary before any benchmark runner is allowed to scan:

```bash
python benchmarks/g2/verify_snapshots.py \
  benchmarks/g2/manifest.yaml /path/to/pinned-snapshots --json
```

The snapshot directory must contain one clean Git checkout per repository ID.
Verification checks the detached `HEAD`, worktree cleanliness, the SHA-256 of
`git archive HEAD`, the selected scan subpath, and declared manifest/lockfile
paths. It performs no network access, scanning, or scoring; `VERIFIED` is not
a G2 pass. The repository does not include a real G2 corpus or benchmark
result bundle.
