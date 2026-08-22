# Local configuration

ImpactPrism can load an optional `.impactprism.toml` from the repository being
scanned. Configuration is local, explicit, and offline. It is not required for
the CLI or Action.

```toml
[scan]
exclude = ["generated", "vendor-copy"]
roots = ["apps/web", "packages/shared"]
baseline = "artifacts/baseline.json"
delta = "artifacts/delta.json"

[outputs]
report = "artifacts/report.json"
evidence = "artifacts/evidence.json"
sbom = "artifacts/bom.json"

[policy]
fail_on = "finding"
```

Supported keys are deliberately limited:

- `scan.exclude` adds directory-name or repository-relative directory-prefix
  exclusions to the built-in defaults. For npm workspaces, the same values also
  exclude nested workspace manifests before workspace-discovery limits are
  applied. For example, `cmd/fiximports/testdata` excludes only that tree,
  while `testdata` excludes every directory with that basename.
- `scan.roots` is optional. For npm/pnpm, each value is one repository-relative
  package directory containing `package.json`. For Go, each value is one
  repository-relative module directory containing `go.mod`. Roots are literal
  paths, not globs. Multiple roots are supported, and only their manifests and
  source trees are classified. The repository still provides workspace,
  replacement, vendor, lockfile, and checksum resolution context. If omitted,
  the scan retains the historical whole-repository scope. An explicit root that
  is covered by `scan.exclude` is rejected.
- `scan.baseline` and `scan.delta` enable incremental comparison.
- `outputs.report`, `outputs.evidence`, and `outputs.sbom` select default output
  paths.
- `policy.fail_on` is `finding` (the default) or `never`.

Paths from the configuration file are relative to the scanned repository. CLI
flags override configured values. Unknown sections and keys are errors rather
than being silently ignored. `impactprism doctor .` validates the file without
running a scan.

The GitHub Action also reads `.impactprism.toml` by default. Its explicit
`exclude`, `roots`, `config-path`, `baseline-path`, and `delta-path` inputs override the
corresponding repository settings. Action paths are resolved relative to the
scanned repository; the generated report directory remains controlled by the
Action's `output-dir` input.

Canonical scan reports include the normalized effective scope. This makes an
excluded tree visible to reviewers instead of making a clean result appear to
cover files that were intentionally outside the scan.
