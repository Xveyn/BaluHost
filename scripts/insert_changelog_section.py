#!/usr/bin/env python3
"""Insert a new CHANGELOG section after the H1 heading.

Usage:
    python scripts/insert_changelog_section.py \\
        --section /tmp/changelog-section.md \\
        --target CHANGELOG.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

H1_PATTERN = re.compile(r"^# Changelog\s*$", re.MULTILINE)
# Find the first '---\n' separator after the H1 heading
SEPARATOR_AFTER_H1 = re.compile(r"^---\s*$", re.MULTILINE)


def insert(target: Path, section_text: str) -> None:
    text = target.read_text(encoding="utf-8")

    h1_match = H1_PATTERN.search(text)
    if not h1_match:
        sys.stderr.write(
            f"Target {target} does not contain '# Changelog' heading\n"
        )
        sys.exit(2)

    sep_match = SEPARATOR_AFTER_H1.search(text, pos=h1_match.end())
    if sep_match:
        # Insert directly after the separator, with one blank line before the new section
        insert_at = sep_match.end()
        before = text[:insert_at]
        after = text[insert_at:]
        # Strip leading newlines from after, then add exactly one blank line
        after = after.lstrip("\n")
        # before ends with '\n', so we add one more \n to create a blank line
        new_text = before + "\n" + section_text.rstrip() + "\n\n" + after
    else:
        # No separator after H1 — insert directly after the H1 line
        insert_at = h1_match.end()
        before = text[:insert_at]
        after = text[insert_at:]
        new_text = before + "\n\n" + section_text.rstrip() + "\n" + after

    target.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    section_text = args.section.read_text(encoding="utf-8")
    insert(args.target, section_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
