#!/usr/bin/env python3
"""Finalize the `## [Unreleased]` CHANGELOG section into a versioned, dated one.

The prepare flow (`/release-prepare`) writes a hand-curated `## [Unreleased]`
section with no version/date so it never matches the GitHub-release-fallback
parser's `## [x.y.z] - date` pattern (`changelog_fallback.py`). This script
runs in the promote step (`release-stable.yml`) once that PR has merged,
turning the bare placeholder into the real, dated header.

Usage:
    python scripts/finalize_changelog_section.py \\
        --version 1.32.0 \\
        --date 2026-05-06 \\
        --target CHANGELOG.md
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date as date_cls
from pathlib import Path

UNRELEASED_RE = re.compile(r"^## \[Unreleased\][ \t]*$", re.MULTILINE)


def finalize(target: Path, version: str, date_iso: str) -> None:
    text = target.read_text(encoding="utf-8")
    matches = list(UNRELEASED_RE.finditer(text))
    if not matches:
        sys.stderr.write(
            f"No '## [Unreleased]' section found in {target} -- "
            "merge the release-prep PR first\n"
        )
        sys.exit(2)
    if len(matches) > 1:
        sys.stderr.write(
            f"Found {len(matches)} '## [Unreleased]' sections in {target} -- expected exactly 1\n"
        )
        sys.exit(2)

    match = matches[0]
    new_header = f"## [{version}] - {date_iso}"
    new_text = text[: match.start()] + new_header + text[match.end():]
    target.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    finalize(args.target, args.version, args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
