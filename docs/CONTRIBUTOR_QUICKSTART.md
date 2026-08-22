# Contributor quickstart

This is the shortest reliable path from a fresh checkout to a reviewable
ImpactPrism change. The repository is intentionally test-first: a behavior
change should arrive with a small public fixture, a focused assertion, and a
clear statement of what remains outside the scanner's scope.

## 1. Set up a development checkout

```bash
git clone https://github.com/bulltickr/impactprism.git
cd impactprism
python -m venv .venv
```

Activate the environment using the shell you use for development:

```bash
# macOS or Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install the test extras and run the provider-neutral gate:

```bash
python -m pip install -e ".[test]"
python scripts/ci.py verify
```

The first run establishes a known-good baseline. If it fails before reaching
the project commands, record the Python version, operating system, and the
first actionable error in the pull request or issue.

## 2. Choose the smallest contribution path

| Change | Start here | Minimum evidence |
|---|---|---|
| Documentation or wording | The relevant Markdown file | Link or command checked locally |
| Parser or finding behavior | [`docs/ADDING_FIXTURES.md`](ADDING_FIXTURES.md) | Minimal fixture plus focused test |
| Output, schema, SARIF, SBOM, or Action behavior | Existing contract fixture and schema | Regression fixture, test, docs, and changelog note |
| A real-repository shape | [`docs/REPRODUCTION_INTAKE.md`](REPRODUCTION_INTAKE.md) | Sanitized reproduction validated before review |
| CI-provider integration | [`docs/CI_PORTABILITY.md`](CI_PORTABILITY.md) | Provider-neutral command remains the source contract |
| Unsupported or ambiguous behavior | [`docs/HARD_CASE_COVERAGE.md`](HARD_CASE_COVERAGE.md) | Explicit boundary documentation, not a forced clean result |

For a reproduction bundle, the maintainer review command is
`python scripts/review_reproduction.py <bundle> --json`. It validates the
bundle, runs the local scanner without executing repository code, and records
the expected-versus-observed result for human triage.

Do not begin with the public compatibility corpus for an ordinary pull
request. It is a maintainer-triggered, pinned regression contract for selected
upstream trees and has a separate network-bound preparation step.

## 3. Work in a focused loop

Run the narrowest useful check while iterating, then run the complete gate
before opening the pull request:

```bash
# all unit and integration tests
python -m pytest tests -q

# public demos across npm, Python, and Go
python scripts/ci.py validate-demos

# governed fixture contracts
python scripts/ci.py conformance
python scripts/ci.py correctness

# complete provider-neutral verification
python scripts/ci.py verify

# distribution contents, when packaging or release metadata changed
python scripts/ci.py build
```

The complete gate is the meaningful local contract. Individual commands are
feedback tools, not substitutes for it when the change affects shared code or
public output.

## 4. Keep reproductions public and minimal

Use fictional package names and module paths unless a public upstream shape is
essential. Remove credentials, private registry URLs, customer identifiers,
proprietary source, generated secrets, and unnecessary lockfile content. A
small fixture is easier to review and less likely to accidentally disclose
something than a copied repository.

Never make a parser failure look clean just to satisfy a fixture. If the shape
is unsupported, preserve the diagnostic and document the boundary. A clean
fixture demonstrates one supported input contract; it does not establish
complete dependency discovery or broad accuracy.

## 5. Open a useful pull request

Describe four things in the PR body:

1. the user problem and intended behavioral contract;
2. the smallest fixture or input shape that exercises it;
3. the commands and platforms used for verification; and
4. the compatibility, output, and limitation impact.

Keep the change focused. If the behavior changes JSON, SARIF, SBOM, evidence,
exit codes, Action inputs, or finding identity, call that out explicitly and
include the corresponding contract coverage. Reviewers should be able to tell
whether a clean result, a finding, an unsupported input, or a scanner error is
the intended outcome.

## 6. Ask for help with enough context

Use the issue template that matches the problem. Include the ImpactPrism
version or commit, ecosystem and package-manager format, exact command,
expected result, actual result, and a sanitized reproduction when relevant.
Security concerns belong in the private security-reporting path described in
[`SECURITY.md`](../SECURITY.md), not in a public issue.

For the maintainer review sequence and label vocabulary, see
[`docs/MAINTAINER_TRIAGE.md`](MAINTAINER_TRIAGE.md). For release work, see
[`docs/RELEASING.md`](RELEASING.md).
