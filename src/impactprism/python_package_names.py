"""Curated mappings between Python distributions and import packages.

Python project names and import package names are independent metadata.  Keep
this registry deliberately small and evidence-backed: guessing a distribution
from an import name can recommend the wrong package, especially when multiple
distributions provide the same namespace.
"""

from __future__ import annotations

from .python_manifest import canonical_name

__all__ = [
    "PYTHON_IMPORT_ALIASES",
    "distribution_for_import",
    "import_aliases_for_distribution",
]


# Distribution names use PEP 503 comparison spelling. Import names are kept
# as their top-level package spelling because callers already strip submodules.
# Add entries only when the relationship is documented by the upstream
# project or otherwise independently verified.
PYTHON_IMPORT_ALIASES = {
    "beautifulsoup4": frozenset({"bs4"}),
    "scikit-learn": frozenset({"sklearn"}),
    "python-dateutil": frozenset({"dateutil"}),
    "pyyaml": frozenset({"yaml"}),
    "pillow": frozenset({"pil"}),
    "opencv-python": frozenset({"cv2"}),
    "attrs": frozenset({"attr"}),
    "python-dotenv": frozenset({"dotenv"}),
}

_PYTHON_IMPORT_TO_DIST = {
    import_name: distribution
    for distribution, import_names in PYTHON_IMPORT_ALIASES.items()
    for import_name in import_names
}


def import_aliases_for_distribution(distribution: str) -> frozenset[str]:
    """Return curated import names provided by *distribution*."""
    return PYTHON_IMPORT_ALIASES.get(canonical_name(distribution), frozenset())


def distribution_for_import(import_name: str) -> str | None:
    """Return a curated distribution for an import name, if one is known."""
    return _PYTHON_IMPORT_TO_DIST.get(canonical_name(import_name))
