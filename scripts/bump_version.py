#!/usr/bin/env python3
"""Bump the project version in all relevant files.

Single source of truth: backend/pyproject.toml
Synced targets: client/package.json, CLAUDE.md

Usage:
    python scripts/bump_version.py 1.21.0
    python scripts/bump_version.py patch      # 1.20.2 -> 1.20.3
    python scripts/bump_version.py minor      # 1.20.2 -> 1.21.0
    python scripts/bump_version.py major      # 1.20.2 -> 2.0.0
    python scripts/bump_version.py            # just sync from pyproject.toml (no bump)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "backend" / "pyproject.toml"
PACKAGE_JSON = ROOT / "client" / "package.json"
CLAUDE_MD = ROOT / "CLAUDE.md"


def read_current_version() -> str:
    """Read version from pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("Could not find version in pyproject.toml")
    return m.group(1)


def bump(current: str, part: str) -> str:
    """Bump a semver part."""
    parts = current.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump type: {part}")


def update_pyproject(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    text = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        rf'\g<1>"{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(text, encoding="utf-8")


def update_package_json(version: str) -> None:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    data["version"] = version
    PACKAGE_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def update_claude_md(version: str) -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    text = re.sub(
        r"(\*\*Version\*\*:\s*)\S+",
        rf"\g<1>{version}",
        text,
        count=1,
    )
    CLAUDE_MD.write_text(text, encoding="utf-8")


def main() -> None:
    current = read_current_version()

    if len(sys.argv) < 2:
        # Sync-only mode: propagate current version to all targets
        new_version = current
        print(f"Syncing version {new_version} to all files...")
    else:
        arg = sys.argv[1]
        if arg in ("major", "minor", "patch"):
            new_version = bump(current, arg)
        elif re.match(r"^\d+\.\d+\.\d+", arg):
            new_version = arg
        else:
            print(f"Usage: {sys.argv[0]} [major|minor|patch|X.Y.Z]")
            sys.exit(1)
        print(f"Bumping version: {current} -> {new_version}")
        update_pyproject(new_version)

    update_package_json(new_version)
    update_claude_md(new_version)

    print(f"Updated files:")
    print(f"  backend/pyproject.toml  -> {new_version}")
    print(f"  client/package.json     -> {new_version}")
    print(f"  CLAUDE.md               -> {new_version}")
    print()
    print("Note: Run 'cd client && npm install' to sync package-lock.json")


if __name__ == "__main__":
    main()
