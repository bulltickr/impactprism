# Sanitized reproduction intake

External reports are most useful when they become small, reviewable
reproductions rather than copies of private repositories. ImpactPrism accepts
two kinds of public reproduction bundle:

- `synthetic`: a deliberately invented fixture that isolates a behavior;
- `sanitized-external`: a reduced shape derived from a real repository after
  private and identifying material has been removed.

Neither label is an accuracy claim. A reproduction records a behavior to
review; it does not prove that the original repository, package, or scan is
secure or compliant.

## Bundle contract

Each bundle is a directory containing `impactprism-reproduction.json` and only
the files listed in its `files` array. The metadata records the ecosystem,
package-manager format, review-only scan command, expected finding families,
and four required sanitization confirmations:

```json
{
  "schema_version": 1,
  "id": "npm-undeclared-direct-use",
  "provenance": "synthetic",
  "ecosystem": "npm",
  "package_manager": "npm",
  "scan": {
    "command": "impactprism scan . --ecosystem npm --json",
    "expected_result": "findings",
    "expected_finding_types": ["UNDECLARED_DIRECT_USE"]
  },
  "sanitization": {
    "secrets_removed": true,
    "proprietary_source_removed": true,
    "private_urls_removed": true,
    "customer_identifiers_removed": true
  },
  "files": [
    {"path": "package.json", "role": "manifest"},
    {"path": "package-lock.json", "role": "lockfile"},
    {"path": "src/index.js", "role": "source"}
  ]
}
```

The metadata is intentionally explicit. Reviewers can see what the submitter
believes the case exercises before running the scanner, and accidental extra
files cannot silently become part of the fixture.

## Validate before opening a pull request

The validator is read-only. It checks JSON shape, known finding families,
relative paths, declared-file parity, symlinks, sensitive-looking filenames,
generated/repository directories, and conservative size limits. It does not
execute source code, install dependencies, contact a registry, inspect file
contents for every possible secret, or decide whether the expected behavior is
correct.

Validate the checked-in example with:

```bash
python scripts/validate_reproduction.py tests/fixtures/reproduction_intake
```

The provider-neutral gate runs the same check through:

```bash
python scripts/ci.py validate-reproductions
```

## Produce a review record

After validation, a maintainer can run the read-only review command:

```bash
python scripts/review_reproduction.py tests/fixtures/reproduction_intake --json
```

The result records the scanner version, bundle provenance, declared expected
result, actual finding families, normalized findings, and whether the observed
result matches the submitter's declaration. The command supports one bundle or
a parent directory containing bundles. It is deliberately not a promotion
command: a passing review record is evidence for human triage, not permission
to add a case to the governed correctness matrix.

The provider-neutral verification runs the checked-in review example through:

```bash
python scripts/ci.py review-reproductions
```

The review runner accepts one ecosystem at a time (`npm`, `python`, or `go`).
`multiple` bundles remain validation-only until a maintainer splits them into
separate, reproducible cases. Review execution is static and local: it does
not run repository scripts, install dependencies, contact a registry, or
modify the bundle.

## Maintainer review sequence

1. Remove credentials, proprietary source, private registry details, customer
   names, and unneeded files before reviewing the behavior.
2. Run the validator and inspect the complete bundle against its metadata.
3. Run `scripts/review_reproduction.py <bundle> --json` with the pinned
   ImpactPrism commit or release. Do not install or execute code from the
   submitted bundle as part of the scanner test.
4. Compare the actual finding family, source location, manifest, lockfile, and
   scope with the expected behavior. A matching result is a triage signal, not
   an accuracy claim.
5. Decide whether the case is a regression, a documented limitation, or an
   unsupported shape. Add a governed correctness case only when the behavior
   and expected output are stable enough to become a public contract.
6. If guidance changes, update its contract tests and changelog entry. Keep
   finding identity, exit-code, and schema compatibility in view.

Do not promote a sanitized reproduction into the pinned real-repository
compatibility corpus automatically. That corpus has separate provenance,
selection, and evidence requirements described in
[COMPATIBILITY_REPORT.md](COMPATIBILITY_REPORT.md).

## Submission checklist

- [ ] The bundle is the smallest useful shape.
- [ ] `provenance` is honestly labeled as `synthetic` or `sanitized-external`.
- [ ] All four sanitization flags are true after an actual human review.
- [ ] No secrets, proprietary source, private URLs, customer identifiers, or
      complete private lockfiles remain.
- [ ] Every file is listed in `impactprism-reproduction.json`.
- [ ] The scan command is review-only and does not install, apply, deploy, or
      merge anything.
- [ ] The expected result and finding families are explicit.
- [ ] `python scripts/validate_reproduction.py <bundle>` passes.
