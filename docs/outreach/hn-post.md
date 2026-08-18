# Show HN draft

## Title options

1. Show HN: ImpactPrism — checks whether your npm/Python/Go dependencies are actually used, then ships CRA evidence
2. Show HN: Your lockfile is a lie — ImpactPrism checks what your code actually imports
3. Show HN: An offline dependency-integrity scanner for npm, Python, and Go with EU CRA evidence output
4. Show HN: Find undeclared and transitive dependencies your SBOM does not report
5. Show HN: ImpactPrism — CycloneDX, SARIF, and CRA evidence from one dependency-integrity scan

## Draft

Hi HN — I built ImpactPrism to answer a question that manifest-only SBOMs do not answer: what is the application actually importing?

Your lockfile is a lie. Trivy scans what you declared — ImpactPrism checks what you actually import, then hands you CRA evidence.

ImpactPrism analyzes npm, Python, and Go repositories offline. It compares manifests, lockfiles, and source imports to find dependency drift, undeclared direct imports, transitive use, scope mismatches, and lockfile mismatches. It is not a vulnerability scanner and it is not trying to replace a general-purpose SBOM generator.

One command produces a CycloneDX SBOM, a dependency-integrity report, and a CRA-grounded evidence pack covering the project’s mapped Art 13(1)(a/b), Art 14(1), Annex I, and Annex VII references. The GitHub Action can also produce SARIF and a PR evidence comment.

The wedge is the three failure modes I kept seeing around manifest-based inventory:

- a package imported by source but absent from the manifest;
- a package reached transitively but used as if it were a direct dependency; and
- a declared package or dependency scope that does not match reality.

Try it locally:

```bash
python -m pip install "git+https://github.com/bulltickr/impactprism.git"
impactprism scan .
```

The committed demo is at [demo/](../../demo/) and the sample evidence pack is [docs/samples/evidence-sample.md](../samples/evidence-sample.md). The command is offline and does not require an account or API key.

ImpactPrism is early, open source, and intentionally narrow. I would especially like feedback from EU agency developers, indie SaaS founders, security engineers, and npm/Python/Go maintainers: what did the scan find that your current SBOM or dependency check did not?

Primary CTA: install from GitHub and run `impactprism scan .` on a real repository.

Feedback: [open an issue](https://github.com/bulltickr/impactprism/issues) with what you scanned, what you expected, and what is missing.

## Posting notes

- Attach only reproducible output from the committed demo or a real local run.
- Replace relative demo links with verified public links only after the repository is public.
- Do not describe ImpactPrism as a vulnerability scanner or as legal/compliance advice.
