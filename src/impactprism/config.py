"""Strict, small configuration file support for local scans."""

from __future__ import annotations

from pathlib import Path

from .scope import normalize_excludes, normalize_roots

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


CONFIG_NAME = ".impactprism.toml"
_ALLOWED = {
    "scan": {"exclude", "roots", "baseline", "delta"},
    "outputs": {"report", "evidence", "sbom"},
    "policy": {"fail_on"},
}


def load_config(repo_path, explicit_path=None):
    """Load and validate the optional repository configuration."""

    repo_path = Path(repo_path).resolve()
    path = Path(explicit_path) if explicit_path is not None else repo_path / CONFIG_NAME
    if not path.is_absolute():
        path = (repo_path / path).resolve()
    if not path.is_file():
        if explicit_path is not None:
            raise ValueError("configuration file not found: " + str(path))
        return {"path": None}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError("unable to read configuration: " + str(error)) from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError("invalid TOML in configuration: " + str(error)) from error
    if not isinstance(data, dict):
        raise ValueError("configuration must contain a TOML table")
    unknown_sections = sorted(set(data) - set(_ALLOWED))
    if unknown_sections:
        raise ValueError("unsupported configuration section(s): " + ", ".join(unknown_sections))
    for section, values in data.items():
        if not isinstance(values, dict):
            raise ValueError("configuration section must be a table: " + section)
        unknown_keys = sorted(set(values) - _ALLOWED[section])
        if unknown_keys:
            raise ValueError(
                "unsupported configuration key(s) in ["
                + section
                + "]: "
                + ", ".join(unknown_keys)
            )

    scan = data.get("scan", {})
    if not isinstance(scan.get("exclude", []), list) or any(
        not isinstance(value, str) or not value for value in scan.get("exclude", [])
    ):
        raise ValueError("[scan].exclude must be a list of non-empty strings")
    try:
        normalize_excludes(scan.get("exclude", []))
    except ValueError as error:
        raise ValueError("[scan].exclude contains an unsafe path: " + str(error)) from error
    if not isinstance(scan.get("roots", []), list) or any(
        not isinstance(value, str) or not value for value in scan.get("roots", [])
    ):
        raise ValueError("[scan].roots must be a list of non-empty strings")
    if scan.get("roots", []):
        try:
            normalize_roots(scan.get("roots", []))
        except ValueError as error:
            raise ValueError("[scan].roots contains an unsafe path: " + str(error)) from error
    policy = data.get("policy", {})
    if policy.get("fail_on", "finding") not in ("finding", "never"):
        raise ValueError("[policy].fail_on must be 'finding' or 'never'")
    for section in ("scan", "outputs"):
        for key, value in data.get(section, {}).items():
            if key not in ("exclude", "roots") and (not isinstance(value, str) or not value):
                raise ValueError(f"[{section}].{key} must be a non-empty string")
    data["path"] = str(path)
    return data


def resolve_config_path(repo_path, value):
    """Resolve a config path relative to the repository root."""

    path = Path(value)
    return str(path if path.is_absolute() else Path(repo_path).resolve() / path)
