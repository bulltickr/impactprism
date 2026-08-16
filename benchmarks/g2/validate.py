"""Validate the frozen, local inputs for the internal G2 benchmark.

This module is deliberately a preflight only.  It never clones repositories,
opens URLs, runs the scanner, or calculates benchmark metrics.  A READY result
means that the frozen inputs have the shape needed by a future benchmark run;
it is not a G2 result or a performance claim.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml


EXPECTED_REPOSITORIES = 20
REQUIRED_ECOSYSTEM_QUOTAS = {"javascript": 6, "python": 7, "go": 5}
REQUIRED_MONOREPOS = 5
REQUIRED_DYNAMIC_REPOSITORIES = 4

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T[^\s]+Z$")
FINDING_TYPES = {
    "UNDECLARED_DIRECT_USE",
    "DECLARED_UNUSED_CANDIDATE",
    "DIRECT_DEPENDENCY_USED_TRANSITIVELY",
    "SCOPE_MISMATCH",
    "LOCKFILE_MANIFEST_MISMATCH",
    "MISSING_LOCKFILE",
    "UNRESOLVED_IMPORT",
    "SCANNER_ERROR",
    "UNSUPPORTED",
}
LABEL_STATUSES = {"present", "absent", "unsupported", "not_assessable"}
ECOSYSTEMS = set(REQUIRED_ECOSYSTEM_QUOTAS)

REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "benchmark_id",
    "status",
    "created_at_utc",
    "owner",
    "scanner",
    "repositories",
    "adjudication",
    "outputs",
)
REQUIRED_SCANNER_FIELDS = (
    "repository",
    "commit_sha",
    "requirements_lock",
    "environment_ref",
)
REQUIRED_REPOSITORY_FIELDS = (
    "id",
    "url",
    "default_branch",
    "commit_sha",
    "license_spdx",
    "license_evidence_url",
    "license_verified_at_utc",
    "primary_ecosystem",
    "secondary_ecosystems",
    "scan_subpath",
    "manifest_paths",
    "lockfile_paths",
    "selection_rationale",
    "is_monorepo",
    "monorepo_evidence",
    "has_dynamic_or_generated_code",
    "dynamic_generated_evidence",
    "source_snapshot_sha256",
    "ground_truth_ref",
)
REQUIRED_LABEL_FILE_FIELDS = (
    "repository_id",
    "commit_sha",
    "label_schema_version",
    "labels",
)
REQUIRED_LABEL_FIELDS = (
    "label_id",
    "repository_id",
    "commit_sha",
    "finding_type",
    "package",
    "status",
    "ecosystem",
    "source_file",
    "line",
    "column",
    "manifest",
    "lockfile",
    "rationale",
    "evidence_sha256",
)

# These are metadata declarations, not benchmark scores.  Values may be a
# status such as "not_run" or a repository-relative artifact reference.
REQUIRED_ADJUDICATION_FIELDS = (
    "status",
    "labeler_a",
    "labeler_b",
    "decisions",
    "sign_off",
)
REQUIRED_OUTPUT_FIELDS = (
    "status",
    "report",
    "bom",
    "evidence",
    "normalized_predictions",
    "hashes",
)


@dataclass(frozen=True)
class Diagnostic:
    """One actionable preflight problem."""

    path: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass
class PreflightResult:
    """Score-free result returned by :func:`validate_preflight`."""

    status: str
    manifest: str
    repositories_expected: int = EXPECTED_REPOSITORIES
    repositories_found: int = 0
    labels_found: int = 0
    quota_counts: dict[str, int] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    @property
    def errors(self) -> list[str]:
        """Compatibility-friendly rendered diagnostics for callers."""

        return [item.render() for item in self.diagnostics]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "manifest": self.manifest,
            "repositories_expected": self.repositories_expected,
            "repositories_found": self.repositories_found,
            "labels_found": self.labels_found,
            "quota_counts": dict(self.quota_counts),
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "scores_calculated": False,
            "g2_passed": False,
        }


def _diagnostic(result: PreflightResult, path: str, message: str) -> None:
    result.diagnostics.append(Diagnostic(path, message))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_mapping(
    result: PreflightResult, value: Any, path: str
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        _diagnostic(result, path, "must be an object")
        return None
    return value


def _require_fields(
    result: PreflightResult,
    value: Mapping[str, Any],
    fields: tuple[str, ...],
    path: str,
) -> None:
    for name in fields:
        if name not in value:
            _diagnostic(result, f"{path}.{name}", "missing required field")


def _validate_sha(
    result: PreflightResult, value: Any, path: str, pattern: re.Pattern[str]
) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        description = "40 lowercase hex characters" if pattern is SHA40 else "64 lowercase hex characters"
        _diagnostic(result, path, f"must be {description}")


def _validate_timestamp(result: PreflightResult, value: Any, path: str) -> None:
    if not isinstance(value, str) or not ISO_UTC.fullmatch(value):
        _diagnostic(result, path, "must be an ISO-8601 UTC timestamp ending in Z")


def _validate_url(result: PreflightResult, value: Any, path: str) -> None:
    parsed = urlparse(value) if isinstance(value, str) else None
    if parsed is None or parsed.scheme != "https" or not parsed.netloc:
        _diagnostic(result, path, "must be a canonical https URL")


def _validate_relative_path(
    result: PreflightResult, value: Any, path: str, allow_null: bool = False
) -> None:
    if allow_null and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        _diagnostic(result, path, "must be a repository-relative path")
        return
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        _diagnostic(result, path, "must not be absolute or escape the repository")


def _validate_string_list(
    result: PreflightResult, value: Any, path: str, *, nonempty: bool = False
) -> None:
    if not isinstance(value, list):
        _diagnostic(result, path, "must be a list")
        return
    if nonempty and not value:
        _diagnostic(result, path, "must contain at least one item")
    for index, item in enumerate(value):
        if not _is_nonempty_string(item):
            _diagnostic(result, f"{path}[{index}]", "must be a non-empty string")


def _load_yaml(result: PreflightResult, path: Path) -> Mapping[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    except OSError as error:
        _diagnostic(result, "manifest", f"cannot be read: {error}")
        return None
    except yaml.YAMLError as error:
        _diagnostic(result, "manifest", f"invalid YAML: {error}")
        return None
    return _require_mapping(result, value, "manifest")


def _load_json(result: PreflightResult, path: Path, label: str) -> Mapping[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError as error:
        _diagnostic(result, label, f"cannot be read: {error}")
        return None
    except json.JSONDecodeError as error:
        _diagnostic(result, label, f"invalid JSON: {error.msg}")
        return None
    return _require_mapping(result, value, label)


def _safe_local_ref(
    result: PreflightResult, root: Path, value: Any, path: str
) -> Path | None:
    _validate_relative_path(result, value, path)
    if not isinstance(value, str) or not value.strip():
        return None
    root = root.resolve()
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        _diagnostic(result, path, "must resolve inside the benchmark directory")
        return None
    return candidate


def _validate_metadata_block(
    result: PreflightResult,
    block: Any,
    path: str,
    required_fields: tuple[str, ...],
) -> None:
    mapping = _require_mapping(result, block, path)
    if mapping is None:
        return
    _require_fields(result, mapping, required_fields, path)
    for name in required_fields:
        if name in mapping and not _is_nonempty_string(mapping[name]):
            _diagnostic(result, f"{path}.{name}", "must be a non-empty string")


def _validate_repository(
    result: PreflightResult,
    repository: Any,
    index: int,
    benchmark_root: Path,
    seen_ids: set[str],
    seen_urls: set[str],
) -> dict[str, Any] | None:
    path = f"repositories[{index}]"
    mapping = _require_mapping(result, repository, path)
    if mapping is None:
        return None
    _require_fields(result, mapping, REQUIRED_REPOSITORY_FIELDS, path)

    repository_id = mapping.get("id")
    if not _is_nonempty_string(repository_id):
        _diagnostic(result, f"{path}.id", "must be a unique non-empty string")
    elif repository_id in seen_ids:
        _diagnostic(result, f"{path}.id", f"duplicate repository id {repository_id!r}")
    else:
        seen_ids.add(repository_id)

    url = mapping.get("url")
    _validate_url(result, url, f"{path}.url")
    if isinstance(url, str):
        if url in seen_urls:
            _diagnostic(result, f"{path}.url", f"duplicate repository URL {url!r}")
        seen_urls.add(url)

    _validate_sha(result, mapping.get("commit_sha"), f"{path}.commit_sha", SHA40)
    _validate_timestamp(result, mapping.get("license_verified_at_utc"), f"{path}.license_verified_at_utc")
    _validate_sha(result, mapping.get("source_snapshot_sha256"), f"{path}.source_snapshot_sha256", SHA256)
    for field_name in ("default_branch", "scan_subpath", "selection_rationale"):
        if not _is_nonempty_string(mapping.get(field_name)):
            _diagnostic(result, f"{path}.{field_name}", "must be a non-empty string")
    _validate_url(result, mapping.get("license_evidence_url"), f"{path}.license_evidence_url")
    _validate_string_list(result, mapping.get("license_spdx"), f"{path}.license_spdx", nonempty=True)
    _validate_string_list(result, mapping.get("secondary_ecosystems"), f"{path}.secondary_ecosystems")
    _validate_string_list(result, mapping.get("manifest_paths"), f"{path}.manifest_paths")
    _validate_string_list(result, mapping.get("lockfile_paths"), f"{path}.lockfile_paths")

    ecosystem = mapping.get("primary_ecosystem")
    if ecosystem not in ECOSYSTEMS:
        _diagnostic(result, f"{path}.primary_ecosystem", "must be javascript, python, or go")
    if not isinstance(mapping.get("is_monorepo"), bool):
        _diagnostic(result, f"{path}.is_monorepo", "must be a boolean")
    if not isinstance(mapping.get("has_dynamic_or_generated_code"), bool):
        _diagnostic(result, f"{path}.has_dynamic_or_generated_code", "must be a boolean")

    for evidence_name, enabled in (
        ("monorepo_evidence", mapping.get("is_monorepo") is True),
        ("dynamic_generated_evidence", mapping.get("has_dynamic_or_generated_code") is True),
    ):
        evidence_path = f"{path}.{evidence_name}"
        evidence = _require_mapping(result, mapping.get(evidence_name), evidence_path)
        if evidence is None:
            continue
        _require_fields(result, evidence, ("categories" if evidence_name.startswith("dynamic") else "markers", "paths"), evidence_path)
        if enabled:
            first_key = "categories" if evidence_name.startswith("dynamic") else "markers"
            _validate_string_list(result, evidence.get(first_key), f"{evidence_path}.{first_key}", nonempty=True)
            _validate_string_list(result, evidence.get("paths"), f"{evidence_path}.paths", nonempty=True)
        else:
            for key in ("categories", "markers", "paths", "lines"):
                if key in evidence:
                    _validate_string_list(result, evidence[key], f"{evidence_path}.{key}")

    ground_truth_ref = mapping.get("ground_truth_ref")
    label_path = _safe_local_ref(result, benchmark_root, ground_truth_ref, f"{path}.ground_truth_ref")
    if label_path is not None and not label_path.is_file():
        _diagnostic(result, f"{path}.ground_truth_ref", f"label file not found: {ground_truth_ref}")
    return dict(mapping)


def _validate_label_file(
    result: PreflightResult,
    label_path: Path,
    repository: Mapping[str, Any],
    repository_index: int,
) -> None:
    label_key = f"repositories[{repository_index}].ground_truth_ref"
    if not label_path.is_file():
        return
    label_file = _load_json(result, label_path, str(label_path))
    if label_file is None:
        return
    _require_fields(result, label_file, REQUIRED_LABEL_FILE_FIELDS, str(label_path))
    if label_file.get("repository_id") != repository.get("id"):
        _diagnostic(result, f"{label_path}.repository_id", "does not match its manifest repository id")
    if label_file.get("commit_sha") != repository.get("commit_sha"):
        _diagnostic(result, f"{label_path}.commit_sha", "does not match its manifest commit_sha")
    if not _is_nonempty_string(label_file.get("label_schema_version")):
        _diagnostic(result, f"{label_path}.label_schema_version", "must be a non-empty string")

    labels = label_file.get("labels")
    if not isinstance(labels, list):
        _diagnostic(result, f"{label_path}.labels", "must be a list of label objects")
        return
    result.labels_found += 1
    seen_label_ids: set[str] = set()
    for index, label in enumerate(labels):
        path = f"{label_path}.labels[{index}]"
        mapping = _require_mapping(result, label, path)
        if mapping is None:
            continue
        _require_fields(result, mapping, REQUIRED_LABEL_FIELDS, path)
        label_id = mapping.get("label_id")
        if not _is_nonempty_string(label_id):
            _diagnostic(result, f"{path}.label_id", "must be a unique non-empty string")
        elif label_id in seen_label_ids:
            _diagnostic(result, f"{path}.label_id", f"duplicate label id {label_id!r}")
        else:
            seen_label_ids.add(label_id)
        if mapping.get("repository_id") != repository.get("id"):
            _diagnostic(result, f"{path}.repository_id", "does not match its manifest repository id")
        if mapping.get("commit_sha") != repository.get("commit_sha"):
            _diagnostic(result, f"{path}.commit_sha", "does not match its manifest commit_sha")
        if mapping.get("finding_type") not in FINDING_TYPES:
            _diagnostic(result, f"{path}.finding_type", "is not in the documented finding vocabulary")
        status = mapping.get("status")
        if status not in LABEL_STATUSES:
            _diagnostic(result, f"{path}.status", "must be present, absent, unsupported, or not_assessable")
        if mapping.get("ecosystem") not in ECOSYSTEMS:
            _diagnostic(result, f"{path}.ecosystem", "must be javascript, python, or go")
        package = mapping.get("package")
        if package is not None and not _is_nonempty_string(package):
            _diagnostic(result, f"{path}.package", "must be a package name or null")
        source_file = mapping.get("source_file")
        _validate_relative_path(result, source_file, f"{path}.source_file", allow_null=status != "present")
        for field_name in ("manifest", "lockfile"):
            _validate_relative_path(
                result,
                mapping.get(field_name),
                f"{path}.{field_name}",
                allow_null=field_name == "lockfile",
            )
        for field_name in ("line", "column"):
            value = mapping.get(field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _diagnostic(result, f"{path}.{field_name}", "must be a positive integer")
        if not _is_nonempty_string(mapping.get("rationale")):
            _diagnostic(result, f"{path}.rationale", "must be a non-empty string")
        _validate_sha(result, mapping.get("evidence_sha256"), f"{path}.evidence_sha256", SHA256)


def validate_preflight(manifest_path: str | Path = "benchmarks/g2/manifest.yaml") -> PreflightResult:
    """Validate local G2 inputs and return a score-free READY/INCOMPLETE result."""

    manifest = Path(manifest_path)
    result = PreflightResult(status="INCOMPLETE", manifest=str(manifest))
    if not manifest.is_file():
        _diagnostic(result, "manifest", f"missing frozen manifest: {manifest}")
        return result

    document = _load_yaml(result, manifest)
    if document is None:
        return result
    _require_fields(result, document, REQUIRED_MANIFEST_FIELDS, "manifest")
    if document.get("schema_version") != "1.0":
        _diagnostic(result, "manifest.schema_version", "must be \"1.0\"")
    if document.get("status") != "complete":
        _diagnostic(result, "manifest.status", "must be \"complete\" for a frozen benchmark manifest")
    for field_name in ("benchmark_id", "owner"):
        if not _is_nonempty_string(document.get(field_name)):
            _diagnostic(result, f"manifest.{field_name}", "must be a non-empty string")
    _validate_timestamp(result, document.get("created_at_utc"), "manifest.created_at_utc")

    scanner = _require_mapping(result, document.get("scanner"), "manifest.scanner")
    if scanner is not None:
        _require_fields(result, scanner, REQUIRED_SCANNER_FIELDS, "manifest.scanner")
        _validate_url(result, scanner.get("repository"), "manifest.scanner.repository")
        _validate_sha(result, scanner.get("commit_sha"), "manifest.scanner.commit_sha", SHA40)
        for field_name in ("requirements_lock", "environment_ref"):
            _validate_relative_path(result, scanner.get(field_name), f"manifest.scanner.{field_name}")

    _validate_metadata_block(result, document.get("adjudication"), "manifest.adjudication", REQUIRED_ADJUDICATION_FIELDS)
    _validate_metadata_block(result, document.get("outputs"), "manifest.outputs", REQUIRED_OUTPUT_FIELDS)

    repositories = document.get("repositories")
    if not isinstance(repositories, list):
        _diagnostic(result, "manifest.repositories", "must be a list")
        return result
    result.repositories_found = len(repositories)
    if len(repositories) != EXPECTED_REPOSITORIES:
        _diagnostic(
            result,
            "manifest.repositories",
            f"expected exactly {EXPECTED_REPOSITORIES} repositories, found {len(repositories)}",
        )

    benchmark_root = manifest.parent
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    repositories_by_index: list[dict[str, Any] | None] = []
    for index, repository in enumerate(repositories):
        repositories_by_index.append(
            _validate_repository(result, repository, index, benchmark_root, seen_ids, seen_urls)
        )

    result.quota_counts = {
        ecosystem: sum(
            1
            for repository in repositories_by_index
            if repository and repository.get("primary_ecosystem") == ecosystem
        )
        for ecosystem in REQUIRED_ECOSYSTEM_QUOTAS
    }
    result.quota_counts["monorepo"] = sum(
        1 for repository in repositories_by_index if repository and repository.get("is_monorepo") is True
    )
    result.quota_counts["dynamic_or_generated"] = sum(
        1
        for repository in repositories_by_index
        if repository and repository.get("has_dynamic_or_generated_code") is True
    )
    for ecosystem, minimum in REQUIRED_ECOSYSTEM_QUOTAS.items():
        if result.quota_counts[ecosystem] < minimum:
            _diagnostic(result, "manifest.repositories", f"primary ecosystem quota {ecosystem}: need at least {minimum}, found {result.quota_counts[ecosystem]}")
    if result.quota_counts["monorepo"] < REQUIRED_MONOREPOS:
        _diagnostic(result, "manifest.repositories", f"monorepo quota: need at least {REQUIRED_MONOREPOS}, found {result.quota_counts['monorepo']}")
    if result.quota_counts["dynamic_or_generated"] < REQUIRED_DYNAMIC_REPOSITORIES:
        _diagnostic(result, "manifest.repositories", f"dynamic/generated quota: need at least {REQUIRED_DYNAMIC_REPOSITORIES}, found {result.quota_counts['dynamic_or_generated']}")

    for index, repository in enumerate(repositories_by_index):
        if repository is None:
            continue
        label_ref = repository.get("ground_truth_ref")
        label_path = _safe_local_ref(result, benchmark_root, label_ref, f"repositories[{index}].ground_truth_ref")
        if label_path is not None and label_path.is_file():
            _validate_label_file(result, label_path, repository, index)

    if not result.diagnostics:
        result.status = "READY"
    return result


def _print_human(result: PreflightResult) -> None:
    print(f"G2 BENCHMARK PREFLIGHT: {result.status}")
    print(f"Repositories: {result.repositories_found}/{result.repositories_expected}")
    print(f"Ground-truth label files: {result.labels_found}/{result.repositories_found}")
    if result.quota_counts:
        print("Quotas: " + ", ".join(f"{key}={value}" for key, value in result.quota_counts.items()))
    if result.diagnostics:
        print("Diagnostics:")
        for diagnostic in result.diagnostics:
            print("- " + diagnostic.render())
    print("No benchmark scores were calculated; READY is not a G2 pass.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline G2 benchmark preflight validator.")
    parser.add_argument("manifest", nargs="?", default="benchmarks/g2/manifest.yaml")
    parser.add_argument("--json", action="store_true", help="emit the score-free preflight result as JSON")
    args = parser.parse_args(argv)
    result = validate_preflight(args.manifest)
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_human(result)
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
