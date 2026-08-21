# Adding sanitized fixtures

Fixtures are the preferred way to improve ImpactPrism. They make a behavior
reviewable without sharing a private repository and keep a parser change tied
to a reproducible contract.

For a report derived from a real repository, start with the
[sanitized reproduction intake contract](REPRODUCTION_INTAKE.md). Validate the
small bundle before converting it into a governed correctness fixture.

## Choose the smallest public shape

Start with only the files needed to express the behavior:

| Ecosystem | Typical files |
|---|---|
| npm | `package.json`, one supported lockfile, and a small `src/index.js` or `.ts` |
| Python | `pyproject.toml` or `requirements.txt`, a supported lockfile, and `src/app.py` |
| Go | `go.mod`, optional `go.sum` or `vendor/modules.txt`, and one `.go` file |

Use fictional package names and module paths unless a public upstream shape is
essential to the case. Never include credentials, private registry URLs,
customer names, proprietary source, generated secrets, or an unredacted private
lockfile.

## Put the fixture in the right layer

- `tests/fixtures/correctness/` is for a known input shape with an explicit
  expected normalized result. Add or update a case in
  `benchmarks/correctness/cases.json` when the behavior belongs in the governed
  correctness contract.
- `tests/fixtures/conformance/` is for output-schema and contract examples.
- `tests/fixtures/remediation/` is for proposed remediation and rollback
  behavior.
- `demo/` is for a short, readable user-facing example that belongs in the
  onboarding path.
- `benchmarks/compatibility/` is reserved for maintainer-reviewed, pinned
  public repositories. Do not add a real repository there from a normal pull
  request or present the corpus as an accuracy score.

If the case is primarily a limitation, document the boundary in
`docs/HARD_CASE_COVERAGE.md` or the relevant ecosystem guide instead of making
the fixture appear more supported than it is.

## Make the expected behavior explicit

Every fixture change should answer:

1. Which ecosystem and package-manager format is being exercised?
2. Which finding types are expected, including the expected clean case?
3. Which source import or manifest entry creates the behavior?
4. What should remain out of scope, such as dynamic or generated code?
5. Does the change affect JSON, SARIF, SBOM, evidence, or Action output?

Prefer exact finding-family assertions and stable normalized fields over brittle
assertions on console formatting. Parser failures must remain scanner errors;
do not make a fixture pass by weakening an error into a clean result.

## Run the public checks

From an installed development checkout:

```bash
python scripts/ci.py validate-demos
python scripts/ci.py test
python scripts/ci.py conformance
python scripts/ci.py correctness
```

For a normal pull request, run the complete provider-neutral gate:

```bash
python scripts/ci.py verify
```

The demo validator runs all checked-in public examples across npm, Python, and
Go. It uses a temporary output directory, accepts the intentional non-zero
finding-demo exit, and verifies that clean demos remain clean.

## Pull-request checklist

- [ ] The fixture is minimal and sanitized.
- [ ] The expected finding families or clean result are asserted.
- [ ] The affected output contract and documentation were reviewed.
- [ ] The relevant limitation or parser assumption is documented.
- [ ] `python scripts/ci.py verify` passes.
- [ ] `CHANGELOG.md` is updated for a user-visible behavior or output change.
