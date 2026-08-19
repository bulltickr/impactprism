# Output contract

ImpactPrism treats its machine-readable output as a public integration
surface. The contract is intentionally small, deterministic where practical,
and versioned independently from the package release number.

## Published schemas

- [Scan report schema](schemas/scan-report.schema.json) — canonical output from
  `scan` and `analyze`.
- [Evidence pack schema](schemas/evidence-pack.schema.json) — output from
  `evidence` and the evidence artifact produced by the Action.
- [Baseline delta schema](schemas/delta.schema.json) — output from incremental
  scans and the `diff` command.
- [CLI error schema](schemas/cli-error.schema.json) — JSON returned for input
  and scanner errors when `--json` is requested.
- [Doctor schema](schemas/doctor.schema.json) — output from the offline
  `doctor` command.

The Action's `findings.json` validates against the scan-report schema and adds
Action-only fields such as `outcome`, `policy`, `error`, `bom_validated`, and
`timestamp`. This is an additive envelope for existing workflow consumers;
the findings, buckets, counts, package metadata, and embedded SBOM come from
the same scan service as the CLI.

The schemas are also regression-tested against generated outputs. They are
documentation and validation artifacts; the normal runtime does not require
the `jsonschema` package.

## Compatibility policy

- The scan report currently has `schema_version: 1`.
- The evidence pack has `output_schema_version: 1`. Its existing `schema_version`
  field remains the version of the CRA clause map (`2`), for compatibility with
  existing evidence consumers.
- New fields may be added in a minor release.
- Existing fields are not removed, renamed, or given a different type within a
  schema version.
- Finding identifiers are stable for the same finding identity and are the
  preferred key for comparing reports.
- Older category-only scan reports remain readable by the evidence adapter.
- A schema-version change requires a changelog entry, updated fixtures, and a
  migration note.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | The supported checks completed and emitted no findings. |
| `1` | The supported checks completed and emitted one or more findings. |
| `2` | The repository could not be scanned or a scanner diagnostic made the result unavailable. |

Exit code `0` is not a certification claim. It means only that no finding was
emitted by the supported checks for the available inputs.

## Determinism

Reports sort findings and aggregate lists before serialization. Consumers
should compare `finding_id` values and contract fields rather than relying on
the order of object keys. Evidence packs include a timestamp and therefore are
not byte-for-byte deterministic; their source-report digest is the provenance
anchor.
