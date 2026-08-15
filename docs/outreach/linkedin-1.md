# LinkedIn post 1 — The dependency your SBOM tool cannot see

The dependency your SBOM tool cannot see is often the one your code imports but your manifest never declared.

That is the gap behind ImpactPrism.

Your lockfile is a lie. Trivy scans what you declared — ImpactPrism checks what you actually import, then hands you CRA evidence.

An ordinary manifest-based inventory can tell you that a package is declared. It does not necessarily tell you that:

- production code imports an undeclared package;
- a transitive package has become a de facto direct dependency;
- a dev dependency is used by production code; or
- a declared package is unused and the lockfile no longer reflects intent.

ImpactPrism compares declarations, lockfiles, and source imports for npm and Go. One offline command produces a CycloneDX SBOM, a drift/undeclared report, and a CRA-grounded evidence pack mapped to Art 13(1)(a/b), Art 14(1), Annex I, and Annex VII.

It is not a vulnerability scanner. It is not a replacement for your SBOM or SCA tooling. It answers a narrower question: does the dependency inventory match reality?

Primary CTA: run `pipx run impactprism scan .` on one real repository.

The local demo is [demo/](../../demo/), with a sample evidence pack in [docs/samples/](../samples/).

If it finds something surprising, [open an issue](https://github.com/bulltickr/impactprism/issues) with what you scanned, what you expected, and what is missing.

#dependencysecurity #opensource #SBOM #CRA #softwareSupplyChain

## Publishing note

Replace relative demo links with verified public links only after the repository is public. Keep the claim framed as dependency-integrity analysis, not vulnerability coverage or legal advice.
