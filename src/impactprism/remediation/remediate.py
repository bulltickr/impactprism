from __future__ import annotations

from pathlib import Path

from .. import go_manifest as go_manifest_module
from .. import manifest as manifest_module
from ..python_manifest import is_python_repo, parse_python_manifest
from ..drift import analyze_repo
from . import patcher, pr
from .lockfile import LockfileUpdater
from .models import RemediationError, RemediationPlan
from .verify import verify_remediation

__all__ = ["remediate"]

_ROLLBACK_LOCKFILES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.sum",
)


def _capture_mutation_state(repo_dir: str, manifest_path: Path) -> dict[Path, bytes | None]:
    repo = Path(repo_dir).resolve()
    paths = {manifest_path.resolve()}
    paths.update(repo / name for name in _ROLLBACK_LOCKFILES)
    return {path: path.read_bytes() if path.is_file() else None for path in paths}


def _restore_mutation_state(state: dict[Path, bytes | None]) -> None:
    for path, content in state.items():
        if content is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _detect_ecosystem(repo_dir: str) -> str:
    repo = Path(repo_dir)
    if (repo / "package.json").is_file():
        return "npm"
    if (repo / "go.mod").is_file():
        return "go"
    if is_python_repo(repo):
        return "python"
    raise RemediationError("unsupported or missing ecosystem")


def _parse_manifest(repo_dir: str, ecosystem: str):
    if ecosystem == "go":
        return go_manifest_module.parse_go_manifest(repo_dir)
    if ecosystem == "npm":
        return manifest_module.parse_manifest(repo_dir)
    if ecosystem == "python":
        return parse_python_manifest(repo_dir)
    raise RemediationError(f"unsupported ecosystem: {ecosystem!r}")


def remediate(
    finding: dict,
    repo_dir: str,
    *,
    ecosystem: str = "auto",
    update_lockfile: bool = True,
    verify: bool = True,
    dry_run: bool = True,
    commit_sha: str | None = None,
    offline: bool = False,
    registry: str | None = None,
) -> RemediationPlan:
    if ecosystem == "auto":
        try:
            ecosystem = _detect_ecosystem(repo_dir)
        except RemediationError:
            raise
        except Exception as exc:
            raise RemediationError(f"unsupported or missing ecosystem: {exc}") from exc

    try:
        scan_before = analyze_repo(
            repo_dir, ecosystem=ecosystem, commit_sha=commit_sha
        ).as_dicts()
    except Exception as exc:
        raise RemediationError(f"failed to analyze repository: {exc}") from exc

    try:
        manifest = _parse_manifest(repo_dir, ecosystem)
        manifest_patch = patcher.build_manifest_patch(finding, manifest)
    except Exception as exc:
        raise RemediationError(f"failed to build manifest patch: {exc}") from exc

    if manifest_patch is None:
        raise RemediationError("finding is not remediable by manifest patch")

    if ecosystem == "python" and not dry_run:
        raise RemediationError(
            "Python remediation apply is not supported yet; use the proposed plan "
            "and apply a reviewed requirements/lockfile change manually."
        )

    rollback_state = (
        _capture_mutation_state(repo_dir, Path(manifest_patch.path))
        if not dry_run
        else {}
    )
    try:
        if not dry_run:
            patcher.apply_manifest_patch(repo_dir, manifest_patch)

        lockfile_plan = None
        if update_lockfile:
            updater = LockfileUpdater(dry_run=dry_run, offline=offline, registry=registry)
            lockfile_plan = updater.run(repo_dir, ecosystem, patch=manifest_patch)

        verification = None
        if verify:
            verification = verify_remediation(
                repo_dir,
                finding,
                ecosystem=ecosystem,
                scan_before=scan_before,
                commit_sha=commit_sha,
            )
    except RemediationError:
        if not dry_run:
            _restore_mutation_state(rollback_state)
        raise
    except Exception as exc:
        if not dry_run:
            _restore_mutation_state(rollback_state)
        raise RemediationError(f"failed to apply and verify remediation: {exc}") from exc

    base_plan = RemediationPlan(
        finding=finding,
        manifest_patch=manifest_patch,
        lockfile_plan=lockfile_plan,
        verification=verification,
        proposed_only=dry_run,
    )

    try:
        pr_description = pr.build_pr_description(base_plan)
        pr_proposal = pr.create_pr_proposal(repo_dir, base_plan)
    except Exception as exc:
        raise RemediationError(
            f"failed to build pull request description: {exc}"
        ) from exc

    return RemediationPlan(
        finding=finding,
        manifest_patch=manifest_patch,
        lockfile_plan=lockfile_plan,
        verification=verification,
        pr_description=pr_description,
        pr_proposal=pr_proposal,
        proposed_only=dry_run,
    )
