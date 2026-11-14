"""Command-line interface for reporttool."""

import argparse

from . import table


def build_parser():
    """Build the report command-line parser."""
    parser = argparse.ArgumentParser(prog="report")
    parser.add_argument("title")
    parser.add_argument("items", nargs="*", metavar="KEY=VALUE")
    return parser


def main(argv=None) -> int:
    """Render a report and return a process exit status."""
    args = build_parser().parse_args(argv)
    rows = [item.split("=", 1) for item in args.items]
    print(table.format_table(args.title, rows))
    return 0
