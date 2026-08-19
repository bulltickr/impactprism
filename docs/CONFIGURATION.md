# Local configuration

ImpactPrism can load an optional `.impactprism.toml` from the repository being
scanned. Configuration is local, explicit, and offline. It is not required for
the CLI or Action.

```toml
[scan]
exclude = ["generated", "vendor-copy"]
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

- `scan.exclude` adds directory-name exclusions to the built-in defaults.
- `scan.baseline` and `scan.delta` enable incremental comparison.
- `outputs.report`, `outputs.evidence`, and `outputs.sbom` select default output
  paths.
- `policy.fail_on` is `finding` (the default) or `never`.

Paths from the configuration file are relative to the scanned repository. CLI
flags override configured values. Unknown sections and keys are errors rather
than being silently ignored. `impactprism doctor .` validates the file without
running a scan.
