# Provider-neutral CI examples

These are copyable examples for running the same ImpactPrism verification
contract outside the repository's GitHub Actions workflows. They are kept
under `docs/ci/` deliberately: copy one into the provider's expected location
when adopting it, rather than enabling several provider configurations in one
checkout.

| Provider | Example | Provider reference |
|---|---|---|
| GitLab CI | [`gitlab-ci.yml`](gitlab-ci.yml) | [GitLab CI/CD YAML reference](https://docs.gitlab.com/ci/yaml/) |
| Azure Pipelines | [`azure-pipelines.yml`](azure-pipelines.yml) | [Microsoft Python pipeline guide](https://learn.microsoft.com/en-us/azure/devops/pipelines/ecosystems/python) |
| Jenkins | [`Jenkinsfile`](Jenkinsfile) | [Jenkinsfile reference](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/) |
| POSIX self-hosted runner | [`self-hosted-runner.sh`](self-hosted-runner.sh) | Local/provider-neutral shell |
| Windows self-hosted runner | [`self-hosted-runner.ps1`](self-hosted-runner.ps1) | Local/provider-neutral PowerShell |

Every example runs the same contract:

1. create or select an isolated Python environment;
2. install the project and its declared test/build dependencies;
3. run `python scripts/ci.py verify`;
4. build with `python scripts/ci.py build`; and
5. generate strict release-directory checksums.

The repository also checks these templates with
`python scripts/ci.py validate-ci-examples` so required commands and key
provider syntax cannot silently drift.

The examples assume the runner can obtain the declared package artifacts. For
air-gapped execution, pre-stage a wheelhouse and replace installation with an
approved `--no-index --find-links` command. The scanner and verification
commands do not call the GitHub API, require a GitHub token, or depend on a
hosted ImpactPrism service.

The examples do not publish packages, create releases, upload source code, or
send scan results to ImpactPrism. They are verification templates only.
