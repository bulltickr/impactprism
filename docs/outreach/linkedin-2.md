# LinkedIn post 2 — CRA Art 13(1)(b) tutorial

## CRA Art 13(1)(b) in plain English: start with component reality

For a product with digital elements, component transparency is not just a polished SBOM file. The practical question is whether the component record is grounded in what the product actually contains and uses.

That is the reason for ImpactPrism’s CRA evidence workflow.

### A practical review loop

1. Compare the manifest with the lockfile.
2. Compare both with the imports found in source code.
3. Review undeclared, transitive-use, scope, drift, and lockfile-mismatch findings.
4. Preserve the report, CycloneDX SBOM, and review notes as evidence.

ImpactPrism maps dependency-integrity findings to Art 13(1)(b), Art 14(1), Annex I Part II, and Annex VII in its evidence pack. It also maps unnecessary or scope-inconsistent components to the secure-by-default references used by the project’s clause map.

The command is:

```bash
pipx run impactprism scan .
```

It is offline, requires no account or API key, and supports selected npm, Python, and Go checks. The local example is [demo/](../../demo/); the sample output is [docs/samples/evidence-sample.md](../samples/evidence-sample.md).

This is an evidence aid, not a legal opinion or a claim that running one scan establishes CRA compliance. Teams still need to determine scope, applicability, review ownership, and the evidence their product and process require.

Primary CTA: run `pipx run impactprism scan .` on a real repository and inspect the evidence pack.

Feedback: [open an issue](https://github.com/bulltickr/impactprism/issues) with what you scanned, what you expected, and what is missing.

#CyberResilienceAct #CRA #SBOM #opensource #productsecurity

## Publishing note

Have legal/compliance reviewers check the wording and applicability before publication. Replace relative links with verified public links only after the repository is public.
