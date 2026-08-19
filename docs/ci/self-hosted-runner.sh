#!/usr/bin/env bash
# Run this script from the repository root on a POSIX self-hosted runner.
# It is provider-neutral and does not require a CI service account or API.

set -euo pipefail

python_command="${IMPACTPRISM_PYTHON:-python3}"
created_venv=0

if [[ -n "${IMPACTPRISM_CI_VENV:-}" ]]; then
    venv_root="${IMPACTPRISM_CI_VENV}"
else
    venv_root="$(mktemp -d "${TMPDIR:-/tmp}/impactprism-ci.XXXXXX")"
    created_venv=1
fi

cleanup() {
    if [[ "${created_venv}" -eq 1 ]]; then
        rm -rf -- "${venv_root}"
    fi
}
trap cleanup EXIT

"${python_command}" -m venv "${venv_root}"
ci_python="${venv_root}/bin/python"
"${ci_python}" -m pip install --upgrade pip build "setuptools>=77"
"${ci_python}" -m pip install -e ".[test]"
"${ci_python}" -m pip check
"${ci_python}" scripts/ci.py verify
"${ci_python}" scripts/ci.py build
"${ci_python}" scripts/checksums.py dist --strict
