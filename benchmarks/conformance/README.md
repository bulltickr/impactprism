# Local conformance fixtures

This directory contains a small, deterministic regression suite built from
fixtures committed in this repository. CI runs it to catch changes to finding
classification and exit-relevant behavior.

It is not the frozen 20-repository G2 benchmark. Its results are not external
accuracy evidence and must not be described as such.

Run it from the repository root:

```bash
python benchmarks/conformance/run.py --json
```

