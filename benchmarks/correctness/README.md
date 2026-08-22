# Governed correctness fixtures

This suite exercises supported manifest and lockfile formats using versioned,
small fixtures. It is intentionally separate from the local
conformance suite so format coverage can grow without turning either suite
into an unsupported accuracy claim.

Current matrix:

- npm workspaces with a root lockfile;
- npm workspaces with literal dynamic imports, an explicit non-literal boundary,
  and checked-in generated source;
- Python requirements files;
- Python Pipenv manifests and locks;
- Python `pyproject.toml` with `uv.lock`;
- Python `pyproject.toml` optional dependency groups;
- Python literal `importlib.import_module` usage plus checked-in generated
  source;
- Python Poetry findings;
- npm pnpm lockfiles;
- repository-local TypeScript `tsconfig` inheritance for static aliases;
- literal Vite/webpack aliases plus a function-generated bundler-alias
  non-execution boundary;
- Go vendoring through `vendor/modules.txt`; and
- Go workspace/replacement findings, including explicit module-root scope.

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

Dynamic import coverage is intentionally limited to literal module names.
Non-literal runtime resolution is not executed or inferred. Checked-in source
under a directory named `generated` is scanned by default; callers that know a
directory is generated and should be excluded must pass an explicit exclusion.
