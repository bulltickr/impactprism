# Threat model

## Assets

- Source repository confidentiality
- Integrity of generated evidence and SBOM artifacts
- Correctness of CI gate decisions
- Developer workstation and CI runner safety

## Relevant threats

- Malformed manifests or lockfiles causing crashes or false clean results
- Oversized or deeply nested files causing resource exhaustion
- Path traversal through Action output paths or remediation patches
- Generated reports accidentally embedding source contents
- A parser silently ignoring unsupported syntax
- A remediation failure leaving a partially modified repository
- A misleading CRA mapping being interpreted as legal certification

## Controls

- Bounded scanners and controlled parse errors
- Path containment checks
- Deterministic finding IDs and provenance fields
- Explicit scanner-error findings
- Non-executing static resolution parsing for package and TypeScript metadata
- Validated CycloneDX output
- SARIF and evidence generated from normalized findings
- Plan-only remediation by default and rollback on apply failure
- Legal-scope disclaimers in evidence output

## Out of scope

ImpactPrism does not currently prove runtime reachability, detect every build
artifact, scan vulnerabilities, or determine legal applicability. Those limits
must remain visible in documentation and machine-readable diagnostics.
