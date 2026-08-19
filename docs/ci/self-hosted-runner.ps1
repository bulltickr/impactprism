# Run this script from the repository root on a Windows self-hosted runner.
# It is provider-neutral and does not require a CI service account or API.

$ErrorActionPreference = "Stop"
$pythonCommand = if ($env:IMPACTPRISM_PYTHON) { $env:IMPACTPRISM_PYTHON } else { "python" }
$venvRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("impactprism-ci-" + [guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Path $venvRoot | Out-Null
    & $pythonCommand -m venv $venvRoot
    $ciPython = Join-Path $venvRoot "Scripts\python.exe"
    & $ciPython -m pip install --upgrade pip build "setuptools>=77"
    & $ciPython -m pip install -e ".[test]"
    & $ciPython -m pip check
    & $ciPython scripts/ci.py verify
    & $ciPython scripts/ci.py build
    & $ciPython scripts/checksums.py dist --strict
}
finally {
    if (Test-Path -LiteralPath $venvRoot) {
        Remove-Item -LiteralPath $venvRoot -Recurse -Force
    }
}
