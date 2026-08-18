# Reddit draft — Go

## Suggested title

I built an offline Go dependency-integrity check for imports, `go.mod`, and `go.sum`

## Draft

I built ImpactPrism to check whether a Go repository’s declared dependency story matches what its source actually imports.

Your lockfile is a lie. Trivy scans what you declared — ImpactPrism checks what you actually import, then hands you CRA evidence.

For Go repositories, the tool compares source imports with `go.mod` and `go.sum` and reports dependency drift, undeclared or transitive use, scope problems, and lockfile mismatches. The point is not to replace `govulncheck`, Trivy, or a normal SBOM generator. Those tools answer different questions. ImpactPrism focuses on dependency integrity: is the component inventory aligned with the code?

The output is a CycloneDX SBOM, a machine-readable report, and a CRA-grounded evidence pack with mapped references including Art 13(1)(b), Art 14(1), Annex I, and Annex VII. It is offline and does not require an account or API key.

The repository includes npm, Python, and Go demos; for a real Go repository, run the primary command:

```bash
pipx run impactprism scan .
```

The local project materials are in [demo/](../../demo/), and the primary command works from the root of the Go repository being reviewed.

I am looking for feedback from Go maintainers and platform/security engineers: how do you currently detect a source import that is missing from `go.mod`, or a dependency that is declared but not part of the application’s actual dependency story?

Feedback: [open an issue](https://github.com/bulltickr/impactprism/issues) with what you scanned, what you expected, and what is missing.

## Posting notes

- Confirm the Go demo is present and reproducible before posting.
- Replace relative links with verified public links only when posting from a public repository.
- Do not present the CRA mapping as legal advice or a compliance certification.
