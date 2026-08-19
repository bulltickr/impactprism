# Installing ImpactPrism

ImpactPrism’s official CLI distributions are hosted on GitHub Releases.

## Install a tagged release

The release workflow attaches a wheel and source archive to each published
GitHub Release. Install the wheel for the exact version you want:

```bash
python -m pip install \
  https://github.com/bulltickr/impactprism/releases/download/v0.3.0/impactprism-0.3.0-py3-none-any.whl
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
  "git+https://github.com/bulltickr/impactprism.git@v0.3.0"
```

## Use the GitHub Action

The reusable Action is the preferred CI integration. It installs the checked
out source tree, runs offline, and produces findings, evidence, SBOM, and
SARIF artifacts. See [action/README.md](../action/README.md).

## Development install

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\Activate.ps1
python -m pip install -e ".[test]"
python scripts/ci.py verify
```

After installation, `impactprism doctor .` checks the local runtime and
repository inputs without network access.
