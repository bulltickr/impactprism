# CI portability

ImpactPrism uses GitHub Actions for the repository’s public automation and
ships a GitHub Action adapter, but neither is the source of truth for building
or testing the scanner.

The provider-neutral verification contract is:

```bash
python -m pip install -e ".[test]"
python scripts/ci.py verify
python scripts/ci.py action-smoke
python scripts/ci.py validate-ci-examples
python scripts/ci.py build
python scripts/checksums.py dist
```

The same commands can run in GitLab CI, CircleCI, Azure Pipelines, Jenkins,
a local checkout, or a self-hosted runner. They do not call the GitHub API and
do not require a GitHub token.

Copyable provider examples live in [docs/ci](ci/README.md): GitLab CI, Azure
Pipelines, Jenkins, and POSIX/Windows self-hosted runners. They all invoke the
same provider-neutral commands below; the provider files only allocate a
runner, select Python, and collect optional build artifacts.

For an air-gapped build, install from an approved local wheelhouse with
`--no-index` and `--find-links`; the verification commands themselves do not
contact GitHub.

The commands are intentionally separated:

| Command | Contract |
|---|---|
| `python scripts/ci.py test` | Full pytest suite |
| `python scripts/ci.py conformance` | Local output-conformance fixtures |
| `python scripts/ci.py correctness` | Governed correctness fixtures |
| `python scripts/ci.py smoke` | Clean demo CLI smoke test |
| `python scripts/ci.py action-smoke` | Provider-neutral Action runner contract: clean, finding, scanner-error, output validation, and workspace containment |
| `python scripts/ci.py validate-ci-examples` | Static validation of the checked-in GitLab, Azure, Jenkins, and self-hosted examples |
| `python scripts/ci.py verify` | Test, conformance, correctness, CLI smoke, Action smoke, and CI-example validation |
| `python scripts/ci.py build` | Build source and wheel distributions |

The examples are templates, not hosted-provider validation. A provider's
runner image, network policy, Python installation, package mirror, and plugin
configuration remain external prerequisites. Validate the copied file with
the provider's own linter before enabling it.

The build command intentionally uses `--no-isolation`: the caller must make
the declared build requirements available before invoking it. This makes the
network boundary explicit and allows an air-gapped runner to use a local
wheelhouse instead of silently contacting a public package index.

The public real-repository compatibility corpus is not part of ordinary
verification. Its `prepare.py` command intentionally downloads pinned public
repositories; its `run.py` command is offline after preparation. See
[benchmarks/compatibility](../benchmarks/compatibility/README.md).

## GitHub Action boundary

The GitHub Action is an adapter for GitHub workflow execution, SARIF upload,
and optional artifact upload. The scanner itself remains the normal Python CLI
and can be invoked directly by any CI provider. Analysis is offline after the
runtime and dependencies are available.

The Action supports two installation modes:

- `managed`: the Action creates its Python environment and installs the local
  ImpactPrism source tree. This may require access to the configured Python
  package index during setup.
- `offline`: the caller supplies a compatible Python runtime and dependencies;
  the Action performs no Python package installation or index access.

In both modes, repository analysis is offline. “Offline” must not be read as a
promise that a managed Action bootstrap can work without package artifacts
already being available to the runner.
