# ImpactPrism demo apps

`npm-app` demonstrates dependency findings. It declares `react` but never
imports it (drift), and imports `missingpkg` without declaring it
(undeclared). Running the analyzer on it exits 1 and produces a report whose
`drift` and `undeclared` lists are both non-empty.

`clean-app` demonstrates a clean pass. It declares `lodash` and imports it, so
there is no drift and no undeclared dependency; the analyzer exits 0.

`python-clean` demonstrates the equivalent clean pass for Python. It declares
and locks `requests`, then imports it from `src/app.py`.

`go-clean` demonstrates the equivalent clean pass for Go with only a standard
library import.

From an installed checkout, scan the demos with the canonical CLI:

```text
impactprism scan demo/npm-app --json
impactprism scan demo/clean-app --json
impactprism scan demo/python-clean --json
impactprism scan demo/go-clean --json
```

The finding-bearing npm demo intentionally exits with code `1`; it should
report `DECLARED_UNUSED_CANDIDATE`, `MISSING_LOCKFILE`, and
`UNDECLARED_DIRECT_USE`. The three clean demos exit `0` with no findings. On
Windows, use forward slashes as shown or replace them with PowerShell-
compatible paths.

To validate every demo without leaving output files in the repository, run:

```text
python scripts/ci.py validate-demos
```

For a complete contributor gate, see
[Adding sanitized fixtures](../docs/ADDING_FIXTURES.md).
