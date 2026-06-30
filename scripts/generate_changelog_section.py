#!/usr/bin/env python3
"""Generate a Keep-a-Changelog section from Conventional Commits.

Local drafting aid only -- /release-prepare uses this to seed a
hand-curated CHANGELOG section; no CI workflow invokes this script anymore.

Usage:
    python scripts/generate_changelog_section.py \\
        --version 1.32.0 \\
        --since v1.31.0 \\
        --output CHANGELOG-section.md

Or with prepared input on stdin (used by tests):
    python scripts/generate_changelog_section.py \\
        --version 1.32.0 --date 2026-05-06 --stdin --output - < commits.txt

Stdin format (each commit terminated by 0x1e, fields separated by 0x1f):
    <sha>\\x1f<subject>\\x1f<body>\\x1e

Conventional Commits mapping:
    feat:      -> ### Added
    fix:       -> ### Fixed
    refactor:  -> ### Changed
    perf:      -> ### Changed
    docs:      -> ### Documentation
    feat!: / BREAKING CHANGE: in body -> ### ⚠ BREAKING CHANGES (top of section)
    chore:/ci:/test:/style:/build: -> ignored
    Anything without a recognised prefix -> ignored
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path

CC_PATTERN = re.compile(
    r"^(?P<type>feat|fix|refactor|perf|docs|chore|ci|test|style|build|revert)"
    r"(?P<bang>!?)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r":\s*(?P<desc>.+)$"
)

GROUP_FOR_TYPE = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "perf": "Changed",
    "docs": "Documentation",
}

IGNORED_TYPES = {"chore", "ci", "test", "style", "build", "revert"}


def parse_commits_from_stdin() -> list[tuple[str, str, str]]:
    raw = sys.stdin.read()
    if not raw:
        return []
    out: list[tuple[str, str, str]] = []
    for entry in raw.split("\x1e"):
        if not entry.strip():
            continue
        parts = entry.split("\x1f")
        # Pad to (sha, subject, body)
        while len(parts) < 3:
            parts.append("")
        sha, subject, body = parts[0], parts[1], parts[2]
        out.append((sha.strip(), subject.strip(), body.strip()))
    return out


def parse_commits_from_git(since: str) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["git", "log", f"{since}..HEAD",
         "--pretty=format:%H\x1f%s\x1f%b\x1e",
         "--no-merges"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"git log failed: {result.stderr}\n")
        sys.exit(2)
    raw = result.stdout
    if not raw.strip():
        return []
    out: list[tuple[str, str, str]] = []
    for entry in raw.split("\x1e"):
        if not entry.strip():
            continue
        parts = entry.split("\x1f")
        while len(parts) < 3:
            parts.append("")
        out.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return out


def classify(subject: str, body: str) -> tuple[str | None, str, bool]:
    """Return (group, formatted_description, is_breaking).

    group is one of: "Added", "Fixed", "Changed", "Documentation", or None (ignore).
    Breaking commits are also returned with their normal group, plus is_breaking=True.
    """
    m = CC_PATTERN.match(subject)
    if not m:
        return (None, "", False)
    cc_type = m.group("type")
    bang = m.group("bang") == "!"
    scope = m.group("scope")
    desc = m.group("desc").strip()
    is_breaking = bang or "BREAKING CHANGE:" in body

    if cc_type in IGNORED_TYPES and not is_breaking:
        return (None, "", False)
    group = GROUP_FOR_TYPE.get(cc_type)
    # group stays None for ignored types even when breaking;
    # render_section() handles is_breaking independently via its own list.
    formatted = f"**({scope})** {desc}" if scope else desc
    return (group, formatted, is_breaking)


def render_section(version: str, date_iso: str,
                   commits: list[tuple[str, str, str]]) -> str:
    breaking: list[str] = []
    buckets: dict[str, list[str]] = {
        "Added": [],
        "Changed": [],
        "Fixed": [],
        "Documentation": [],
    }
    for _sha, subject, body in commits:
        group, desc, is_breaking = classify(subject, body)
        if is_breaking and desc:
            breaking.append(desc)
        if group is not None and desc:
            buckets[group].append(desc)

    lines: list[str] = [f"## [{version}] - {date_iso}", ""]
    if breaking:
        lines.append("### ⚠ BREAKING CHANGES")
        lines.append("")
        for item in breaking:
            lines.append(f"- {item}")
        lines.append("")
    for group in ("Added", "Changed", "Fixed", "Documentation"):
        items = buckets[group]
        if not items:
            continue
        lines.append(f"### {group}")
        lines.append("")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", default=date_cls.today().isoformat())
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--since", help="Git ref to read commits from.")
    mode_group.add_argument("--stdin", action="store_true",
                            help="Read commits from stdin (test mode)")
    parser.add_argument("--output", required=True,
                        help="Output file path or '-' for stdout")
    args = parser.parse_args()

    if args.stdin:
        commits = parse_commits_from_stdin()
    else:
        commits = parse_commits_from_git(args.since)

    section = render_section(args.version, args.date, commits)

    if args.output == "-":
        # Write to stdout with UTF-8 encoding explicitly to handle Unicode chars
        text_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline=None)
        text_stdout.write(section)
        text_stdout.flush()
    else:
        Path(args.output).write_text(section, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
