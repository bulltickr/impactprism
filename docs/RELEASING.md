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
   python benchmarks/correctness/run.py --json
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
a `v*` tag is pushed. After the tag is made into an explicitly published
GitHub Release, the release-artifacts workflow builds a wheel and source
archive, writes `SHA256SUMS`, and uploads all three to that GitHub Release.
The project does not publish to a package registry.

## Installing a release

Install the attached wheel directly from GitHub. Confirm its checksum against
the `SHA256SUMS` file from the same release before using it in a controlled
build. See [INSTALLING.md](INSTALLING.md) for tagged, source, and development
install commands.

## Evidence boundaries

The local conformance fixtures are regression tests, not an external accuracy
benchmark. The G2 benchmark remains blocked until its separately governed
manifest, frozen inputs, labels, and adjudication bundle exist. A release must
not describe either fixture results or an incomplete G2 preflight as evidence
of broad detection accuracy.
