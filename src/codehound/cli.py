"""Command-line interface: ``codehound scan <path>``."""

from __future__ import annotations

import argparse
import ast
import json
import sys

from codehound import __version__
from codehound.checks import ALL_CHECKS, get_checks
from codehound.config import load_config
from codehound.core import DEFAULT_SKIP_DIRS, build_parents, iter_python_files, scan_files
from codehound.fixes import fix_source
from codehound.sarif import to_sarif
from codehound.terminal import format_findings_text, format_summary


def _apply_fixes(paths: list[str], skip_dirs: frozenset) -> tuple[int, int]:
    """Rewrite every fixable finding in place. Returns ``(files_changed, edit_count)``."""
    files_changed = 0
    total_edits = 0
    for root in paths:
        for path in iter_python_files(root, skip_dirs):
            try:
                with open(path, encoding="utf-8") as fh:
                    source = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError:
                continue
            parents = build_parents(tree)
            new_source, count = fix_source(source, tree, parents)
            if count:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new_source)
                files_changed += 1
                total_edits += count
    return files_changed, total_edits


def _cmd_scan(args: argparse.Namespace) -> int:
    config = load_config()

    select_arg = args.select or (",".join(config.select) if config.select else None)
    selected = [s.strip() for s in select_arg.split(",")] if select_arg else None
    checks = get_checks(selected)
    if not checks:
        print(f"No checks matched: {select_arg}", file=sys.stderr)
        return 2

    paths = args.paths or config.paths or ["."]

    skip = set(DEFAULT_SKIP_DIRS)
    if args.include_tests:
        skip -= {"tests", "test", "testing"}
    skip |= set(config.exclude)
    if args.exclude:
        skip |= {e.strip() for e in args.exclude.split(",") if e.strip()}

    if args.fix:
        files_changed, edit_count = _apply_fixes(paths, frozenset(skip))
        if edit_count:
            print(f"Fixed {edit_count} issue(s) in {files_changed} file(s).", file=sys.stderr)

    all_files: list[str] = []
    for path in paths:
        all_files.extend(iter_python_files(path, frozenset(skip)))
    findings = scan_files(all_files, checks)

    if args.format == "json":
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    elif args.format == "csv":
        print("path,line,col,code,message")
        for f in findings:
            msg = f.message.replace('"', "'")
            print(f'{f.path},{f.line},{f.col},{f.code},"{msg}"')
    elif args.format == "sarif":
        print(json.dumps(to_sarif(findings, ALL_CHECKS), indent=2))
    else:  # text
        for line in format_findings_text(findings):
            print(line)
        print(f"\n{format_summary(findings)}", file=sys.stderr)

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

    scan = sub.add_parser("scan", help="scan one or more files/directories for issues")
    scan.add_argument(
        "paths",
        nargs="*",
        metavar="path",
        help=(
            "file(s) or director(y/ies) to scan (accepts multiple, for pre-commit). "
            "Defaults to `paths` in pyproject.toml's [tool.codehound], then `.`"
        ),
    )
    scan.add_argument(
        "--select",
        help=(
            "comma-separated check codes/names to run (default: `select` in "
            "pyproject.toml's [tool.codehound], else all), e.g. CH001,CH006"
        ),
    )
    scan.add_argument(
        "--exclude",
        help=(
            "comma-separated extra directory names to skip, merged with the "
            "built-in defaults and pyproject.toml's [tool.codehound] `exclude`"
        ),
    )
    scan.add_argument(
        "--format",
        choices=["text", "json", "csv", "sarif"],
        default="text",
        help="output format (default: text; sarif for GitHub Code Scanning)",
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
    scan.add_argument(
        "--fix",
        action="store_true",
        help=(
            "rewrite fixable findings in place before reporting (currently CH017, "
            "and CH004 only inside async functions - see docs/ARCHITECTURE.md)"
        ),
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
