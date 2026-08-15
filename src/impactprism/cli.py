import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from . import go_imports
from .analysis import generate_sbom, main as analysis_main
from .drift import FindingType, analyze_repo
from .evidence import main as evidence_main
from .cra_clauses import main as cra_clauses_main


DEFAULT_SCAN_EXCLUDES = {
    "tests",
    "fixtures",
    "demo",
    "node_modules",
    "build",
    "dist",
    ".git",
    ".cache",
    "coverage",
    "public",
}


def _write_json(path, value):
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def _load_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _detect_ecosystem(repo_path):
    if (repo_path / "package.json").is_file():
        return "npm"
    if (repo_path / "go.mod").is_file():
        return "go"
    return None


def _bucket_packages(findings, finding_type):
    return sorted(
        {
            finding.package
            for finding in findings
            if finding.finding_type == finding_type and finding.package is not None
        }
    )


def _classifier_report(repo_path):
    try:
        drift_report = analyze_repo(str(repo_path), ecosystem="auto")
    except Exception as error:
        print("error: " + str(error), file=sys.stderr)
        return None
    scanner_errors = [
        finding
        for finding in drift_report.findings
        if finding.finding_type == FindingType.SCANNER_ERROR
    ]
    if scanner_errors:
        message = scanner_errors[0].explanation or "dependency scan failed"
        print("error: " + message, file=sys.stderr)
        return None
    return drift_report


def _go_report(repo_path, classifier):
    graph = go_imports.build_import_graph(repo_path)
    main_module = getattr(graph.manifest, "main_module", None)
    declared = sorted(
        {
            entry.module_path
            for entry in getattr(graph.manifest, "modules", [])
            if entry.module_path != main_module
            and getattr(entry, "source", None) in (None, "go.mod", "go.work")
        }
    )
    imported = sorted(
        {
            module_path
            for module_path, usage in (getattr(graph, "module_usage", {}) or {}).items()
            if getattr(usage, "used", False)
        }
    )
    findings = list(classifier.findings)
    undeclared = sorted(
        set(_bucket_packages(findings, FindingType.UNDECLARED_DIRECT_USE))
        | set(
            _bucket_packages(
                findings, FindingType.DIRECT_DEPENDENCY_USED_TRANSITIVELY
            )
        )
    )
    return {
        "repo": str(repo_path),
        "package_name": main_module or "unknown",
        "package_version": "0.0.0",
        "declared": declared,
        "imported": imported,
        "drift": _bucket_packages(findings, FindingType.DECLARED_UNUSED_CANDIDATE),
        "undeclared": undeclared,
        "scope-mismatch": _bucket_packages(findings, FindingType.SCOPE_MISMATCH),
        "ecosystem": "go",
        "sbom": None,
    }


def _run_analyze(args):
    delegated = [args.repo_dir]
    if args.sbom is not None:
        delegated.extend(["--sbom", args.sbom])
    if args.report is not None:
        delegated.extend(["--report", args.report])
    if args.json:
        delegated.append("--json")
    return analysis_main(delegated)


def _run_evidence(args):
    delegated = [args.scan_report]
    if hasattr(args, "markdown"):
        delegated.extend(["--markdown", args.markdown])
    if hasattr(args, "json"):
        delegated.extend(["--json", args.json])
    if args.stdout:
        delegated.append("--stdout")
    return evidence_main(delegated)


def _run_clauses(args):
    return cra_clauses_main([args.path] if args.path is not None else [])


def _run_scan(args):
    excludes = sorted(DEFAULT_SCAN_EXCLUDES | set(args.exclude or []))
    repo_path = Path(args.repo).resolve()
    if not repo_path.is_dir():
        print("error: repository directory not found: " + str(repo_path), file=sys.stderr)
        return 2
    ecosystem = _detect_ecosystem(repo_path)
    if ecosystem is None:
        print(
            "error: no package.json or go.mod found in " + str(repo_path),
            file=sys.stderr,
        )
        return 2

    report_path = args.report
    temp_report = None
    try:
        if report_path is None:
            fd, report_path = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            temp_report = report_path

        if ecosystem == "npm":
            analyze_argv = [args.repo]
            for name in excludes:
                analyze_argv.extend(["--exclude", name])
            if args.sbom is not None:
                analyze_argv.extend(["--sbom", args.sbom])
            analyze_argv.extend(["--report", report_path])
            with contextlib.redirect_stdout(io.StringIO() if args.json else sys.stdout):
                analysis_rc = analysis_main(analyze_argv)
            if analysis_rc == 2:
                return 2
            report = _load_json(report_path)
            classifier = _classifier_report(repo_path)
            if classifier is None:
                return 2
            report["scope-mismatch"] = _bucket_packages(
                classifier.findings, FindingType.SCOPE_MISMATCH
            )
            report["ecosystem"] = ecosystem
            report["sbom"] = generate_sbom(str(repo_path))
        else:
            classifier = _classifier_report(repo_path)
            if classifier is None:
                return 2
            report = _go_report(repo_path, classifier)
            if args.sbom is not None:
                _write_json(args.sbom, None)

        _write_json(report_path, report)

        evidence_argv = [report_path]
        if args.evidence is not None:
            evidence_argv.extend(["--json", args.evidence])
        if evidence_main(evidence_argv) == 2:
            return 2

        if args.json:
            json.dump(report, sys.stdout, indent=2)
            print()

        if report["drift"] or report["undeclared"] or report["scope-mismatch"]:
            return 1
        return 0
    except Exception as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    finally:
        if temp_report is not None:
            try:
                os.remove(temp_report)
            except OSError:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ImpactPrism command line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="analyze a repository")
    analyze.add_argument("repo_dir")
    analyze.add_argument("--sbom", metavar="PATH")
    analyze.add_argument("--report", metavar="PATH")
    analyze.add_argument("--json", action="store_true")
    analyze.set_defaults(func=_run_analyze)

    evidence = subparsers.add_parser("evidence", help="generate an evidence pack")
    evidence.add_argument("scan_report")
    evidence.add_argument(
        "--markdown",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="write Markdown evidence (default: evidence.md)",
    )
    evidence.add_argument(
        "--json",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="write JSON evidence (default: evidence.json)",
    )
    evidence.add_argument("--stdout", action="store_true")
    evidence.set_defaults(func=_run_evidence)

    clauses = subparsers.add_parser("clauses", help="print the CRA clause map")
    clauses.add_argument("path", nargs="?", default=None)
    clauses.set_defaults(func=_run_clauses)

    scan = subparsers.add_parser(
        "scan", help="analyze a repository and generate an evidence pack in one shot"
    )
    scan.add_argument("repo")
    scan.add_argument("--exclude", action="append", metavar="PAT", default=None)
    scan.add_argument("--sbom", metavar="PATH")
    scan.add_argument("--report", metavar="PATH")
    scan.add_argument("--evidence", metavar="PATH")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=_run_scan)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
