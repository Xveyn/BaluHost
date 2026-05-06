#!/usr/bin/env python3
"""Generate and splice BaluHost README stats from tracked git files.

Counts only files reported by `git ls-files` — automatically respects
.gitignore. No third-party dependencies.

Usage:
    python scripts/generate_readme_stats.py            # check mode (exit 1 if drift)
    python scripts/generate_readme_stats.py --check    # explicit check mode
    python scripts/generate_readme_stats.py --write    # rewrite README.md in place
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def count_lines(files: Iterable[Path]) -> int:
    """Count newline bytes across files. Matches `wc -l` semantics.

    Skips files that are unreadable (missing, permission error). We count
    newlines rather than lines to keep behavior simple and binary-safe.
    """
    total = 0
    for f in files:
        try:
            with open(f, "rb") as fh:
                while chunk := fh.read(65536):
                    total += chunk.count(b"\n")
        except OSError:
            continue
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Rewrite README.md")
    parser.add_argument("--check", action="store_true", help="Exit 1 if drift")
    args = parser.parse_args()

    if not args.write and not args.check:
        args.check = True

    raise NotImplementedError("filled in by later tasks")


if __name__ == "__main__":
    sys.exit(main())
