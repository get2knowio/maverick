#!/usr/bin/env python3
"""
Snapshot Diff - Compare two TUI text snapshots and highlight changes.

Usage:
    python snapshot_diff.py before.txt after.txt [--context LINES]

Output shows:
    - Lines only in before (removed): prefixed with '- '
    - Lines only in after (added): prefixed with '+ '
    - Character-level changes for modified lines
    - Summary of change locations
"""

import argparse
import difflib
import sys
from pathlib import Path


def load_snapshot(path: str) -> list[str]:
    """Load a snapshot file, stripping ANSI codes if present."""
    import re

    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    with open(path) as f:
        lines = f.readlines()

    # Strip ANSI codes and trailing whitespace, preserve line structure
    return [ansi_escape.sub("", line).rstrip() for line in lines]


def find_changed_regions(before: list[str], after: list[str]) -> list[dict]:
    """Identify contiguous regions of change."""
    matcher = difflib.SequenceMatcher(None, before, after)
    regions = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            regions.append(
                {
                    "type": tag,
                    "before_start": i1,
                    "before_end": i2,
                    "after_start": j1,
                    "after_end": j2,
                    "before_lines": before[i1:i2],
                    "after_lines": after[j1:j2],
                }
            )

    return regions


def format_char_diff(line1: str, line2: str) -> tuple[str, str]:
    """Show character-level differences between two lines."""
    matcher = difflib.SequenceMatcher(None, line1, line2)

    result1 = []
    result2 = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result1.append(line1[i1:i2])
            result2.append(line2[j1:j2])
        elif tag == "replace":
            result1.append(f"[{line1[i1:i2]}]")
            result2.append(f"[{line2[j1:j2]}]")
        elif tag == "delete":
            result1.append(f"[{line1[i1:i2]}]")
        elif tag == "insert":
            result2.append(f"[{line2[j1:j2]}]")

    return "".join(result1), "".join(result2)


def print_diff(before: list[str], after: list[str], context: int = 3):
    """Print a human-readable diff with context."""
    regions = find_changed_regions(before, after)

    if not regions:
        print("No differences found.")
        return

    print(f"Found {len(regions)} changed region(s):\n")

    for i, region in enumerate(regions, 1):
        print(f"{'=' * 60}")
        print(f"Region {i}: {region['type'].upper()}")
        print(f"  Before lines {region['before_start'] + 1}-{region['before_end']}")
        print(f"  After lines {region['after_start'] + 1}-{region['after_end']}")
        print(f"{'=' * 60}")

        # Show context before
        ctx_start = max(0, region["before_start"] - context)
        if ctx_start < region["before_start"]:
            print("\n  Context (before):")
            for idx in range(ctx_start, region["before_start"]):
                print(f"    {idx + 1:4d} | {before[idx]}")

        # Show the change
        if region["type"] == "replace":
            print("\n  Changed:")
            # Pair up lines for character-level diff where possible
            max_lines = max(len(region["before_lines"]), len(region["after_lines"]))
            for idx in range(max_lines):
                before_line = (
                    region["before_lines"][idx]
                    if idx < len(region["before_lines"])
                    else ""
                )
                after_line = (
                    region["after_lines"][idx]
                    if idx < len(region["after_lines"])
                    else ""
                )

                if before_line and after_line:
                    diff1, diff2 = format_char_diff(before_line, after_line)
                    print(f"    - {diff1}")
                    print(f"    + {diff2}")
                elif before_line:
                    print(f"    - {before_line}")
                else:
                    print(f"    + {after_line}")

        elif region["type"] == "delete":
            print("\n  Removed:")
            for line in region["before_lines"]:
                print(f"    - {line}")

        elif region["type"] == "insert":
            print("\n  Added:")
            for line in region["after_lines"]:
                print(f"    + {line}")

        # Show context after
        ctx_end = min(len(after), region["after_end"] + context)
        if ctx_end > region["after_end"]:
            print("\n  Context (after):")
            for idx in range(region["after_end"], ctx_end):
                if idx < len(after):
                    print(f"    {idx + 1:4d} | {after[idx]}")

        print()

    # Summary
    print(f"{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    total_removed = sum(
        len(r["before_lines"]) for r in regions if r["type"] in ("delete", "replace")
    )
    total_added = sum(
        len(r["after_lines"]) for r in regions if r["type"] in ("insert", "replace")
    )
    print(f"  Lines removed/changed: {total_removed}")
    print(f"  Lines added/changed: {total_added}")
    print(f"  Regions affected: {len(regions)}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare two TUI text snapshots and highlight changes"
    )
    parser.add_argument("before", help="Path to 'before' snapshot file")
    parser.add_argument("after", help="Path to 'after' snapshot file")
    parser.add_argument(
        "--context",
        "-c",
        type=int,
        default=3,
        help="Number of context lines to show (default: 3)",
    )

    args = parser.parse_args()

    # Validate files exist
    for path in [args.before, args.after]:
        if not Path(path).exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)

    before = load_snapshot(args.before)
    after = load_snapshot(args.after)

    print(f"Comparing: {args.before} → {args.after}")
    print(f"Before: {len(before)} lines, After: {len(after)} lines\n")

    print_diff(before, after, args.context)


if __name__ == "__main__":
    main()
