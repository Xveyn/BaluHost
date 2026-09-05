#!/usr/bin/env python3
"""Map the BaluHost repo: LOC per directory plus per-file refactor signals.

Counts only files reported by `git ls-files`, so .gitignore is respected by
definition. No third-party dependencies.

Usage:
    python scripts/repo_map.py                  # writes repo-map.html
    python scripts/repo_map.py -o /tmp/map.html # custom output path
"""
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from repo_map_metrics import FileEntry, Thresholds, analyze_file

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class DirNode:
    """A directory in the map, carrying the totals of everything beneath it."""

    name: str
    path: str
    loc: int = 0
    files: int = 0
    children: dict[str, DirNode] = field(default_factory=dict)
    entries: list[FileEntry] = field(default_factory=list)


def build_tree(entries: Iterable[FileEntry]) -> DirNode:
    """Aggregate file entries into a directory tree with rolled-up totals."""
    root = DirNode(name="", path="")
    for entry in entries:
        parts = entry.path.split("/")
        node = root
        node.loc += entry.loc
        node.files += 1
        for index, part in enumerate(parts[:-1]):
            child = node.children.get(part)
            if child is None:
                child = DirNode(name=part, path="/".join(parts[: index + 1]))
                node.children[part] = child
            child.loc += entry.loc
            child.files += 1
            node = child
        node.entries.append(entry)
    return root


@dataclass(frozen=True)
class Report:
    """Everything one run produces, ready to be rendered."""

    commit: str
    generated_at: str
    thresholds: Thresholds
    entries: list[FileEntry]
    tree: DirNode


def tracked_files(root: Path) -> list[str]:
    """List repo files tracked by git. Respects .gitignore by definition."""
    out = subprocess.check_output(
        ["git", "ls-files"], cwd=root, text=True, encoding="utf-8"
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def git_commit(root: Path) -> str:
    """Short SHA of HEAD, or 'unknown' outside a repository."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return "unknown"
    return out.strip() or "unknown"


def _read_text(path: Path) -> str | None:
    """Decode a file as UTF-8, or None when it is missing or not text."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return None if "\x00" in text else text


def build_report(
    root: Path,
    paths: Iterable[str],
    *,
    thresholds: Thresholds,
    commit: str,
    include_generated: bool = False,
    generated_at: str | None = None,
) -> Report:
    """Analyse every readable path under root and assemble the report.

    Unreadable and binary files are skipped rather than raising: a repo map
    that dies on one stray blob is useless.
    """
    entries: list[FileEntry] = []
    for rel in paths:
        text = _read_text(root / rel)
        if text is None:
            continue
        entries.append(
            analyze_file(
                rel,
                text,
                thresholds=thresholds,
                include_generated=include_generated,
            )
        )

    return Report(
        commit=commit,
        generated_at=generated_at or datetime.now().strftime("%Y-%m-%d %H:%M"),
        thresholds=thresholds,
        entries=entries,
        tree=build_tree(entries),
    )


def main(argv: list[str] | None = None) -> int:
    # Imported here, not at module level: the renderer imports this module back
    # for its dataclasses, and a top-level import would close that cycle.
    import repo_map_html

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "repo-map.html"),
        help="output path (default: repo-map.html in the repo root)",
    )
    parser.add_argument("--max-loc", type=int, default=Thresholds.max_loc)
    parser.add_argument("--max-fn-loc", type=int, default=Thresholds.max_fn_loc)
    parser.add_argument("--max-depth", type=int, default=Thresholds.max_depth)
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="score generated files like hand-written ones",
    )
    args = parser.parse_args(argv)

    thresholds = Thresholds(
        max_loc=args.max_loc,
        max_fn_loc=args.max_fn_loc,
        max_depth=args.max_depth,
    )
    report = build_report(
        ROOT,
        tracked_files(ROOT),
        thresholds=thresholds,
        commit=git_commit(ROOT),
        include_generated=args.include_generated,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(repo_map_html.render(report), encoding="utf-8")

    flagged = sum(1 for e in report.entries if e.score > 0)
    print(
        f"{len(report.entries)} files, {report.tree.loc:,} lines, "
        f"{flagged} flagged -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
