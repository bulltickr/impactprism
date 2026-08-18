# Security policy

## Scope

ImpactPrism is an offline static-analysis tool. It reads the repository passed
to it and writes reports to configured output paths. It is not a vulnerability
database, a legal compliance determination, or a guarantee that all runtime
dependencies have been discovered.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through a [GitHub private
vulnerability report](https://github.com/bulltickr/impactprism/security/advisories/new).
If private reporting is unavailable, open a minimal issue asking for a private
contact channel; do not include exploit details, secrets, or customer data in
the issue.

Include the affected version or commit, reproduction steps, expected impact,
and a suggested mitigation when available.

## Supported versions

The latest tagged release is the only version receiving routine security fixes.
Development branches may contain incomplete behavior and should not be treated
as production security controls.

## Safe disclosure

Please allow reasonable time for investigation and a coordinated fix before
public disclosure. We will credit reporters who want attribution. The threat
model and non-goals are documented in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
