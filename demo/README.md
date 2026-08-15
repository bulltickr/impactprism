# ImpactPrism demo apps

`npm-app` demonstrates dependency findings. It declares `react` but never
imports it (drift), and imports `missingpkg` without declaring it
(undeclared). Running the analyzer on it exits 1 and produces a report whose
`drift` and `undeclared` lists are both non-empty.

`clean-app` demonstrates a clean pass. It declares `lodash` and imports it, so
there is no drift and no undeclared dependency; the analyzer exits 0.

From the repository root, scan either app with:

```text
python main.py analyze demo\npm-app --json
python main.py analyze demo\clean-app --json
```
