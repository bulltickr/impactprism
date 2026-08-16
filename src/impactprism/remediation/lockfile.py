from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from .models import LockfilePlan, LockfilePlanResult, RemediationError
from .patcher import compute_lockfile_patch

__all__ = ["LockfileUpdater", "detect_npm_manager", "resolve_npm_command"]

_LOCKFILE_PRECEDENCE = (
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
)
_PACKAGE_MANAGER_PATTERN = re.compile(r"^\s*([^@\s]+)@(\S+)\s*$")


def _fingerprint(path):
    if path is None:
        return None
    target = Path(path)
    try:
        stat = target.stat()
    except OSError:
        return None
    try:
        content = target.read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(content).hexdigest()
    return (stat.st_size, stat.st_mtime_ns, digest)


def _write_patch(patch, repo_dir) -> None:
    repo_path = Path(repo_dir).resolve()
    patch_path = Path(patch.path).resolve()
    try:
        inside_repo = os.path.commonpath((str(repo_path), str(patch_path))) == str(repo_path)
    except ValueError:
        inside_repo = False
    if not inside_repo:
        raise RemediationError(f"Patch path escapes repository: {patch.path}")
    target = Path(patch.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patch.after, encoding="utf-8")


def _read_package_manager(repo_dir):
    """Parse the ``packageManager`` field of repo_dir/package.json.

    Returns ``(name, version)`` for the well-formed ``name@version`` form,
    otherwise ``None``.
    """
    package_path = Path(repo_dir) / "package.json"
    try:
        with package_path.open("r", encoding="utf-8") as package_file:
            data = json.load(package_file)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("packageManager")
    if not isinstance(raw, str):
        return None
    match = _PACKAGE_MANAGER_PATTERN.match(raw)
    if match is None:
        return None
    name, version = match.group(1), match.group(2)
    if not name or not version:
        return None
    return name, version


def _npm_lockfile(repo_dir) -> str:
    if (Path(repo_dir) / "npm-shrinkwrap.json").is_file():
        return "npm-shrinkwrap.json"
    return "package-lock.json"


def _yarn_is_berry(version: str) -> bool:
    if "+" in version:
        return True
    major = version.split(".", 1)[0]
    if major.isdigit():
        return int(major) >= 2
    return False


def _yarn_lockfile_is_berry(repo_dir) -> bool:
    lock_path = Path(repo_dir) / "yarn.lock"
    try:
        with lock_path.open("r", encoding="utf-8") as lockfile:
            for _index, line in zip(range(40), lockfile):
                if line.startswith("# yarn lockfile v1"):
                    return False
    except OSError:
        pass
    return True


def _yarn_is_berry_for_repo(repo_dir) -> bool:
    package_manager = _read_package_manager(repo_dir)
    if package_manager is not None and package_manager[0] == "yarn":
        return _yarn_is_berry(package_manager[1])
    return _yarn_lockfile_is_berry(repo_dir)


def detect_npm_manager(repo_dir):
    """Detect the authoritative npm-family package manager and lockfile.

    Returns ``(manager, lockfile_basename)``. The ``packageManager`` field wins;
    otherwise the strongest lockfile signal wins; an empty repo defaults to npm
    with ``package-lock.json``.
    """
    package_manager = _read_package_manager(repo_dir)
    if package_manager is not None:
        name, _version = package_manager
        if name == "npm":
            return name, _npm_lockfile(repo_dir)
        if name == "yarn":
            return name, "yarn.lock"
        if name == "pnpm":
            return name, "pnpm-lock.yaml"
    for lockfile_name in _LOCKFILE_PRECEDENCE:
        if (Path(repo_dir) / lockfile_name).is_file():
            if lockfile_name == "yarn.lock":
                return "yarn", lockfile_name
            if lockfile_name == "pnpm-lock.yaml":
                return "pnpm", lockfile_name
            return "npm", lockfile_name
    return "npm", "package-lock.json"


def resolve_npm_command(repo_dir, *, offline=False, registry=None):
    """Resolve ``(manager, lockfile_basename, args)`` for the npm ecosystem."""
    manager, lockfile_name = detect_npm_manager(repo_dir)
    if manager == "npm":
        args = ["install", "--no-audit", "--ignore-scripts", "--no-fund"]
    elif manager == "yarn":
        if _yarn_is_berry_for_repo(repo_dir):
            args = ["install", "--mode=update-lockfile", "--ignore-scripts"]
        else:
            args = ["install", "--ignore-scripts", "--non-interactive"]
    else:
        args = ["install", "--ignore-scripts"]
    if offline:
        args.append("--offline")
    if registry is not None:
        args.extend(["--registry", registry])
    return manager, lockfile_name, args


class LockfileUpdater:
    """Update a project lockfile, falling back to a deterministic patch offline."""

    def __init__(
        self,
        *,
        dry_run: bool = False,
        simulate: bool = False,
        timeout_seconds: int = 300,
        offline: bool = False,
        registry: str | None = None,
    ):
        self.dry_run = dry_run
        self.simulate = simulate
        self.timeout_seconds = timeout_seconds
        self.offline = offline
        self.registry = registry

    def _resolve(self, repo_dir: str, ecosystem: str):
        if ecosystem == "npm":
            manager, lockfile_name, args = resolve_npm_command(
                repo_dir, offline=self.offline, registry=self.registry
            )
            return manager, args, lockfile_name, None
        if ecosystem == "go":
            env_overrides = None
            if self.registry is not None:
                env_overrides = {"GOPROXY": self.registry, "GOSUMDB": "off"}
            elif self.offline:
                env_overrides = {"GOPROXY": "off", "GOSUMDB": "off"}
            return "go", ["mod", "tidy"], None, env_overrides
        if ecosystem == "python":
            # Keep the command explicit and side-effect scope predictable; in
            # dry-run/simulate mode no package manager is invoked.
            args = ["-m", "pip", "install", "--no-input"]
            if self.offline:
                args.append("--no-index")
            if self.registry is not None:
                args.extend(["--index-url", self.registry])
            return "python", args, None, None
        raise RemediationError(f"unsupported ecosystem: {ecosystem!r}")

    @staticmethod
    def _merged_env(overrides):
        if not overrides:
            return None
        env = dict(os.environ)
        env.update(overrides)
        return env

    def run(self, repo_dir: str, ecosystem: str, *, patch=None) -> LockfilePlanResult:
        command, args, lockfile_name, env_overrides = self._resolve(repo_dir, ecosystem)

        fallback_patch = None
        if patch is not None:
            try:
                fallback_patch = compute_lockfile_patch(
                    repo_dir, patch, ecosystem=ecosystem, lockfile=lockfile_name
                )
            except Exception:
                fallback_patch = None

        plan = LockfilePlan(
            command=command,
            args=list(args),
            cwd=Path(repo_dir),
            dry_run=self.dry_run,
            fallback_patch=fallback_patch,
            lockfile=lockfile_name,
            env=env_overrides,
        )

        command_text = " ".join(args) if args else command

        if self.dry_run or self.simulate:
            return LockfilePlanResult(
                command=command_text,
                returncode=0,
                stdout="",
                stderr="",
                patched=False,
                applied=fallback_patch,
            )

        before_fingerprint = _fingerprint(fallback_patch.path) if fallback_patch is not None else None

        run_kwargs = {
            "cwd": repo_dir,
            "capture_output": True,
            "text": True,
            "timeout": self.timeout_seconds,
            "shell": False,
        }
        merged_env = self._merged_env(env_overrides)
        if merged_env is not None:
            run_kwargs["env"] = merged_env

        try:
            completed = subprocess.run([command] + args, **run_kwargs)
        except subprocess.TimeoutExpired as exc:
            raise RemediationError(
                f"lockfile update timed out for ecosystem {ecosystem!r}"
            ) from exc
        except OSError as exc:
            raise RemediationError(f"failed to run {command!r}: {exc}") from exc

        if completed.returncode != 0:
            raise RemediationError(
                "lockfile update failed for ecosystem "
                f"{ecosystem!r}: {completed.stderr or '(no stderr)'}"
            )

        if fallback_patch is not None and _fingerprint(fallback_patch.path) == before_fingerprint:
            _write_patch(fallback_patch, repo_dir)
            return LockfilePlanResult(
                command=command_text,
                returncode=0,
                stdout=completed.stdout,
                stderr=completed.stderr,
                patched=True,
                applied=fallback_patch,
            )

        return LockfilePlanResult(
            command=command_text,
            returncode=0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            patched=True,
            applied=None,
        )
