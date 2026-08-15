import argparse
import sys

from analysis import main as analysis_main
from evidence import main as evidence_main
from cra_clauses import main as cra_clauses_main


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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
