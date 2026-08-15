import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


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
IMPORT_PATTERN = re.compile(
    r"\bimport\s+(?:(?:[\s\S]*?)\sfrom\s+)?['\"]([^'\"]+)['\"]"
)
DYNAMIC_IMPORT_PATTERN = re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
REQUIRE_PATTERN = re.compile(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


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
    for group_name in ("dependencies", "devDependencies"):
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


def generate_sbom(repo_dir: str) -> dict:
    repo_path = Path(repo_dir).resolve()
    package_json = _load_json(repo_path / "package.json")
    declared = _declared_dependencies(package_json)
    lockfile = None
    for lockfile_name in ("package-lock.json", "npm-shrinkwrap.json"):
        lockfile_path = repo_path / lockfile_name
        if lockfile_path.is_file():
            lockfile = _load_json(lockfile_path)
            break

    components = []
    for name in sorted(declared):
        version = _resolved_version(name, declared[name], lockfile)
        purl = "pkg:npm/" + _encode_purl_name(name) + "@" + version
        components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": _utc_timestamp(),
            "tools": [
                {
                    "vendor": "impactprism",
                    "name": "impactprism-analysis",
                    "version": "0.1.0",
                }
            ],
            "component": {
                "type": "application",
                "name": _package_name(package_json),
                "version": _package_version(package_json),
            },
        },
        "components": components,
    }


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


def scan_imports(repo_dir: str) -> set:
    imported = set()
    for root, directories, files in os.walk(repo_dir):
        directories[:] = [
            directory
            for directory in directories
            if directory not in SKIPPED_DIRECTORIES and not directory.startswith(".")
        ]
        for filename in files:
            if filename.startswith(".") or Path(filename).suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            try:
                source = (Path(root) / filename).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in (IMPORT_PATTERN, DYNAMIC_IMPORT_PATTERN, REQUIRE_PATTERN):
                for match in pattern.finditer(source):
                    name = _normalize_name(match.group(1))
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
        imported = scan_imports(str(repo_path))
        report = _report(repo_path, package_json, declared, imported)
        if args.sbom:
            _write_json(args.sbom, generate_sbom(str(repo_path)))
        if args.report:
            _write_json(args.report, report)
        if args.json:
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
