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
