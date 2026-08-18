# Releasing ImpactPrism

ImpactPrism uses a deliberately small release process. A release tag is a
claim about the exact source tree, so the tag check, tests, conformance
fixtures, and built artifacts are all part of the release boundary.

## Before tagging

1. Update `CHANGELOG.md` and move the intended entries out of `Unreleased`.
2. Update `src/impactprism/version.py` to the release version. Because the
   repository already has a historical `v0.2.0` tag, the next synchronized
   package/Action release should use `v0.3.0` or later; do not move an existing
   tag.
3. Run the local checks from the repository root:

   ```bash
   python -m pytest -q
   python benchmarks/conformance/run.py --json
   python scripts/check_release.py
   python -m build
   ```

4. Inspect the wheel metadata and confirm that the package version, generated
   artifact version, and intended Action tag agree.
5. Commit the release preparation and create the matching tag:

   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```

The repository's release-check workflow repeats the important checks whenever
a `v*` tag is pushed. The publish workflow runs only after an explicitly
published GitHub Release and uses PyPI Trusted Publishing. Before enabling it,
configure the PyPI project publisher for this repository, workflow, and
`pypi` environment; the workflow intentionally has no long-lived package token.

## Evidence boundaries

The local conformance fixtures are regression tests, not an external accuracy
benchmark. The G2 benchmark remains blocked until its separately governed
manifest, frozen inputs, labels, and adjudication bundle exist. A release must
not describe either fixture results or an incomplete G2 preflight as evidence
of broad detection accuracy.
