# Newsletter pitch

## Subject options

- Story idea: the dependency-integrity gap behind manifest-only SBOMs
- A practical CRA angle: checking what npm, Python, and Go code actually imports
- Open-source tool for CRA component-transparency evidence

## Three-sentence pitch

ImpactPrism is an open-source tool for npm, Python, and Go that performs an offline scan after installation. It compares manifests, lockfiles, and source imports to find undeclared, transitive, scope, drift, and lockfile-mismatch dependencies—a gap manifest-only inventories can leave. It turns those findings into a CycloneDX SBOM, a machine-readable report, and a review-oriented evidence pack with contextual references mapped to Art 13(1)(b), Art 14(1), Annex I, and Annex VII. The story is a practical look at how small EU software teams can make dependency inventory evidence more faithful without requiring an account, API key, or hosted service.

## Supporting material

- Local demo: [demo/](../../demo/)
- Sample evidence pack: [docs/samples/evidence-sample.md](../samples/evidence-sample.md)
- Primary CTA for readers: install from GitHub and run `impactprism scan .`
- Feedback loop: [open an issue](https://github.com/bulltickr/impactprism/issues)

## Outreach handling

Do not send this draft until the target publication is independently verified as active, accepts relevant pitches, and has a current submission route. Replace the local demo link with a verified public repository/demo link only at send time. Do not invent an editor email, form URL, or publication URL.
