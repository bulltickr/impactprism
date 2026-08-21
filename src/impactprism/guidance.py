"""Stable, review-first remediation guidance for scanner findings."""

from __future__ import annotations

from copy import deepcopy


_GENERIC_GUIDANCE = {
    "summary": "Review the finding against the supported repository inputs before changing dependency files.",
    "steps": [
        "Confirm the observed manifest, lockfile, source location, and package identity.",
        "Make the smallest reviewed change that matches the repository's package manager.",
        "Regenerate or validate the lockfile with approved tooling, then rerun the scan.",
    ],
    "caution": "A clean rerun is evidence for the supported inputs only; it does not prove runtime dependency completeness.",
}


_GUIDANCE = {
    "UNDECLARED_DIRECT_USE": {
        "summary": "Declare the directly imported package in the manifest for the package that owns the source file.",
        "steps": [
            "Confirm the import is intentional and identify whether it is runtime or test-only code.",
            "Add the package to the matching manifest scope using the repository's package manager.",
            "Regenerate and review the lockfile, then rerun the scan and relevant tests.",
        ],
        "caution": "Do not copy a guessed version from an unrelated project or treat a transitive install as an intentional direct dependency.",
    },
    "DIRECT_DEPENDENCY_USED_TRANSITIVELY": {
        "summary": "Declare the directly imported package instead of relying on a transitive dependency.",
        "steps": [
            "Confirm the package is a deliberate direct API or runtime dependency.",
            "Add it to the appropriate manifest scope and preserve the repository's version policy.",
            "Regenerate and review the lockfile, then rerun the scan and relevant tests.",
        ],
        "caution": "A package being present in the lockfile does not make an undeclared direct import reproducible or owned by the project.",
    },
    "DECLARED_UNUSED_CANDIDATE": {
        "summary": "Confirm whether the declared package is genuinely unused before removing or moving it.",
        "steps": [
            "Check generated, dynamic, test, and configuration-driven usage that is outside the supported static scan boundary.",
            "If it is unused, remove it with the package manager or document why it remains declared.",
            "Regenerate and review the lockfile, then rerun the scan and relevant tests.",
        ],
        "caution": "This is an advisory candidate, not proof that the package can be removed; runtime-only or generated usage may not be visible.",
    },
    "LOCKFILE_MANIFEST_MISMATCH": {
        "summary": "Bring the manifest and lockfile back into agreement using the repository's package manager.",
        "steps": [
            "Inspect the declared range, locked version, lockfile path, and package-manager format in the finding.",
            "Use approved package-manager tooling to update the manifest or regenerate the lockfile as appropriate.",
            "Review the dependency diff and rerun the scan before accepting the change.",
        ],
        "caution": "Do not hand-edit a lockfile when package-manager regeneration is available; a parser or resolution failure must not be hidden as a clean result.",
    },
    "MISSING_LOCKFILE": {
        "summary": "Create and commit the supported lockfile for the dependency manifest, or record the intentional evidence gap.",
        "steps": [
            "Identify the package manager used by the repository and choose its supported lockfile format.",
            "Generate the lockfile with approved, reviewable tooling and commit it with the manifest.",
            "Rerun the scan and confirm the resulting lockfile covers the intended dependency scope.",
        ],
        "caution": "If the repository intentionally does not commit a lockfile, keep the finding visible and document the reproducibility boundary.",
    },
    "SCOPE_MISMATCH": {
        "summary": "Align the dependency declaration with the source scope where the package is actually used.",
        "steps": [
            "Confirm whether the import belongs to runtime, build, development, or test code.",
            "Move the dependency to the matching manifest scope, or move the import to the intended source scope.",
            "Regenerate the lockfile and rerun the scan plus the relevant production and test commands.",
        ],
        "caution": "Changing dependency scope can affect packaging and production installs; review the resulting artifact, not only the scan result.",
    },
    "UNRESOLVED_IMPORT": {
        "summary": "Verify the import target, package exports, and supported local-resolution configuration.",
        "steps": [
            "Confirm the source path or package specifier is intentional and exists in the checked-out repository or lockfile.",
            "Fix the import, package export, workspace mapping, or supported alias configuration as appropriate.",
            "Rerun the scan and the relevant build or test command from a clean checkout.",
        ],
        "caution": "ImpactPrism does not execute repository code or infer non-literal runtime resolution, so unresolved dynamic loading remains a separate review gap.",
    },
    "SCANNER_ERROR": {
        "summary": "Resolve the scanner diagnostic before interpreting the repository as clean.",
        "steps": [
            "Read the diagnostic and validate the affected manifest, lockfile, repository path, and local runtime.",
            "Fix the input or environment problem without suppressing the parser or scanner error.",
            "Rerun the scan and confirm that a normal finding result or a clean result is produced.",
        ],
        "caution": "A scanner error is not a passing scan and must not be converted into a compliance or release claim.",
    },
}


def get_remediation_guidance(finding_type: str | None) -> dict:
    """Return a defensive copy of the guidance for a finding family."""

    key = str(finding_type or "").upper()
    return deepcopy(_GUIDANCE.get(key, _GENERIC_GUIDANCE))


__all__ = ["get_remediation_guidance"]
