# Support

ImpactPrism is an early open-source project. The fastest way to get useful
help is to provide a small, reproducible example without secrets or
proprietary source code.

## Where to ask

- Usage questions and design discussion: use the [usage question template](https://github.com/bulltickr/impactprism/issues/new?template=usage_question.yml)
- Real repository shapes or unsupported package-manager formats: use the [compatibility report template](https://github.com/bulltickr/impactprism/issues/new?template=compatibility_report.yml)
- Incorrect or incomplete scanner behavior: use the [bug report template](https://github.com/bulltickr/impactprism/issues/new?template=bug_report.yml)
- Unexpected findings or suspected false positives: use the [false-positive template](https://github.com/bulltickr/impactprism/issues/new?template=false_positive.yml)
- Feature proposals: use the [feature request template](https://github.com/bulltickr/impactprism/issues/new?template=feature_request.yml)
- Security vulnerabilities: follow [SECURITY.md](SECURITY.md), not a public issue

## Include this context

Please include:

- the ImpactPrism commit or release version;
- ecosystem and package-manager format;
- the exact command and relevant options;
- a sanitized minimal fixture or repository shape;
- the expected result and actual result;
- whether the finding came from CLI, Action, SBOM, SARIF, or evidence output.

Do not upload credentials, private source, customer data, or complete
proprietary lockfiles. Reduce the reproduction to a small fixture whenever
possible.

## Scope

ImpactPrism is not a CVE database, legal advice, certification, audit opinion,
or guarantee that every runtime dependency has been discovered. Questions
about unsupported package managers and dynamic/runtime loading are welcome,
but should be framed as feature or coverage requests rather than assumed bugs.
