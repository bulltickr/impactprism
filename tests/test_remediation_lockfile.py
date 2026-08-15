import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import impactprism.remediation.lockfile as lockfile_module
from impactprism.remediation.lockfile import (
    LockfileUpdater,
    detect_npm_manager,
    resolve_npm_command,
)
from impactprism.remediation.models import LockfilePlan, PatchSpec, PatchTarget, RemediationError

NPM_ARGS = ["install", "--no-audit", "--ignore-scripts", "--no-fund"]
YARN_CLASSIC_ARGS = ["install", "--ignore-scripts", "--non-interactive"]
YARN_BERRY_ARGS = ["install", "--mode=update-lockfile", "--ignore-scripts"]
PNPM_ARGS = ["install", "--ignore-scripts"]


def completed(code, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


def fallback_patch(repo, after="patched-lockfile"):
    return PatchSpec(
        path=str(repo / "package-lock.json"),
        target=PatchTarget.LOCKFILE,
        after=after,
        before="{}",
        package="leftpad",
        version="1.3.0",
        kind="dependencies",
    )


def write_file(repo, name, content):
    path = repo / name
    path.write_text(content, encoding="utf-8")
    return path


def capture_plan(monkeypatch):
    captured = []

    class CapturingPlan(LockfilePlan):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured.append(self)

    monkeypatch.setattr(lockfile_module, "LockfilePlan", CapturingPlan)
    return captured


def test_npm_command_and_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = LockfileUpdater().run(str(repo), "npm")

    assert calls["cmd"] == ["npm", "install", "--no-audit", "--ignore-scripts", "--no-fund"]
    assert calls["kwargs"]["cwd"] == str(repo)
    assert calls["kwargs"]["capture_output"] is True
    assert calls["kwargs"]["text"] is True
    assert calls["kwargs"].get("shell") is not True
    assert result.returncode == 0
    assert result.patched is True
    assert result.applied is None


@pytest.mark.parametrize(
    "seed,expected_manager,expected_lockfile,expected_cmd",
    [
        (
            {"package-lock.json": "{}"},
            "npm",
            "package-lock.json",
            ["npm"] + NPM_ARGS,
        ),
        (
            {"yarn.lock": "# yarn lockfile v1\n"},
            "yarn",
            "yarn.lock",
            ["yarn"] + YARN_CLASSIC_ARGS,
        ),
        (
            {"yarn.lock": "__metadata:\n  version: 6\n"},
            "yarn",
            "yarn.lock",
            ["yarn"] + YARN_BERRY_ARGS,
        ),
        (
            {"pnpm-lock.yaml": "lockfileVersion: '9.0'\n"},
            "pnpm",
            "pnpm-lock.yaml",
            ["pnpm"] + PNPM_ARGS,
        ),
        (
            {
                "package.json": '{"packageManager": "yarn@3.6.4"}',
                "package-lock.json": "{}",
            },
            "yarn",
            "yarn.lock",
            ["yarn"] + YARN_BERRY_ARGS,
        ),
        (
            {
                "package.json": '{"packageManager": "pnpm@9.0.0"}',
                "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            },
            "pnpm",
            "pnpm-lock.yaml",
            ["pnpm"] + PNPM_ARGS,
        ),
        (
            {
                "package.json": '{"packageManager": "npm@10.5.0"}',
                "npm-shrinkwrap.json": "{}",
                "package-lock.json": "{}",
            },
            "npm",
            "npm-shrinkwrap.json",
            ["npm"] + NPM_ARGS,
        ),
    ],
)
def test_manager_detection_and_argv(
    tmp_path, monkeypatch, seed, expected_manager, expected_lockfile, expected_cmd
):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, content in seed.items():
        write_file(repo, name, content)
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    captured = capture_plan(monkeypatch)

    result = LockfileUpdater().run(str(repo), "npm")

    assert detect_npm_manager(str(repo)) == (expected_manager, expected_lockfile)
    assert resolve_npm_command(str(repo)) == (expected_manager, expected_lockfile, expected_cmd[1:])
    assert calls["cmd"] == expected_cmd
    assert calls["kwargs"]["cwd"] == str(repo)
    assert calls["kwargs"].get("shell") is not True
    assert captured[0].lockfile == expected_lockfile
    assert result.returncode == 0
    assert result.patched is True


@pytest.mark.parametrize(
    "offline,registry,expected_args",
    [
        (False, None, ["npm"] + NPM_ARGS),
        (True, None, ["npm"] + NPM_ARGS + ["--offline"]),
        (False, "https://reg.example.com", ["npm"] + NPM_ARGS + ["--registry", "https://reg.example.com"]),
        (True, "https://reg.example.com", ["npm"] + NPM_ARGS + ["--offline", "--registry", "https://reg.example.com"]),
    ],
)
def test_npm_offline_and_registry_argv(tmp_path, monkeypatch, offline, registry, expected_args):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    LockfileUpdater(offline=offline, registry=registry).run(str(repo), "npm")

    assert calls["cmd"] == expected_args
    assert calls["kwargs"].get("shell") is not True


def test_go_command(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = LockfileUpdater().run(str(repo), "go")

    assert calls["cmd"] == ["go", "mod", "tidy"]
    assert calls["kwargs"].get("shell") is not True
    assert calls["kwargs"].get("env") is None
    assert result.returncode == 0
    assert result.patched is True


def test_go_offline_sets_goproxy_off(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    captured = capture_plan(monkeypatch)

    result = LockfileUpdater(offline=True).run(str(repo), "go")

    assert calls["cmd"] == ["go", "mod", "tidy"]
    assert calls["kwargs"]["env"]["GOPROXY"] == "off"
    assert calls["kwargs"]["env"]["GOSUMDB"] == "off"
    assert captured[0].lockfile is None
    assert captured[0].env == {"GOPROXY": "off", "GOSUMDB": "off"}
    assert result.returncode == 0


def test_go_registry_sets_goproxy_proxy(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    LockfileUpdater(registry="https://proxy.example.com").run(str(repo), "go")

    assert calls["cmd"] == ["go", "mod", "tidy"]
    assert calls["kwargs"]["env"]["GOPROXY"] == "https://proxy.example.com"
    assert calls["kwargs"]["env"]["GOSUMDB"] == "off"


def test_plan_exposes_lockfile_and_env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(cmd, *args, **kwargs):
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    captured = capture_plan(monkeypatch)

    LockfileUpdater(offline=True).run(str(repo), "go")
    assert captured[0].lockfile is None
    assert captured[0].env == {"GOPROXY": "off", "GOSUMDB": "off"}

    captured.clear()
    LockfileUpdater().run(str(repo), "npm")
    assert captured[0].lockfile == "package-lock.json"
    assert captured[0].env is None


def test_lockfile_plan_as_dict_includes_lockfile_and_env():
    plan = LockfilePlan(
        command="yarn",
        args=["install"],
        cwd="repo",
        lockfile="yarn.lock",
        env={"GOPROXY": "off"},
    )
    as_dict = plan.as_dict()
    assert as_dict["lockfile"] == "yarn.lock"
    assert as_dict["env"] == {"GOPROXY": "off"}


def test_dry_run_never_executes(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("subprocess must not run during dry-run")

    monkeypatch.setattr(subprocess, "run", fail)

    result = LockfileUpdater(dry_run=True).run(str(tmp_path), "npm")

    assert result.returncode == 0
    assert result.patched is False
    assert result.applied is None


def test_simulate_never_executes(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("subprocess must not run during simulate")

    monkeypatch.setattr(subprocess, "run", fail)

    result = LockfileUpdater(simulate=True).run(str(tmp_path), "npm")

    assert result.returncode == 0
    assert result.patched is False
    assert result.applied is None


def test_dry_run_never_writes_filesystem(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    lock_path = repo / "package-lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    patch = fallback_patch(repo)

    monkeypatch.setattr(
        lockfile_module,
        "compute_lockfile_patch",
        lambda repo_dir, patch_arg, ecosystem=None, lockfile=None: patch,
    )

    def fail(*args, **kwargs):
        raise AssertionError("subprocess must not run during dry-run")

    monkeypatch.setattr(subprocess, "run", fail)

    result = LockfileUpdater(dry_run=True).run(str(repo), "npm", patch=patch)

    assert result.applied is patch
    assert result.patched is False
    assert lock_path.read_text(encoding="utf-8") == "{}"


def test_nonzero_returncode_raises(tmp_path, monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        return completed(1, stderr="boom: registry unreachable")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RemediationError, match="registry unreachable"):
        LockfileUpdater().run(str(tmp_path), "npm")


def test_offline_fallback_writes_lockfile(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    lock_path = repo / "package-lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    patch = fallback_patch(repo)

    monkeypatch.setattr(
        lockfile_module,
        "compute_lockfile_patch",
        lambda repo_dir, patch_arg, ecosystem=None, lockfile=None: patch,
    )

    def fake_run(cmd, *args, **kwargs):
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = LockfileUpdater().run(str(repo), "npm", patch=patch)

    assert result.patched is True
    assert result.applied is patch
    assert lock_path.read_text(encoding="utf-8") == patch.after


def test_modified_lockfile_skips_fallback(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    lock_path = repo / "package-lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    patch = fallback_patch(repo)

    monkeypatch.setattr(
        lockfile_module,
        "compute_lockfile_patch",
        lambda repo_dir, patch_arg, ecosystem=None, lockfile=None: patch,
    )

    def fake_run(cmd, *args, **kwargs):
        lock_path.write_text("written by npm", encoding="utf-8")
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = LockfileUpdater().run(str(repo), "npm", patch=patch)

    assert result.patched is True
    assert result.applied is None
    assert lock_path.read_text(encoding="utf-8") == "written by npm"


def test_fallback_writes_only_authoritative_lockfile(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    package_lock = write_file(repo, "package-lock.json", "{}")
    yarn_lock = write_file(repo, "yarn.lock", "# yarn lockfile v1\n")
    patch = PatchSpec(
        path=str(repo / "yarn.lock"),
        target=PatchTarget.LOCKFILE,
        after="patched-yarn-lock",
        before="# yarn lockfile v1\n",
        package="leftpad",
        version="1.3.0",
        kind="dependencies",
    )

    monkeypatch.setattr(
        lockfile_module,
        "compute_lockfile_patch",
        lambda repo_dir, patch_arg, ecosystem=None, lockfile=None: patch,
    )

    def fake_run(cmd, *args, **kwargs):
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert detect_npm_manager(str(repo)) == ("yarn", "yarn.lock")
    result = LockfileUpdater().run(str(repo), "npm", patch=patch)

    assert result.patched is True
    assert result.applied is patch
    assert package_lock.read_bytes() == b"{}"
    assert yarn_lock.read_text(encoding="utf-8") == patch.after


def test_unsupported_ecosystem_raises(tmp_path):
    with pytest.raises(RemediationError, match="unsupported ecosystem"):
        LockfileUpdater(dry_run=True).run(str(tmp_path), "pip")


def test_symlink_escape_rejects_fallback_write(tmp_path, monkeypatch):
    sentinel = tmp_path / "sentinel.json"
    sentinel.write_bytes(b"SENTINEL")
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        os.symlink(str(sentinel), str(repo / "package-lock.json"))
    except OSError:
        pytest.skip("symlinks not available")
    patch = PatchSpec(
        path=str(repo / "package-lock.json"),
        target=PatchTarget.LOCKFILE,
        after="patched",
        before="",
        package="leftpad",
        version="1.3.0",
        kind="dependencies",
    )

    monkeypatch.setattr(
        lockfile_module,
        "compute_lockfile_patch",
        lambda repo_dir, patch_arg, ecosystem=None, lockfile=None: patch,
    )

    def fake_run(cmd, *args, **kwargs):
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RemediationError):
        LockfileUpdater().run(str(repo), "npm", patch=patch)
    assert sentinel.read_bytes() == b"SENTINEL"


def test_escape_rejects_fallback_write(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = repo / ".." / "outside.json"
    patch = PatchSpec(
        path=str(outside),
        target=PatchTarget.LOCKFILE,
        after="patched",
        before="",
        package="leftpad",
        version="1.3.0",
        kind="dependencies",
    )

    monkeypatch.setattr(
        lockfile_module,
        "compute_lockfile_patch",
        lambda repo_dir, patch_arg, ecosystem=None, lockfile=None: patch,
    )

    def fake_run(cmd, *args, **kwargs):
        return completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RemediationError):
        LockfileUpdater().run(str(repo), "npm", patch=patch)
    assert not outside.exists()
