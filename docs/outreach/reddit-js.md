# Reddit draft — JavaScript / Node

## Suggested title

My SBOM listed the packages in `package.json`, but not the package my code actually imported

## Draft

I built ImpactPrism, an offline dependency-integrity scanner for npm repositories.

Your lockfile is a lie. Trivy scans what you declared — ImpactPrism checks what you actually import, then hands you CRA evidence.

The useful distinction is between an inventory of declarations and an inventory of runtime reality. ImpactPrism compares `package.json`, the lockfile, and JavaScript source imports to flag:

- undeclared direct imports;
- dependencies used only through a transitive path;
- declared-but-unused packages;
- production code using a dev dependency; and
- lockfile or scope mismatches.

It then writes a CycloneDX SBOM, a report, and a CRA-grounded evidence pack. The relevant mapped references include Art 13(1)(b), Art 14(1), Annex I, and Annex VII. It is not a CVE scanner; it is meant to catch dependency-integrity gaps before another tool reports a vulnerability in a component you did not realize you shipped.

Try the local demo:

```bash
pipx run impactprism scan demo/npm-app
```

The source demo is [demo/npm-app/](../../demo/npm-app/) and a sample evidence pack is [docs/samples/evidence-sample.md](../samples/evidence-sample.md). It runs offline, with no account or API key.

Primary CTA: run `pipx run impactprism scan .` on a real Node repository and see whether declared equals used.

Feedback: [open an issue](https://github.com/bulltickr/impactprism/issues) with what you scanned, what you expected, and what is missing.

This is an early project, so I am interested in false positives, monorepo/workspace behavior, dynamic imports, bundler edge cases, and whether this distinction is useful in your CI review.

## Posting notes

- Keep this as a single original post; do not cross-post unchanged to multiple communities.
- Replace relative links with verified public links only when posting from a public repository.
- Avoid claiming that a scan alone establishes CRA compliance.
