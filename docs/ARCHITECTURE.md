# Architecture

ImpactPrism has five conceptual layers:

```text
repository inputs
  -> ecosystem parsers and bounded source scanners
  -> normalized manifest/import/lockfile models
  -> drift classifier producing Finding objects
  -> canonical ScanResult/reporting adapters
  -> JSON, Markdown evidence, SARIF, CycloneDX, and Action outputs
```

## Canonical boundaries

- `manifest.py`, `python_manifest.py`, and the Go manifest modules parse inputs.
- `imports.py`, `python_imports.py`, and `go_imports.py` discover source usage.
- `drift/classifier.py` is responsible for finding classification.
- `reporting.py` normalizes findings and defines report categories and exit
  semantics.
- `evidence.py` maps normalized findings to the versioned contextual clause
  map.
- `sbom/cyclonedx_builder.py` validates CycloneDX output.
- `cli.py` and `action/run.py` orchestrate execution; they should not invent
  ecosystem-specific finding semantics.

## Finding contract

Every finding has a stable type and deterministic ID, severity, confidence,
ecosystem, package/module, provenance, explanation, and status. New finding
types must be wired into the classifier, report normalization, evidence mapping,
SARIF, tests, and documentation together.

## Trust boundaries

The scanner treats repository contents as untrusted input. Parsers must be
bounded by file, tree, depth, and time budgets. Outputs must not embed source
contents or secrets. Remediation must be explicit, plan-only by default, and
rollback-safe when apply mode is used.

## Compatibility

Legacy category-only report JSON is accepted by the reporting adapter so users
can regenerate evidence from older reports while the canonical schema evolves.
New fields must be additive until a versioned breaking change is approved.
