# Releasing ImpactPrism

ImpactPrism uses a deliberately small release process. A release tag is a
claim about the exact source tree, so the tag check, tests, conformance
fixtures, and built artifacts are all part of the release boundary.

## Before tagging

1. Update `CHANGELOG.md` and move the intended entries out of `Unreleased`.
2. Update `src/impactprism/version.py` to the release version. For the current
   release preparation, the next synchronized package/Action release is
   `v0.4.7`; never move an existing tag.
3. Run the local checks from the repository root:

   ```bash
   python scripts/ci.py verify
   python scripts/check_release.py
   python scripts/ci.py build
   python scripts/verify_release_artifacts.py dist
   python scripts/checksums.py dist
   ```

4. Inspect the wheel metadata and confirm that the package version, generated
   artifact version, and intended Action tag agree.
5. Commit the release preparation and create the matching tag:

   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```

The repository's release-check workflow repeats the important checks whenever
a `v*` tag is pushed, including exact artifact-set validation, an installed
wheel smoke test, and strict checksums. After those checks pass, manually run
the `Publish GitHub Release artifacts` workflow with the existing tag as its
`release-tag` input. The workflow builds a wheel and source archive, writes
`SHA256SUMS`, creates or reuses a draft GitHub Release, uploads all assets, and
only then publishes the release. The project does not publish to a package
registry.

The release-artifacts workflow also creates a GitHub artifact attestation for
the built release files. When GitHub is available, verify a downloaded wheel
with:

```bash
gh attestation verify impactprism-0.4.7-py3-none-any.whl \
  -R bulltickr/impactprism
```

Checksums remain useful for offline transfer; the attestation adds build
provenance when the GitHub API is reachable.

The release-artifacts workflow also runs the pinned public compatibility corpus
from the exact release tag and uploads `compatibility-result.json` with the
other release assets. That result is a compatibility regression contract, not
an accuracy benchmark.

The compatibility result is accompanied by `compatibility-result.json.sha256`.
It is a standard single-file checksum manifest, so a downloaded result can be
checked offline with `sha256sum -c compatibility-result.json.sha256` when both
files are in the same directory. The distribution `SHA256SUMS` file continues
to cover the wheel and source archive.

The draft-first sequence is intentional. It keeps all assets attached before
publication, so the process remains compatible with GitHub immutable releases.
If the selected tag already has a published release, the workflow stops rather
than attempting to mutate it. A failed run may leave a draft release or partial
assets; inspect that draft before retrying and do not overwrite a published
asset.

Do not overwrite an existing release asset; a corrected result belongs to a new
release or a clearly versioned evidence asset with its own provenance.

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
