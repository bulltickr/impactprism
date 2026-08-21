# Getting started

This guide takes a first-time user from an installed ImpactPrism release to a
reviewable local result. The scanner is intentionally local and offline after
installation; it does not require an account, API key, or hosted service.

## 1. Install a verified release

ImpactPrism publishes its official wheel and source archive on GitHub Releases.
Download the files from [v0.4.4](https://github.com/bulltickr/impactprism/releases/tag/v0.4.4),
download `SHA256SUMS`, and verify the artifacts before installing:

```bash
sha256sum -c SHA256SUMS
python -m pip install ./impactprism-0.4.4-py3-none-any.whl
```

On Windows PowerShell, the equivalent checksum command is:

```powershell
Get-FileHash .\impactprism-0.4.4-py3-none-any.whl -Algorithm SHA256
```

Compare the displayed digest with the matching line in `SHA256SUMS`.

## 2. Check the local environment

Run the offline diagnostic before scanning a repository:

```bash
impactprism --version
impactprism doctor .
```

`doctor` distinguishes an unsupported runtime, missing local dependency, missing
manifest, and missing lockfile. A lockfile warning is useful context: the scan
can still run, but it may report `MISSING_LOCKFILE`.

## 3. Run the first scan

Start with the clean npm demo to see the successful path:

```bash
impactprism scan demo/clean-app \
  --report impactprism-reports/clean-report.json \
  --evidence impactprism-reports/clean-evidence.json
```

Then run the finding-bearing demo:

```bash
impactprism scan demo/npm-app \
  --report impactprism-reports/findings-report.json \
  --evidence impactprism-reports/findings-evidence.json
```

The second command intentionally exits with code `1`. That is a useful result,
not a command failure: the report and evidence files are still written and
should contain a declared-unused dependency, a missing-lockfile signal, and an
undeclared import. Use `--json` when another tool will consume the canonical
scan report.

The same demos are available for Python and Go:

```bash
impactprism scan demo/python-clean
impactprism scan demo/go-clean
```

## 4. Read the result in the right order

1. Check the exit code and `counts.total`.
2. Read each finding's `finding_type`, package, source locations, and rationale.
3. Check the observed manifest, lockfile, and source inputs in the report.
4. Open the evidence output and treat `REVIEW_REQUIRED` as a review queue, not
   as an automated compliance conclusion.
5. If the result is surprising, reproduce it with a minimal sanitized fixture
   before changing a rule.

ImpactPrism is not a CVE scanner and a clean result is limited to the supported
inputs and rules. Review [scope and limitations](../README.md#project-status-and-trust-boundaries)
before treating a result as release evidence.

## 5. Add it to CI

For GitHub Actions, use the pinned Action reference shown in
[action/README.md](../action/README.md). For other providers, copy one of the
provider-neutral examples in [docs/ci](ci/README.md). The portable contract is:

```bash
python scripts/ci.py verify
python scripts/ci.py build
```

The scanner itself remains the source of truth; the GitHub Action is an adapter
that adds workflow outputs such as SARIF and artifact upload.

## 6. If the result looks wrong

Do not paste a private repository or complete proprietary lockfile into an
issue. Follow [SUPPORT.md](../SUPPORT.md), reduce the case to the smallest
sanitized manifest, lockfile, and source-import shape, and include the exact
ImpactPrism version and command. Contributors can use
[Adding sanitized fixtures](ADDING_FIXTURES.md) to turn that reproduction into
a durable regression test.
