# Governed correctness fixtures

This suite exercises supported manifest and lockfile formats using versioned,
small fixtures. It is intentionally separate from the local
conformance suite so format coverage can grow without turning either suite
into an unsupported accuracy claim.

Current matrix:

- npm workspaces with a root lockfile;
- Python requirements files;
- Python Pipenv manifests and locks;
- Python `pyproject.toml` with `uv.lock`;
- Python `pyproject.toml` optional dependency groups;
- Python Poetry findings;
- npm pnpm lockfiles;
- Go vendoring through `vendor/modules.txt`; and
- Go workspace/replacement findings.

Each case checks finding counts and normalized finding signatures, including
provenance, severity, confidence, status, and stable finding IDs. The
expected results are maintained in `expected.json` through a reviewed fixture
change; they are not generated during CI.

Run it from the repository root:

```bash
python benchmarks/correctness/run.py --json
```

These are regression and format-contract results. They are not external
accuracy evidence and must not be described as broad precision or recall.
