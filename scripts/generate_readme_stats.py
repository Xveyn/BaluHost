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
import ast
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def count_lines(files: Iterable[Path]) -> int:
    """Count newline bytes across files. Matches `wc -l` semantics.

    Relative paths are resolved against ROOT so the script works regardless
    of the process's current working directory. Skips files that are
    unreadable (missing, permission error). Counts newlines rather than
    lines to keep behavior simple and binary-safe.
    """
    total = 0
    for f in files:
        path = f if f.is_absolute() else ROOT / f
        try:
            with open(path, "rb") as fh:
                while chunk := fh.read(65536):
                    total += chunk.count(b"\n")
        except OSError:
            continue
    return total


def count_test_functions(files: Iterable[Path]) -> int:
    """Count def/async def whose name starts with 'test_' across files.

    Relative paths are resolved against ROOT so the script works regardless
    of the process's current working directory. Uses AST so it works without
    importing the project. Walks the whole tree to catch class methods.
    Files that fail to parse are skipped.
    """
    total = 0
    for f in files:
        path = f if f.is_absolute() else ROOT / f
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    total += 1
    return total


def tracked_files(cwd: Path | None = None) -> list[Path]:
    """List repo files tracked by git. Respects .gitignore by definition."""
    out = subprocess.check_output(
        ["git", "ls-files"],
        cwd=cwd or ROOT,
        text=True,
        encoding="utf-8",
    )
    return [Path(line) for line in out.splitlines() if line.strip()]


def _normalize(p: Path) -> str:
    return str(p).replace("\\", "/")


def under(
    files: Iterable[Path],
    *prefixes: str,
    exclude_init: bool = False,
) -> list[Path]:
    """Return files whose normalized path starts with any of the prefixes."""
    out: list[Path] = []
    for f in files:
        norm = _normalize(f)
        if not any(norm.startswith(p) for p in prefixes):
            continue
        if exclude_init and f.name == "__init__.py":
            continue
        out.append(f)
    return out


def with_ext(files: Iterable[Path], *exts: str) -> list[Path]:
    """Return files whose suffix is in exts (suffixes include the dot)."""
    return [f for f in files if f.suffix in exts]


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
