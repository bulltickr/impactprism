# Remediation guidance contract

ImpactPrism findings now carry a small, review-first `remediation_guidance`
object in the canonical scan report. The same object is included in evidence
output, Action `findings.json`, and SARIF result properties so a consumer does
not need to reconstruct advice from a finding type.

Each object contains:

```json
{
  "summary": "One sentence describing the safest likely next action.",
  "steps": [
    "Confirm the observed evidence.",
    "Make the smallest reviewed change.",
    "Regenerate or validate the lockfile and rerun the scan."
  ],
  "caution": "The main boundary or false-positive risk to review."
}
```

## Design rules

- Guidance is deterministic and keyed by the stable finding family.
- Guidance starts with confirming the observed manifest, lockfile, source
  location, and package identity.
- Guidance does not claim that a clean rerun proves runtime completeness,
  security, legal compliance, or certification.
- Guidance never authorizes an implicit edit, package installation, network
  call, merge, deployment, or automatic lockfile update.
- The existing `impactprism remediate` command remains a separate plan/apply
  workflow. Its default is proposed-only; its supported apply behavior and
  rollback controls are not changed by this field.

## Finding-family boundaries

| Finding family | Typical next action | Important review boundary |
|---|---|---|
| `UNDECLARED_DIRECT_USE` | Declare the direct import in the correct manifest scope. | Do not guess a version or rely on a transitive install. |
| `DIRECT_DEPENDENCY_USED_TRANSITIVELY` | Declare the direct import explicitly. | Lockfile presence is not dependency ownership. |
| `DECLARED_UNUSED_CANDIDATE` | Confirm and remove, move, or document the dependency. | Generated and runtime-only use may be outside the scan. |
| `LOCKFILE_MANIFEST_MISMATCH` | Reconcile manifest and lockfile with package-manager tooling. | Do not hide parser or resolution failures by hand-editing. |
| `MISSING_LOCKFILE` | Generate and commit the supported lockfile, or document the gap. | Intentional omission remains a reproducibility boundary. |
| `SCOPE_MISMATCH` | Align dependency scope with runtime, build, or test use. | Scope changes can alter production packaging. |
| `UNRESOLVED_IMPORT` | Verify the import target, exports, or supported alias. | Non-literal runtime resolution is not inferred. |
| `SCANNER_ERROR` | Fix the diagnostic before interpreting the result. | An error is never a clean scan. |

Consumers should display the guidance as review context, not as an automated
remediation decision. New guidance text is an additive output change and must
be covered by the scan/evidence schema tests and a changelog entry.
