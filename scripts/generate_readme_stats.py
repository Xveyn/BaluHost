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
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
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


@dataclass(frozen=True)
class Bucket:
    files: int
    lines: int


@dataclass(frozen=True)
class Stats:
    backend_total: Bucket
    backend_app: Bucket
    backend_tests: Bucket
    backend_scripts: Bucket
    backend_alembic: Bucket
    backend_tui: Bucket
    frontend: Bucket
    test_functions: int
    api_route_modules: int
    service_modules: int
    db_models: int
    db_migrations: int
    frontend_pages: int
    workflows: int


def _bucket(files: list[Path]) -> Bucket:
    return Bucket(files=len(files), lines=count_lines(files))


def compute_stats(files: list[Path]) -> Stats:
    """Compute the full stats payload from a list of tracked file paths."""
    py = with_ext(files, ".py")

    app = under(py, "backend/app/")
    tests = under(py, "backend/tests/")
    scripts = under(py, "backend/scripts/")
    alembic = under(py, "backend/alembic/")
    tui = under(py, "backend/baluhost_tui/")

    backend_total_files = app + tests + scripts + alembic + tui
    frontend = under(
        with_ext(files, ".ts", ".tsx", ".js", ".jsx", ".css"),
        "client/src/",
    )

    return Stats(
        backend_total=_bucket(backend_total_files),
        backend_app=_bucket(app),
        backend_tests=_bucket(tests),
        backend_scripts=_bucket(scripts),
        backend_alembic=_bucket(alembic),
        backend_tui=_bucket(tui),
        frontend=_bucket(frontend),
        test_functions=count_test_functions(tests),
        api_route_modules=len(under(py, "backend/app/api/routes/", exclude_init=True)),
        service_modules=len(under(py, "backend/app/services/", exclude_init=True)),
        db_models=len(under(py, "backend/app/models/", exclude_init=True)),
        db_migrations=len(under(py, "backend/alembic/versions/")),
        frontend_pages=len(under(with_ext(files, ".tsx"), "client/src/pages/")),
        workflows=len(under(
            with_ext(files, ".yml", ".yaml"),
            ".github/workflows/",
        )),
    )


def _fmt(n: int) -> str:
    return f"{n:,}"


def render_project_stats_block(s: Stats, measured: str | None = None) -> str:
    """Render the Project Stats markdown block (between STATS markers)."""
    measured = measured or date.today().isoformat()
    return (
        "| Metric | Count |\n"
        "|--------|-------|\n"
        "| **Version** | "
        "![Latest Release]"
        "(https://img.shields.io/github/v/release/Xveyn/BaluHost?label=) |\n"
        f"| **Backend code** | {_fmt(s.backend_total.lines)} lines across "
        f"{_fmt(s.backend_total.files)} Python files |\n"
        f"| &nbsp;&nbsp;↳ Application (`app/`) | {_fmt(s.backend_app.lines)} lines / "
        f"{_fmt(s.backend_app.files)} files |\n"
        f"| &nbsp;&nbsp;↳ Tests (`tests/`) | {_fmt(s.backend_tests.lines)} lines / "
        f"{_fmt(s.backend_tests.files)} files |\n"
        f"| &nbsp;&nbsp;↳ Scripts (`scripts/`) | {_fmt(s.backend_scripts.lines)} lines / "
        f"{_fmt(s.backend_scripts.files)} files |\n"
        f"| &nbsp;&nbsp;↳ Alembic migrations | {_fmt(s.backend_alembic.lines)} lines / "
        f"{_fmt(s.backend_alembic.files)} files |\n"
        f"| &nbsp;&nbsp;↳ Terminal UI (`baluhost_tui/`) | {_fmt(s.backend_tui.lines)} lines / "
        f"{_fmt(s.backend_tui.files)} files |\n"
        f"| **Frontend code** | {_fmt(s.frontend.lines)} lines across "
        f"{_fmt(s.frontend.files)} source files (`client/src/`, .ts/.tsx/.js/.jsx/.css) |\n"
        f"| **Test functions** | {s.test_functions} |\n"
        f"| **API route modules** | {s.api_route_modules} |\n"
        f"| **Service modules** | {s.service_modules} |\n"
        f"| **Database models** | {s.db_models} |\n"
        f"| **Database migrations** | {s.db_migrations} |\n"
        f"| **Frontend pages** | {s.frontend_pages} |\n"
        f"| **CI/CD workflows** | {s.workflows} |\n"
        "\n"
        "<sub>LOC counted via `git ls-files` (respects `.gitignore`, "
        "excludes virtualenvs, `node_modules/`, `dist/`, caches, dev-storage). "
        f"Last measured {measured}.</sub>"
    )


def render_test_count(s: Stats) -> str:
    return f"{s.test_functions} tests"


def render_test_files(s: Stats) -> str:
    return f"{s.backend_tests.files} test files"


def replace_between_markers(
    text: str, name: str, content: str, *, inline: bool = False
) -> str:
    """Replace the content between <!-- STATS:NAME:START --> and ...:END -->.

    Block mode (default): expects markers on their own lines, replaces the
    lines in between. Inline mode: marker pair appears on a single line and
    only the inner span is replaced.

    Raises ValueError if either marker is missing.
    """
    start = f"<!-- STATS:{name}:START -->"
    end = f"<!-- STATS:{name}:END -->"
    if start not in text or end not in text:
        raise ValueError(f"Marker pair STATS:{name} not found in text")

    if inline:
        pattern = re.escape(start) + r".*?" + re.escape(end)
        return re.sub(pattern, f"{start}{content}{end}", text, count=1, flags=re.S)

    # Block mode: keep marker lines, replace everything strictly between.
    pattern = (
        re.escape(start) + r"\n.*?\n" + re.escape(end)
    )
    return re.sub(pattern, f"{start}\n{content}\n{end}", text, count=1, flags=re.S)


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
