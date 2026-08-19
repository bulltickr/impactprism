# CRA CI check

This repository runs a Cyber Resilience Act (CRA) dependency check on every
pull request. The workflow lives in `.github/workflows/cra-check.yml`.

## Trigger

Runs on every pull request — no branch or path filters.

## What it does

1. Checks out the PR branch.
2. Runs the trusted `main.py analyze` entry point against the checked-out repo
   to produce `report.json` (drift and undeclared dependencies). The workflow
   explicitly excludes the repository's `tests`, `fixtures`, `demo`, and
   generated/build directories because those contain intentional planted
   findings and are covered by separate CI fixtures.
3. Runs `main.py evidence` to turn the report into a CRA clause-grounded
   evidence pack (`evidence.md`, `evidence.json`).
4. Posts the Markdown evidence summary as a PR comment.
5. Fails the check when findings or errors are present.

## Fail semantics

The analyzer exit code decides the result:

| Exit code | Meaning                                   | Check result |
|-----------|-------------------------------------------|--------------|
| 0         | Clean — no drift, no undeclared           | Pass (green) |
| 1         | Drift and/or undeclared dependencies      | Fail (red)   |
| 2         | Invalid path, missing package.json, error | Fail (red)   |

Both drift and undeclared dependencies are treated as critical findings
because each category maps to CRA clauses (see the evidence pack). The
evidence comment is still posted when findings fail the gate, so PR authors
always see why. A scanner error (exit code 2) does not produce a misleading
evidence comment.

## Run it locally

```
python main.py analyze . --ecosystem npm \
  --exclude tests --exclude fixtures --exclude demo \
  --exclude node_modules --exclude build --exclude dist \
  --exclude .git --exclude .cache --exclude coverage --exclude public \
  --report report.json
python main.py evidence report.json --markdown evidence.md --json evidence.json
```

## Notes

No secrets or additional configuration are required. The check uses the
default `GITHUB_TOKEN` with `pull-requests: write`. For PRs opened from
forks, that token is read-only unless a maintainer approves the workflow, so
the evidence comment may be skipped on fork PRs by default — the gate still
fails correctly.
