"""Command-line interface: ``codehound scan <path>``."""

from __future__ import annotations

import argparse
import json
import sys

from codehound import __version__
from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import DEFAULT_SKIP_DIRS, scan_path


def _cmd_scan(args: argparse.Namespace) -> int:
    selected = [s.strip() for s in args.select.split(",")] if args.select else None
    checks = get_checks(selected)
    if not checks:
        print(f"No checks matched: {args.select}", file=sys.stderr)
        return 2

    skip = set(DEFAULT_SKIP_DIRS)
    if args.include_tests:
        skip -= {"tests", "test", "testing"}
    findings = scan_path(args.path, checks, skip_dirs=frozenset(skip))

    if args.format == "json":
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    elif args.format == "csv":
        print("path,line,col,code,message")
        for f in findings:
            msg = f.message.replace('"', "'")
            print(f'{f.path},{f.line},{f.col},{f.code},"{msg}"')
    else:  # text
        for f in findings:
            print(f.as_text())
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.code] = counts.get(f.code, 0) + 1
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        print(
            f"\nFound {len(findings)} issue(s)"
            + (f" ({summary})" if summary else ""),
            file=sys.stderr,
        )

    if findings and not args.exit_zero:
        return 1
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    for cls in ALL_CHECKS:
        print(f"{cls.code}  {cls.name}\n      {cls.description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codehound",
        description="AST-based static analyzer that hunts real bugs in Python code.",
    )
    parser.add_argument("--version", action="version", version=f"codehound {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan a file or directory for issues")
    scan.add_argument("path", help="file or directory to scan")
    scan.add_argument(
        "--select",
        help="comma-separated check codes/names to run (default: all), e.g. CH001,CH006",
    )
    scan.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="output format (default: text)",
    )
    scan.add_argument(
        "--include-tests",
        action="store_true",
        help="also scan tests/ directories (skipped by default)",
    )
    scan.add_argument(
        "--exit-zero",
        action="store_true",
        help="always exit 0, even when issues are found",
    )
    scan.set_defaults(func=_cmd_scan)

    listp = sub.add_parser("list", help="list available checks")
    listp.set_defaults(func=_cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
