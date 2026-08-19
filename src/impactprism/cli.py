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
from .baseline import compare_reports, delta_exit_code, load_report
from .drift import FindingType, analyze_repo
from .evidence import main as evidence_main
from .doctor import main as doctor_main
from .config import load_config, resolve_config_path
from .cra_clauses import main as cra_clauses_main
from .python_manifest import is_python_repo
from .reporting import build_scan_report, scan_exit_code
from .remediation.models import RemediationError
from .remediation.remediate import remediate
from .version import __version__


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
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
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
    if is_python_repo(repo_path):
        return "python"
    return None


def _bucket_packages(findings, finding_type):
    return sorted(
        {
            finding.package
            for finding in findings
            if finding.finding_type == finding_type and finding.package is not None
        }
    )


def _emit_cli_error(message, *, json_mode=False, kind="input-error"):
    """Emit one stable CLI error without contaminating JSON stdout."""

    if json_mode:
        json.dump(
            {
                "schema_version": 1,
                "generator": "impactprism-cli",
                "error": {"kind": kind, "message": str(message)},
                "exit_code": 2,
            },
            sys.stdout,
            indent=2,
        )
        print()
    else:
        print("error: " + str(message), file=sys.stderr)
    return 2


def _has_scanner_error(report):
    return any(
        finding.finding_type == FindingType.SCANNER_ERROR
        for finding in report.findings
    )


def _classifier_report(repo_path, excludes=None):
    return analyze_repo(
        str(repo_path), ecosystem="auto", exclude=set(excludes or [])
    )


def _scanner_error_message(report):
    for finding in report.findings:
        if finding.finding_type == FindingType.SCANNER_ERROR:
            return finding.explanation or "dependency scan failed"
    return None


def _go_report(repo_path, classifier, sbom=None, excludes=None):
    graph = go_imports.build_import_graph(repo_path, exclude=set(excludes or []))
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
    return build_scan_report(
        repo=str(repo_path),
        ecosystem="go",
        findings=classifier.as_dicts(),
        package_name=main_module or "unknown",
        package_version="0.0.0",
        declared=declared,
        imported=imported,
        sbom=sbom,
    )


def _run_analyze(args):
    repo_path = Path(args.repo_dir).resolve()
    if not repo_path.is_dir():
        return _emit_cli_error(
            "repository directory not found: " + str(repo_path),
            json_mode=args.json,
        )
    ecosystem = _detect_ecosystem(repo_path)
    if ecosystem is None:
        return _emit_cli_error(
            "no supported ecosystem manifest found in " + str(repo_path),
            json_mode=args.json,
        )

    excludes = set(args.exclude or [])
    temp_report = None
    try:
        legacy_report = {}
        if ecosystem in ("npm", "python"):
            fd, temp_report = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            delegated = [args.repo_dir, "--report", temp_report]
            for name in sorted(excludes):
                delegated.extend(["--exclude", name])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                analysis_rc = analysis_main(delegated)
            if analysis_rc != 2 and Path(temp_report).is_file():
                legacy_report = _load_json(temp_report)

        classifier = _classifier_report(repo_path, excludes)
        scanner_error = _has_scanner_error(classifier)
        sbom = None if scanner_error else generate_sbom(str(repo_path))
        if ecosystem == "go" and not scanner_error:
            report = _go_report(repo_path, classifier, sbom=sbom, excludes=excludes)
        else:
            report = build_scan_report(
                repo=str(repo_path),
                ecosystem=ecosystem,
                findings=classifier.as_dicts(),
                package_name=legacy_report.get("package_name", "unknown"),
                package_version=legacy_report.get("package_version", "0.0.0"),
                declared=legacy_report.get("declared", []),
                imported=legacy_report.get("imported", []),
                sbom=sbom,
            )

        if args.report is not None:
            _write_json(args.report, report)
        if args.sbom is not None and sbom is not None:
            _write_json(args.sbom, sbom)
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            print()
        else:
            scanner_error_message = _scanner_error_message(classifier)
            if scanner_error_message:
                print("error: " + scanner_error_message, file=sys.stderr)
            else:
                print("Repository: " + report["repo"])
                print("Package: " + report["package_name"] + "@" + report["package_version"])
                print("Findings: " + str(report["counts"]["total"]))
        return scan_exit_code(report)
    except Exception as error:
        return _emit_cli_error(str(error), json_mode=args.json, kind="scanner-error")
    finally:
        if temp_report is not None:
            try:
                os.remove(temp_report)
            except OSError:
                pass


def _run_evidence(args):
    delegated = [args.scan_report]
    if hasattr(args, "markdown"):
        delegated.extend(["--markdown", args.markdown])
    if hasattr(args, "json"):
        delegated.extend(["--json", args.json])
    if args.stdout:
        delegated.append("--stdout")
    return evidence_main(delegated)


def _run_doctor(args):
    delegated = [args.repo]
    if args.json:
        delegated.append("--json")
    return doctor_main(delegated)


def _run_clauses(args):
    return cra_clauses_main([args.path] if args.path is not None else [])


def _run_remediate(args):
    finding_path = args.finding_option or args.finding_path
    if args.finding_option and args.finding_path:
        print(
            "error: provide the finding as a positional path or with --finding, not both",
            file=sys.stderr,
        )
        return 2
    if finding_path is None:
        print("error: a finding JSON path is required", file=sys.stderr)
        return 2

    try:
        finding = _load_json(finding_path)
    except (OSError, ValueError, TypeError) as error:
        print(f"error: failed to read finding JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(finding, dict):
        print("error: finding JSON must contain an object", file=sys.stderr)
        return 2

    try:
        plan = remediate(
            finding,
            args.repo_dir,
            ecosystem=args.ecosystem,
            update_lockfile=not args.no_update_lockfile,
            verify=not args.no_verify,
            dry_run=args.dry_run,
            commit_sha=args.commit_sha,
            offline=args.offline,
            registry=args.registry,
        )
    except RemediationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(plan.as_dict(), sys.stdout, indent=2)
        print()
    else:
        print("Remediation plan")
        print(f"Proposed-only: {plan.proposed_only}")
        if plan.manifest_patch is not None:
            print(f"Manifest patch: {plan.manifest_patch.path}")
        if plan.lockfile_plan is not None:
            print(f"Lockfile command: {plan.lockfile_plan.command}")
        if plan.pr_proposal is not None:
            print(f"PR proposal: {plan.pr_proposal.branch_name}")
            print(plan.pr_proposal.description.body)
    return 0


def _run_diff(args):
    try:
        current = load_report(args.current_report)
        baseline = load_report(args.baseline_report)
        delta = compare_reports(
            current, baseline, baseline_path=args.baseline_report
        )
    except ValueError as error:
        return _emit_cli_error(str(error), json_mode=args.json)
    if args.json:
        json.dump(delta, sys.stdout, indent=2)
        print()
    else:
        counts = delta["counts"]
        print(
            "New: {new}; existing: {existing}; resolved: {resolved}".format(
                **counts
            )
        )
    return delta_exit_code(current, delta)


def _run_scan(args):
    repo_path = Path(args.repo).resolve()
    if not repo_path.is_dir():
        return _emit_cli_error(
            "repository directory not found: " + str(repo_path),
            json_mode=args.json,
        )
    ecosystem = _detect_ecosystem(repo_path)
    if ecosystem is None:
        return _emit_cli_error(
            "no supported ecosystem manifest found in " + str(repo_path),
            json_mode=args.json,
        )

    try:
        config = load_config(repo_path, args.config)
    except ValueError as error:
        return _emit_cli_error(str(error), json_mode=args.json)
    scan_config = config.get("scan", {})
    output_config = config.get("outputs", {})
    policy_config = config.get("policy", {})
    excludes = sorted(
        DEFAULT_SCAN_EXCLUDES
        | set(scan_config.get("exclude", []))
        | set(args.exclude or [])
    )
    report_arg = args.report or output_config.get("report")
    sbom_arg = args.sbom or output_config.get("sbom")
    evidence_arg = args.evidence or output_config.get("evidence")
    baseline_arg = args.baseline or scan_config.get("baseline")
    delta_arg = args.delta or scan_config.get("delta")
    if report_arg:
        report_arg = resolve_config_path(repo_path, report_arg) if args.report is None else report_arg
    if sbom_arg:
        sbom_arg = resolve_config_path(repo_path, sbom_arg) if args.sbom is None else sbom_arg
    if evidence_arg:
        evidence_arg = resolve_config_path(repo_path, evidence_arg) if args.evidence is None else evidence_arg
    if baseline_arg:
        baseline_arg = resolve_config_path(repo_path, baseline_arg) if args.baseline is None else baseline_arg
    if delta_arg:
        delta_arg = resolve_config_path(repo_path, delta_arg) if args.delta is None else delta_arg
    fail_on = args.fail_on or policy_config.get("fail_on", "finding")

    report_path = report_arg
    temp_report = None
    try:
        if report_path is None:
            fd, report_path = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            temp_report = report_path

        if ecosystem in ("npm", "python"):
            analyze_argv = [args.repo]
            for name in excludes:
                analyze_argv.extend(["--exclude", name])
            if sbom_arg is not None:
                analyze_argv.extend(["--sbom", sbom_arg])
            analyze_argv.extend(["--report", report_path])
            with contextlib.redirect_stdout(
                io.StringIO() if args.json else sys.stdout
            ), contextlib.redirect_stderr(io.StringIO()):
                analysis_rc = analysis_main(analyze_argv)
            report = (
                _load_json(report_path)
                if analysis_rc != 2 and Path(report_path).is_file()
                else {}
            )
            classifier = _classifier_report(repo_path, excludes)
            scanner_error = _has_scanner_error(classifier)
            sbom = None if scanner_error else generate_sbom(str(repo_path))
            report = build_scan_report(
                repo=str(repo_path),
                ecosystem=ecosystem,
                findings=classifier.as_dicts(),
                package_name=report.get("package_name", "unknown"),
                package_version=report.get("package_version", "0.0.0"),
                declared=report.get("declared", []),
                imported=report.get("imported", []),
                sbom=sbom,
            )
            if sbom_arg is not None and sbom is not None:
                _write_json(sbom_arg, sbom)
        else:
            classifier = _classifier_report(repo_path, excludes)
            scanner_error = _has_scanner_error(classifier)
            sbom = None if scanner_error else generate_sbom(str(repo_path))
            if scanner_error:
                report = build_scan_report(
                    repo=str(repo_path),
                    ecosystem=ecosystem,
                    findings=classifier.as_dicts(),
                    sbom=sbom,
                )
            else:
                report = _go_report(
                    repo_path, classifier, sbom=sbom, excludes=excludes
                )
            if sbom_arg is not None and sbom is not None:
                _write_json(sbom_arg, sbom)

        delta = None
        if baseline_arg is not None:
            try:
                baseline = load_report(baseline_arg)
                delta = compare_reports(report, baseline, baseline_path=baseline_arg)
            except ValueError as error:
                return _emit_cli_error(str(error), json_mode=args.json)
            report["delta"] = delta
            if delta_arg is not None:
                _write_json(delta_arg, delta)

        _write_json(report_path, report)

        evidence_argv = [report_path]
        if evidence_arg is not None:
            evidence_argv.extend(["--json", evidence_arg])
        if evidence_main(evidence_argv) == 2:
            return 2

        if args.json:
            json.dump(report, sys.stdout, indent=2)
            print()
        scanner_error_message = _scanner_error_message(classifier)
        if scanner_error_message and not args.json:
            print("error: " + scanner_error_message, file=sys.stderr)

        if delta is not None:
            if not args.json:
                print(
                    "Baseline: "
                    + str(delta["counts"]["new"])
                    + " new, "
                    + str(delta["counts"]["existing"])
                    + " existing, "
                    + str(delta["counts"]["resolved"])
                    + " resolved"
                )
            code = delta_exit_code(report, delta)
        else:
            code = scan_exit_code(report)
        return 0 if fail_on == "never" and code == 1 else code
    except Exception as error:
        return _emit_cli_error(str(error), json_mode=args.json, kind="scanner-error")
    finally:
        if temp_report is not None:
            try:
                os.remove(temp_report)
            except OSError:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ImpactPrism command line interface.")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="analyze a repository")
    analyze.add_argument("repo_dir")
    analyze.add_argument("--exclude", action="append", metavar="PAT", default=None)
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

    doctor = subparsers.add_parser(
        "doctor", help="check local runtime and repository readiness"
    )
    doctor.add_argument("repo", nargs="?", default=".")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=_run_doctor)

    clauses = subparsers.add_parser("clauses", help="print the CRA clause map")
    clauses.add_argument("path", nargs="?", default=None)
    clauses.set_defaults(func=_run_clauses)

    remediate = subparsers.add_parser(
        "remediate", help="plan or apply a supported remediation"
    )
    remediate.add_argument("repo_dir")
    remediate.add_argument(
        "finding_path",
        nargs="?",
        metavar="FINDING_JSON",
        help="path to a JSON object containing one remediation finding",
    )
    remediate.add_argument(
        "--finding",
        dest="finding_option",
        metavar="PATH",
        help="path to a JSON object containing one remediation finding",
    )
    remediate.add_argument(
        "--ecosystem",
        choices=("auto", "npm", "python", "go"),
        default="auto",
    )
    remediate.add_argument("--no-update-lockfile", action="store_true")
    remediate.add_argument("--no-verify", action="store_true")
    dry_run = remediate.add_mutually_exclusive_group()
    dry_run.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="produce a plan without changing the repository (default)",
    )
    dry_run.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="apply the manifest and lockfile changes",
    )
    remediate.add_argument("--commit-sha")
    remediate.add_argument("--offline", action="store_true")
    remediate.add_argument("--registry")
    remediate.add_argument("--json", action="store_true")
    remediate.set_defaults(func=_run_remediate)

    scan = subparsers.add_parser(
        "scan", help="analyze a repository and generate an evidence pack in one shot"
    )
    scan.add_argument("repo")
    scan.add_argument("--exclude", action="append", metavar="PAT", default=None)
    scan.add_argument("--sbom", metavar="PATH")
    scan.add_argument("--report", metavar="PATH")
    scan.add_argument("--evidence", metavar="PATH")
    scan.add_argument("--baseline", metavar="PATH", help="compare findings with a previous scan report")
    scan.add_argument("--delta", metavar="PATH", help="write the baseline comparison JSON")
    scan.add_argument("--config", metavar="PATH", help="configuration file (default: .impactprism.toml in the repository)")
    scan.add_argument("--fail-on", choices=("finding", "never"), help="local exit policy; overrides configuration")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=_run_scan)

    diff = subparsers.add_parser(
        "diff", help="compare two scan reports without scanning a repository"
    )
    diff.add_argument("current_report")
    diff.add_argument("baseline_report")
    diff.add_argument("--json", action="store_true")
    diff.set_defaults(func=_run_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
