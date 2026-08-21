# Public compatibility corpus

This is a small, pinned integration corpus for ten real repository shapes. It is
not an accuracy benchmark, vulnerability study, ranking, or claim about the
quality of any repository or finding family.

The corpus intentionally records observed compatibility contracts, including
repositories that produce findings because they omit a lockfile, use a
development-heavy layout, or exercise parser boundaries. A case passes when
ImpactPrism can reproduce the reviewed normalized output for the exact pinned
tree without a scanner error.

The repository tree is not copied into ImpactPrism. Prepare disposable local
checkouts from the pinned manifest, then run the offline scanner harness:

```bash
python benchmarks/compatibility/prepare.py \
  benchmarks/compatibility/manifest.json /tmp/impactprism-compatibility
python benchmarks/compatibility/run.py \
  benchmarks/compatibility/manifest.json /tmp/impactprism-compatibility --json
```

The JSON result is the evidence artifact for a run. It includes the scanner
version, the SHA-256 of the manifest, each pinned commit and source-tree ID,
the expected and observed finding-family counts, and the normalized output
digest. The manually triggered GitHub Actions workflow uploads this result as
`impactprism-compatibility-result` for 90 days. Release baselines should also
be attached to the corresponding GitHub Release so they remain discoverable
after workflow-artifact retention expires.

`prepare.py` is the explicit network boundary and only performs Git checkout
of the pinned public commits. `run.py` never fetches, installs repository
dependencies, executes repository code, or contacts a registry. It verifies
the detached commit, clean worktree, platform-stable Git tree ID, required
inputs, finding-family counts, and a normalized output digest. The tree ID is
used instead of hashing a tar stream so the same pinned source is verifiable
with different Git versions and operating systems.

The manifest records license identifiers and pinned license-file URLs for
selection traceability. It does not redistribute repository source or license
files. Changes to the corpus require a reviewed manifest and golden-digest
update. The current selection covers three npm, five Python, and three Go
shapes across single-package, lockfile-mismatch, development-heavy, and
lockfile-absent layouts; results must not be presented as precision, recall, or
broad accuracy.

On Windows, prepare and run the corpus under the same user context. Git may
reject a checkout created by another Windows identity as a dubious repository;
that is an environment ownership issue, not a scanner result. Do not weaken
Git's safety checks globally just to bypass it.
