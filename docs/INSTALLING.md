# Installing ImpactPrism

ImpactPrism’s official CLI distributions are hosted on GitHub Releases.

## Install a tagged release

The release workflow attaches a wheel and source archive to each published
GitHub Release. Install the wheel for the exact version you want:

```bash
python -m pip install \
  https://github.com/bulltickr/impactprism/releases/download/v0.4.7/impactprism-0.4.7-py3-none-any.whl
impactprism scan .
```

Verify the downloaded artifact against `SHA256SUMS` from the same release
before installing it in a controlled build environment.

## Install the current source tree

For development or to try the latest `main` branch:

```bash
python -m pip install \
  "git+https://github.com/bulltickr/impactprism.git"
impactprism scan .
```

For a reproducible source install, replace the repository URL with a tag or
commit reference, for example:

```bash
python -m pip install \
  "git+https://github.com/bulltickr/impactprism.git@v0.4.7"
```

## Use the GitHub Action

The reusable Action is the preferred CI integration. Its analysis step runs
offline after dependencies are available and produces findings, evidence, SBOM,
and SARIF artifacts. Managed setup may access the configured Python package
index; use `install-mode: offline` when the caller supplies the runtime and
dependencies. See [action/README.md](../action/README.md).

For release integrity, checksum, provenance, and scope guidance, see
[TRUST_AND_VERIFICATION.md](TRUST_AND_VERIFICATION.md).

## Development install

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\Activate.ps1
python -m pip install -e ".[test]"
python scripts/ci.py verify
```

After installation, `impactprism doctor .` checks the local runtime and
repository inputs without network access.
