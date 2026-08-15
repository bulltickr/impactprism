import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .sbom.cyclonedx_builder import build_cyclonedx_sbom
from .imports import scan_imports as _ast_scan_imports
from .manifest import LockfileParseError, parse_lockfile


SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
SKIPPED_DIRECTORIES = {"node_modules", "build", "dist", "coverage", "public"}
BUILTIN_MODULES = {
    "fs", "path", "http", "https", "os", "crypto", "stream", "util", "events",
    "child_process", "url", "buffer", "querystring", "zlib", "assert",
    "string_decoder", "tty", "net", "dns", "dgram", "cluster", "module",
    "process", "timers", "vm", "worker_threads", "perf_hooks", "readline",
    "readline/promises", "repl", "constants", "domain", "inspector", "punycode",
    "async_hooks", "v8", "wasi", "test", "node:test",
}


def _load_json(path):
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON object expected in " + str(path))
    return value


def _package_name(package_json):
    value = package_json.get("name")
    return str(value) if value else "unknown"


def _package_version(package_json):
    value = package_json.get("version")
    return str(value) if value else "0.0.0"


def _declared_dependencies(package_json):
    declared = {}
    for group_name in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        group = package_json.get(group_name, {})
        if isinstance(group, dict):
            declared.update(
                (str(name), "" if version is None else str(version))
                for name, version in group.items()
            )
    return declared


def _lockfile_version(lockfile, name):
    if not isinstance(lockfile, dict):
        return None
    resolved_versions = lockfile.get("_resolved_versions")
    if isinstance(resolved_versions, dict):
        version = resolved_versions.get(name)
        if version is not None:
            return str(version)
    packages = lockfile.get("packages")
    if isinstance(packages, dict):
        entry = packages.get("node_modules/" + name)
        if isinstance(entry, dict) and entry.get("version") is not None:
            return str(entry["version"])
        entry = packages.get(name)
        if isinstance(entry, dict) and entry.get("version") is not None:
            return str(entry["version"])
    dependencies = lockfile.get("dependencies")
    if isinstance(dependencies, dict):
        entry = dependencies.get(name)
        if isinstance(entry, dict) and entry.get("version") is not None:
            return str(entry["version"])
    return None


def _resolved_version(name, declared_version, lockfile):
    version = _lockfile_version(lockfile, name)
    return version if version is not None else declared_version or "0.0.0"


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _encode_purl_name(name):
    encoded = []
    for byte in name.encode("utf-8"):
        character = chr(byte)
        if (character.isalnum() and byte < 128) or character in "-._~":
            encoded.append(character)
        else:
            encoded.append("%%%02X" % byte)
    return "".join(encoded)


def _dependency_groups(package_json):
    for group_name in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        group = package_json.get(group_name)
        if not isinstance(group, dict):
            continue
        for name, version in group.items():
            yield group_name, str(name), "" if version is None else str(version)


def _lockfile_integrity(lockfile, name):
    if not isinstance(lockfile, dict):
        return []
    packages = lockfile.get("packages")
    if not isinstance(packages, dict):
        return []
    entry = packages.get("node_modules/" + name)
    if not isinstance(entry, dict):
        return []
    integrity = entry.get("integrity")
    if not isinstance(integrity, str) or not integrity:
        return []
    content = integrity[len("sha512-"):] if integrity.startswith("sha512-") else integrity
    return [{"alg": "SHA-512", "content": content}]


def _normalized_components(package_json, lockfile):
    components = []
    seen = set()
    for group_name, name, declared_version in _dependency_groups(package_json):
        if name in seen:
            continue
        seen.add(name)
        version = _resolved_version(name, declared_version, lockfile)
        purl = "pkg:npm/" + _encode_purl_name(name) + "@" + version
        components.append(
            {
                "name": name,
                "version": version,
                "purl": purl,
                "scope": "required" if group_name == "dependencies" else "optional",
                "direct": True,
                "transitive": False,
                "hashes": _lockfile_integrity(lockfile, name),
                "ecosystem": "npm",
            }
        )
    return components


def generate_sbom(repo_dir: str) -> dict:
    repo_path = Path(repo_dir).resolve()
    package_json = _load_json(repo_path / "package.json")
    lockfile = None
    for lockfile_name in ("package-lock.json", "npm-shrinkwrap.json"):
        lockfile_path = repo_path / lockfile_name
        if lockfile_path.is_file():
            lockfile = _load_json(lockfile_path)
            break
    if lockfile is None:
        try:
            parsed = parse_lockfile(repo_path)
        except LockfileParseError:
            parsed = None
        if parsed is not None and parsed.kind != "npm":
            lockfile = {"_resolved_versions": parsed.resolved_versions}

    components = _normalized_components(package_json, lockfile)
    metadata = {
        "name": _package_name(package_json),
        "version": _package_version(package_json),
        "tool_name": "impactprism-cyclonedx",
        "tool_version": "0.1.0",
        "timestamp": _utc_timestamp(),
    }
    return build_cyclonedx_sbom(components, metadata=metadata)


def _normalize_name(specifier):
    specifier = str(specifier).strip()
    if not specifier or specifier.startswith(("./", "../", "/", "node:")):
        return None
    parts = specifier.split("/")
    if specifier.startswith("@"):
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return None
        name = parts[0] + "/" + parts[1]
    else:
        name = parts[0]
    if name in BUILTIN_MODULES:
        return None
    return name


def scan_imports(repo_dir: str, excludes=None) -> set:
    imported = set()
    for records in _ast_scan_imports(repo_dir, exclude=excludes).values():
        for record in records:
            name = _normalize_name(record.specifier)
            if name is not None:
                imported.add(name)
    return imported


def _normalized_names(values):
    normalized = set()
    for value in values:
        name = _normalize_name(value)
        if name is not None:
            normalized.add(name)
    return normalized


def cross_check(declared: set, imported: set) -> dict:
    declared = _normalized_names(declared)
    imported = _normalized_names(imported)
    return {
        "drift": sorted(declared - imported),
        "undeclared": sorted(imported - declared),
        "declared_count": len(declared),
        "imported_count": len(imported),
        "matched_count": len(declared & imported),
    }


def _write_json(path, value):
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def _report(repo_path, package_json, declared, imported):
    declared = _normalized_names(declared)
    imported = _normalized_names(imported)
    findings = cross_check(declared, imported)
    return {
        "repo": str(repo_path),
        "package_name": _package_name(package_json),
        "package_version": _package_version(package_json),
        "declared": sorted(declared),
        "imported": sorted(imported),
        "drift": findings["drift"],
        "undeclared": findings["undeclared"],
    }


def _print_findings(title, entries):
    print(title + ": " + str(len(entries)))
    if not entries:
        print("  - none")
        return
    shown = entries[:50]
    for entry in shown:
        print("  " + entry)
    remaining = len(entries) - len(shown)
    if remaining:
        print("  ... and " + str(remaining) + " more")


def _print_summary(report):
    print("Repository: " + report["repo"])
    print("Package: " + report["package_name"] + "@" + report["package_version"])
    print("Declared dependencies: " + str(len(report["declared"])))
    print("Imported packages: " + str(len(report["imported"])))
    _print_findings("Drift (declared but unused)", report["drift"])
    _print_findings("Undeclared dependencies", report["undeclared"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Analyze JavaScript and TypeScript dependencies.")
    parser.add_argument("repo_dir")
    parser.add_argument("--sbom", metavar="PATH")
    parser.add_argument("--report", metavar="PATH")
    parser.add_argument(
        "--exclude",
        action="append",
        metavar="PAT",
        default=None,
        help="skip directories with this name (repeatable)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_path = Path(args.repo_dir).resolve()
    if not repo_path.is_dir():
        print("error: repository directory not found: " + str(repo_path), file=sys.stderr)
        return 2
    package_path = repo_path / "package.json"
    if not package_path.is_file():
        print("error: package.json not found: " + str(package_path), file=sys.stderr)
        return 2

    try:
        package_json = _load_json(package_path)
        declared = set(_declared_dependencies(package_json))
        excludes = set(args.exclude) if args.exclude else None
        imported = scan_imports(str(repo_path), excludes=excludes)
        report = _report(repo_path, package_json, declared, imported)
        sbom = generate_sbom(str(repo_path))
        if args.sbom:
            _write_json(args.sbom, sbom)
        if args.report:
            _write_json(args.report, report)
        if args.json:
            report["sbom"] = sbom
            json.dump(report, sys.stdout, indent=2)
            print()
        else:
            _print_summary(report)
    except Exception as error:
        print("error: " + str(error), file=sys.stderr)
        return 2

    return 1 if report["drift"] or report["undeclared"] else 0


if __name__ == "__main__":
    sys.exit(main())
