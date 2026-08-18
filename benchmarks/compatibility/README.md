# Public compatibility corpus

This is a small, pinned integration corpus for real repository shapes. It is
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

`prepare.py` is the explicit network boundary and only performs Git checkout
of the pinned public commits. `run.py` never fetches, installs repository
dependencies, executes repository code, or contacts a registry. It verifies
the detached commit, clean worktree, deterministic archive hash, required
inputs, finding-family counts, and a normalized output digest.

The manifest records license identifiers and pinned license-file URLs for
selection traceability. It does not redistribute repository source or license
files. Changes to the corpus require a reviewed manifest and golden-digest
update; results must not be presented as precision, recall, or broad accuracy.
