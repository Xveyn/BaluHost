# README Stats Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-update the Project Stats table and Production Status test counts in `README.md` on every release, using a stdlib-only Python script driven by `git ls-files` (no third-party deps, no gitignored files counted).

**Architecture:** A single script `scripts/generate_readme_stats.py` enumerates tracked files via `git ls-files`, categorizes them by path/extension, computes counts and LOC, and splices the result into `README.md` between named HTML-comment markers. The script runs inside the existing `auto-merge.yml` workflow as part of the version-bump commit, so stats changes ride along with the release on `main` (no separate auto-commit). Tests live in `scripts/test_generate_readme_stats.py` next to the script and run via pytest.

**Tech Stack:** Python 3.11 stdlib only (`subprocess`, `pathlib`, `ast`, `re`, `dataclasses`, `argparse`). Pytest for tests (already a dev dep). YAML edit to `auto-merge.yml`.

---

## File Structure

- **Create:** `scripts/generate_readme_stats.py` — the script (CLI entry + library functions)
- **Create:** `scripts/test_generate_readme_stats.py` — pytest tests for the script
- **Create:** `scripts/conftest.py` — adds `scripts/` to `sys.path` so tests can `import generate_readme_stats`
- **Modify:** `README.md` — add `<!-- STATS:* -->` markers around dynamic content, remove inline file/module counts from the architecture tree (single source of truth = Project Stats table)
- **Modify:** `.github/workflows/auto-merge.yml:57-75` — add `python3 scripts/generate_readme_stats.py --write` before the version-bump commit; include `README.md` in the staged paths

**Responsibilities:**
- `generate_readme_stats.py` does all logic (collect → compute → render → splice). Single file, no submodules.
- `test_generate_readme_stats.py` tests pure functions in isolation (no git invocation, no real README writes).
- `conftest.py` is a 2-line shim — nothing else.

---

## Design Decisions (locked in)

1. **Source of truth for "tracked files":** `git ls-files`. This automatically respects `.gitignore`, excludes `node_modules/`, `.venv/`, `dist/`, `dev-storage/`, etc. — no manual ignore list needed.
2. **Architecture tree (README.md:170–186):** the inline counts (`51 API route modules`, `143 service modules`, etc.) get **stripped**. Tree stays as a pure structural diagram. All counts live in the Project Stats table — one source of truth.
3. **Test-function counting:** AST-parse each tracked test file (`backend/tests/**/*.py` matching `test_*.py` or `*_test.py`) and count top-level + class-method functions named `test_*` or `async test_*`. No reliance on `pytest --collect-only` (would require importable backend with all deps).
4. **Markers:** `<!-- STATS:<NAME>:START -->` ... `<!-- STATS:<NAME>:END -->`. Block-level markers for the Project Stats table; inline markers for the testing row. The script raises a clear error if any expected marker is missing.
5. **CLI modes:**
   - `--check` (default in CI verification, optional): exits non-zero if README would change.
   - `--write` (used in auto-merge.yml): rewrites README in place.
   - No flags = `--check` (safer default).
6. **Categories counted** (matches current README Project Stats table):
   - Backend total LOC + file count (Python files anywhere under `backend/` excluding tests is **not** the split — current README sums *all* Python files including tests; we preserve that)
   - Per-subdir splits: `backend/app/`, `backend/tests/`, `backend/scripts/`, `backend/alembic/`, `backend/baluhost_tui/`
   - Frontend: `client/src/**/*.{ts,tsx,js,jsx,css}`
   - Test functions (count of `def test_*` in tracked test files)
   - API route modules: `backend/app/api/routes/*.py` excluding `__init__.py`
   - Service modules: `backend/app/services/**/*.py` excluding `__init__.py`
   - Database models: `backend/app/models/*.py` excluding `__init__.py`
   - Database migrations: `backend/alembic/versions/*.py` (no `__init__.py` exclusion needed there)
   - Frontend pages: `client/src/pages/**/*.tsx`
   - CI/CD workflows: `.github/workflows/*.{yml,yaml}`

---

## Task 1: Project Skeleton

**Files:**
- Create: `scripts/generate_readme_stats.py`
- Create: `scripts/conftest.py`
- Create: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Create the conftest shim**

Write `scripts/conftest.py`:

```python
"""Add scripts/ to sys.path so sibling test modules can import the script."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 2: Create the script with a placeholder main**

Write `scripts/generate_readme_stats.py`:

```python
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

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


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
```

- [ ] **Step 3: Create the test file with a smoke import test**

Write `scripts/test_generate_readme_stats.py`:

```python
"""Tests for scripts/generate_readme_stats.py — stdlib + pytest only."""
from __future__ import annotations

import generate_readme_stats as grs


def test_module_imports():
    assert hasattr(grs, "main")
```

- [ ] **Step 4: Run the smoke test**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/conftest.py scripts/test_generate_readme_stats.py
git commit -m "chore(stats): scaffold readme stats generator"
```

---

## Task 2: `count_lines()` for LOC

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_generate_readme_stats.py`:

```python
def test_count_lines_simple(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    assert grs.count_lines([f]) == 3


def test_count_lines_no_trailing_newline(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("a\nb\nc", encoding="utf-8")  # no final \n
    # Newline count: \n appears twice → 3 lines logically. We define count as
    # number of \n bytes, matching `wc -l` semantics (which under-counts the
    # last unterminated line). Document this in the test.
    assert grs.count_lines([f]) == 2


def test_count_lines_handles_binary_and_missing(tmp_path):
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\x01\n\x02")  # 1 newline byte
    missing = tmp_path / "does-not-exist.py"
    assert grs.count_lines([binary, missing]) == 1


def test_count_lines_multiple_files(tmp_path):
    a = tmp_path / "a.py"
    a.write_text("x\ny\n", encoding="utf-8")
    b = tmp_path / "b.py"
    b.write_text("p\nq\nr\n", encoding="utf-8")
    assert grs.count_lines([a, b]) == 5
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 4 failures (`AttributeError: module ... has no attribute 'count_lines'`)

- [ ] **Step 3: Implement `count_lines`**

Add to `scripts/generate_readme_stats.py` (above `main`):

```python
from typing import Iterable


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 5 PASS (smoke test + 4 new)

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): add count_lines() with wc -l semantics"
```

---

## Task 3: `count_test_functions()`

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
def test_count_test_functions_module_level(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text(
        "def test_one():\n    pass\n\n"
        "def test_two():\n    pass\n\n"
        "def helper():\n    pass\n",
        encoding="utf-8",
    )
    assert grs.count_test_functions([f]) == 2


def test_count_test_functions_async(tmp_path):
    f = tmp_path / "test_async.py"
    f.write_text(
        "async def test_a():\n    pass\n\n"
        "def test_b():\n    pass\n",
        encoding="utf-8",
    )
    assert grs.count_test_functions([f]) == 2


def test_count_test_functions_in_class(tmp_path):
    f = tmp_path / "test_class.py"
    f.write_text(
        "class TestThing:\n"
        "    def test_inside(self):\n        pass\n"
        "    def helper(self):\n        pass\n"
        "    async def test_async_inside(self):\n        pass\n",
        encoding="utf-8",
    )
    assert grs.count_test_functions([f]) == 2


def test_count_test_functions_skips_syntax_errors(tmp_path):
    bad = tmp_path / "test_bad.py"
    bad.write_text("def test_x(:\n    broken syntax", encoding="utf-8")
    good = tmp_path / "test_good.py"
    good.write_text("def test_y():\n    pass\n", encoding="utf-8")
    assert grs.count_test_functions([bad, good]) == 1


def test_count_test_functions_empty_list():
    assert grs.count_test_functions([]) == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 5 failures (no `count_test_functions`)

- [ ] **Step 3: Implement `count_test_functions`**

Add to `scripts/generate_readme_stats.py`:

```python
import ast


def count_test_functions(files: Iterable[Path]) -> int:
    """Count def/async def whose name starts with 'test_' across files.

    Uses AST so it works without importing the project. Walks the whole
    tree to catch class methods. Files that fail to parse are skipped.
    """
    total = 0
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    total += 1
    return total
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): add count_test_functions() via AST"
```

---

## Task 4: `tracked_files()` + `under()` filter

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
def test_under_unix_paths():
    files = [Path("backend/app/main.py"), Path("client/src/App.tsx"), Path("README.md")]
    result = grs.under(files, "backend/app/")
    assert result == [Path("backend/app/main.py")]


def test_under_normalizes_windows_paths():
    # git ls-files always emits forward slashes on Windows too — but defensively
    # we normalize, so a Path with backslashes still matches.
    files = [Path("backend\\app\\main.py")]
    result = grs.under(files, "backend/app/")
    assert result == files


def test_under_multiple_prefixes():
    files = [
        Path("backend/app/main.py"),
        Path("backend/tests/test_x.py"),
        Path("client/src/App.tsx"),
    ]
    result = grs.under(files, "backend/app/", "backend/tests/")
    assert len(result) == 2


def test_under_excludes_init_when_requested():
    files = [
        Path("backend/app/models/user.py"),
        Path("backend/app/models/__init__.py"),
    ]
    result = grs.under(files, "backend/app/models/", exclude_init=True)
    assert result == [Path("backend/app/models/user.py")]


def test_with_ext_filter():
    files = [Path("a.py"), Path("a.tsx"), Path("a.md")]
    assert grs.with_ext(files, ".py", ".tsx") == [Path("a.py"), Path("a.tsx")]


def test_tracked_files_parses_git_output(monkeypatch):
    def fake_check_output(cmd, **kw):
        assert cmd[:2] == ["git", "ls-files"]
        return "backend/app/main.py\nREADME.md\n\n"

    monkeypatch.setattr(grs.subprocess, "check_output", fake_check_output)
    files = grs.tracked_files()
    assert Path("backend/app/main.py") in files
    assert Path("README.md") in files
    assert len(files) == 2  # blank line dropped
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 6 failures

- [ ] **Step 3: Implement helpers**

Add to `scripts/generate_readme_stats.py`:

```python
import subprocess


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 16 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): add tracked_files() and path filters"
```

---

## Task 5: `compute_stats()` aggregator

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing test using a fixture file tree**

Append to test file:

```python
def _make_repo(tmp_path: Path) -> Path:
    """Create a fixture file tree mimicking BaluHost layout."""
    tree = {
        "backend/app/main.py": "x = 1\n",
        "backend/app/api/routes/auth.py": "def f():\n    pass\n",
        "backend/app/api/routes/files.py": "def g():\n    pass\n",
        "backend/app/api/routes/__init__.py": "",
        "backend/app/services/auth.py": "def h():\n    pass\n",
        "backend/app/services/files/upload.py": "def i():\n    pass\n",
        "backend/app/services/__init__.py": "",
        "backend/app/services/files/__init__.py": "",
        "backend/app/models/user.py": "class User: ...\n",
        "backend/app/models/__init__.py": "",
        "backend/tests/test_one.py": "def test_a():\n    pass\n",
        "backend/tests/test_two.py": "def test_b():\n    pass\n\ndef test_c():\n    pass\n",
        "backend/scripts/foo.py": "print('hi')\n",
        "backend/alembic/versions/0001_init.py": "# rev\n",
        "backend/alembic/versions/0002_add.py": "# rev\n",
        "backend/baluhost_tui/main.py": "pass\n",
        "client/src/App.tsx": "export const X = 1;\n",
        "client/src/pages/Dashboard.tsx": "export default 1;\n",
        "client/src/pages/Settings.tsx": "export default 2;\n",
        "client/src/lib/api.ts": "export {};\n",
        "client/src/styles.css": "body{}\n",
        ".github/workflows/ci.yml": "name: ci\n",
        ".github/workflows/release.yml": "name: rel\n",
    }
    for rel, content in tree.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


def test_compute_stats_counts_match_fixture(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(grs, "ROOT", repo)
    files = [Path(rel) for rel in [
        "backend/app/main.py",
        "backend/app/api/routes/auth.py",
        "backend/app/api/routes/files.py",
        "backend/app/api/routes/__init__.py",
        "backend/app/services/auth.py",
        "backend/app/services/files/upload.py",
        "backend/app/services/__init__.py",
        "backend/app/services/files/__init__.py",
        "backend/app/models/user.py",
        "backend/app/models/__init__.py",
        "backend/tests/test_one.py",
        "backend/tests/test_two.py",
        "backend/scripts/foo.py",
        "backend/alembic/versions/0001_init.py",
        "backend/alembic/versions/0002_add.py",
        "backend/baluhost_tui/main.py",
        "client/src/App.tsx",
        "client/src/pages/Dashboard.tsx",
        "client/src/pages/Settings.tsx",
        "client/src/lib/api.ts",
        "client/src/styles.css",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ]]

    s = grs.compute_stats(files)

    assert s.api_route_modules == 2  # __init__ excluded
    assert s.service_modules == 2    # __init__ excluded, both auth.py + upload.py
    assert s.db_models == 1          # __init__ excluded
    assert s.db_migrations == 2
    assert s.frontend_pages == 2
    assert s.workflows == 2
    assert s.test_functions == 3     # 1 + 2

    assert s.backend_app.files == 10  # all .py under backend/app/
    assert s.backend_tests.files == 2
    assert s.backend_scripts.files == 1
    assert s.backend_alembic.files == 2
    assert s.backend_tui.files == 1
    assert s.backend_total.files == 16  # sum of subdirs

    assert s.frontend.files == 5  # .tsx, .ts, .css under client/src/
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `python -m pytest scripts/test_generate_readme_stats.py::test_compute_stats_counts_match_fixture -v`
Expected: FAIL — `compute_stats` not defined

- [ ] **Step 3: Implement dataclasses + compute_stats**

Add to `scripts/generate_readme_stats.py`:

```python
from dataclasses import dataclass


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
        db_migrations=len(under(py, "backend/alembic/versions/", exclude_init=True)),
        frontend_pages=len(under(with_ext(files, ".tsx"), "client/src/pages/")),
        workflows=len(under(
            with_ext(files, ".yml", ".yaml"),
            ".github/workflows/",
        )),
    )
```

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 17 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): add compute_stats() aggregator"
```

---

## Task 6: `render_project_stats_block()` and `render_test_count()` / `render_test_files()`

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
def _stub_stats() -> grs.Stats:
    return grs.Stats(
        backend_total=grs.Bucket(files=735, lines=150_685),
        backend_app=grs.Bucket(files=411, lines=97_186),
        backend_tests=grs.Bucket(files=166, lines=38_309),
        backend_scripts=grs.Bucket(files=48, lines=6_291),
        backend_alembic=grs.Bucket(files=92, lines=5_989),
        backend_tui=grs.Bucket(files=18, lines=2_910),
        frontend=grs.Bucket(files=427, lines=78_107),
        test_functions=1465,
        api_route_modules=51,
        service_modules=143,
        db_models=42,
        db_migrations=74,
        frontend_pages=31,
        workflows=7,
    )


def test_render_project_stats_block_contains_all_rows():
    md = grs.render_project_stats_block(_stub_stats())
    assert "150,685 lines across 735 Python files" in md
    assert "97,186 lines / 411 files" in md
    assert "38,309 lines / 166 files" in md
    assert "78,107 lines across 427 source files" in md
    assert "| **Test functions** | 1465 |" in md
    assert "| **API route modules** | 51 |" in md
    assert "| **Service modules** | 143 |" in md
    assert "| **Database models** | 42 |" in md
    assert "| **Database migrations** | 74 |" in md
    assert "| **Frontend pages** | 31 |" in md
    assert "| **CI/CD workflows** | 7 |" in md


def test_render_project_stats_block_includes_measured_date():
    md = grs.render_project_stats_block(_stub_stats(), measured="2026-05-06")
    assert "Last measured 2026-05-06" in md


def test_render_test_count():
    assert grs.render_test_count(_stub_stats()) == "1465 tests"


def test_render_test_files():
    assert grs.render_test_files(_stub_stats()) == "166 test files"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 4 failures

- [ ] **Step 3: Implement render functions**

Add to `scripts/generate_readme_stats.py`:

```python
from datetime import date


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 21 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): render markdown for project stats and inline test counts"
```

---

## Task 7: `replace_between_markers()`

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to test file:

```python
def test_replace_between_markers_block():
    text = (
        "intro\n"
        "<!-- STATS:PROJECT:START -->\n"
        "old content here\n"
        "more old\n"
        "<!-- STATS:PROJECT:END -->\n"
        "outro\n"
    )
    out = grs.replace_between_markers(text, "PROJECT", "NEW BLOCK")
    assert (
        "<!-- STATS:PROJECT:START -->\nNEW BLOCK\n<!-- STATS:PROJECT:END -->" in out
    )
    assert "old content" not in out
    assert "intro\n" in out and "outro\n" in out


def test_replace_between_markers_inline():
    text = "Row | <!-- STATS:TC:START -->old<!-- STATS:TC:END --> | rest"
    out = grs.replace_between_markers(text, "TC", "new", inline=True)
    assert "<!-- STATS:TC:START -->new<!-- STATS:TC:END -->" in out
    assert "old" not in out


def test_replace_between_markers_idempotent():
    text = (
        "<!-- STATS:X:START -->\nfoo\n<!-- STATS:X:END -->"
    )
    once = grs.replace_between_markers(text, "X", "bar")
    twice = grs.replace_between_markers(once, "X", "bar")
    assert once == twice


def test_replace_between_markers_missing_raises():
    text = "no markers here"
    try:
        grs.replace_between_markers(text, "MISSING", "x")
    except ValueError as e:
        assert "MISSING" in str(e)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 4 failures

- [ ] **Step 3: Implement `replace_between_markers`**

Add to `scripts/generate_readme_stats.py`:

```python
import re


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 25 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): add idempotent marker-based text splice"
```

---

## Task 8: Wire CLI `main()` + end-to-end smoke test

**Files:**
- Modify: `scripts/generate_readme_stats.py`
- Modify: `scripts/test_generate_readme_stats.py`

- [ ] **Step 1: Write the failing end-to-end test**

Append to test file:

```python
def test_apply_to_text_replaces_three_marker_pairs():
    template = (
        "before\n"
        "<!-- STATS:PROJECT:START -->\n"
        "OLD TABLE\n"
        "<!-- STATS:PROJECT:END -->\n"
        "row | <!-- STATS:TEST_COUNT:START -->old<!-- STATS:TEST_COUNT:END --> | "
        "<!-- STATS:TEST_FILES:START -->old<!-- STATS:TEST_FILES:END -->,\n"
        "after\n"
    )
    s = _stub_stats()
    out = grs.apply_to_text(template, s, measured="2026-05-06")

    assert "OLD TABLE" not in out
    assert "150,685 lines across 735" in out
    assert "1465 tests" in out
    assert "166 test files" in out
    assert "Last measured 2026-05-06" in out


def test_apply_to_text_idempotent():
    template = (
        "<!-- STATS:PROJECT:START -->\nx\n<!-- STATS:PROJECT:END -->\n"
        "<!-- STATS:TEST_COUNT:START -->x<!-- STATS:TEST_COUNT:END -->\n"
        "<!-- STATS:TEST_FILES:START -->x<!-- STATS:TEST_FILES:END -->\n"
    )
    once = grs.apply_to_text(template, _stub_stats(), measured="2026-05-06")
    twice = grs.apply_to_text(once, _stub_stats(), measured="2026-05-06")
    assert once == twice
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 2 failures (no `apply_to_text`)

- [ ] **Step 3: Implement `apply_to_text` and complete `main`**

Add to `scripts/generate_readme_stats.py`:

```python
def apply_to_text(readme_text: str, stats: Stats, *, measured: str | None = None) -> str:
    """Apply all three marker replacements to a README body."""
    out = replace_between_markers(
        readme_text, "PROJECT", render_project_stats_block(stats, measured=measured)
    )
    out = replace_between_markers(
        out, "TEST_COUNT", render_test_count(stats), inline=True
    )
    out = replace_between_markers(
        out, "TEST_FILES", render_test_files(stats), inline=True
    )
    return out
```

Replace the placeholder `main()` with:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Rewrite README.md in place")
    mode.add_argument("--check", action="store_true", help="Exit 1 if README would change")
    args = parser.parse_args()

    if not args.write and not args.check:
        args.check = True

    files = tracked_files()
    stats = compute_stats(files)
    current = README.read_text(encoding="utf-8")
    new = apply_to_text(current, stats)

    if new == current:
        print("README stats up to date.")
        return 0

    if args.write:
        README.write_text(new, encoding="utf-8")
        print("README.md updated.")
        return 0

    # check mode
    print("README stats are out of date. Run with --write to update.", file=sys.stderr)
    return 1
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 27 PASS

- [ ] **Step 5: Run script in --check mode against the current README (will fail until Task 9 adds markers)**

Run: `python scripts/generate_readme_stats.py --check`
Expected: exit code 1 with `ValueError: Marker pair STATS:PROJECT not found` — confirms the script is wired but the README has no markers yet. This is the expected state at this point in the plan.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_readme_stats.py scripts/test_generate_readme_stats.py
git commit -m "feat(stats): wire CLI main with --check and --write modes"
```

---

## Task 9: Add markers to README and remove inline architecture counts

**Files:**
- Modify: `README.md` (add 3 marker pairs, strip 7 inline numbers from architecture tree, drop the obsolete `Last measured 2026-04-30` sub-note since it now lives inside the generated block)

- [ ] **Step 1: Add inline markers around the test count and test files in the Production Status row**

In `README.md` line 32, replace:
```markdown
| **Testing** | 1465 tests | 82 test files, CI/CD via GitHub Actions |
```
with:
```markdown
| **Testing** | <!-- STATS:TEST_COUNT:START -->1465 tests<!-- STATS:TEST_COUNT:END --> | <!-- STATS:TEST_FILES:START -->82 test files<!-- STATS:TEST_FILES:END -->, CI/CD via GitHub Actions |
```

- [ ] **Step 2: Strip inline counts from the Architecture tree (lines 167–197)**

In `README.md`, replace:
```markdown
│   │   ├── api/routes/      # 51 API route modules
│   │   ├── services/        # 143 service modules
│   │   ├── models/          # 42 SQLAlchemy ORM models
│   │   ├── schemas/         # 41 Pydantic schemas
```
with:
```markdown
│   │   ├── api/routes/      # API route modules
│   │   ├── services/        # Service modules
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic schemas
```

Replace:
```markdown
│   ├── tests/               # 82 test files
│   └── alembic/             # 74 database migrations
```
with:
```markdown
│   ├── tests/               # Pytest suite
│   └── alembic/             # Database migrations
```

Replace:
```markdown
│       ├── pages/           # 31 page components
│       ├── components/      # 30+ component directories
```
with:
```markdown
│       ├── pages/           # Page components
│       ├── components/      # Reusable components
```

(The `30+ component directories` line was already approximate; we drop it because we are not generating that count. If we want to add it later, extend `compute_stats`.)

- [ ] **Step 3: Wrap the Project Stats block with markers and remove the standalone "Last measured" sub-note**

In `README.md`, replace lines 309–329 (the `## Project Stats` section through the `<sub>` line) with:

```markdown
## Project Stats

<!-- STATS:PROJECT:START -->
| Metric | Count |
|--------|-------|
| **Version** | ![Latest Release](https://img.shields.io/github/v/release/Xveyn/BaluHost?label=) |
| **Backend code** | (regenerated by scripts/generate_readme_stats.py) |
<!-- STATS:PROJECT:END -->
```

The placeholder line will be overwritten by the script in Step 4 — we just need valid marker structure for the script to splice into.

- [ ] **Step 4: Regenerate the README**

Run: `python scripts/generate_readme_stats.py --write`
Expected stdout: `README.md updated.`

- [ ] **Step 5: Verify the result**

Run: `python scripts/generate_readme_stats.py --check`
Expected stdout: `README stats up to date.` (exit 0)

Run: `git diff README.md` and visually verify:
- Project Stats table has real numbers
- Production Status testing row has real numbers wrapped in markers
- Architecture tree has no inline numbers

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs(readme): wire stats markers and remove inline counts from architecture tree"
```

---

## Task 10: Wire script into auto-merge.yml release workflow

**Files:**
- Modify: `.github/workflows/auto-merge.yml:57-75` (the "Bump version from release label" step)

- [ ] **Step 1: Read current step body**

Open `.github/workflows/auto-merge.yml`. Locate the step beginning at line 57:

```yaml
      - name: Bump version from release label
        if: env.RELEASE_LABEL != ''
        working-directory: /tmp/repo
        run: |
          BUMP_TYPE="${RELEASE_LABEL#release:}"
          echo "Release label: $RELEASE_LABEL → bump type: $BUMP_TYPE"

          CURRENT_VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          echo "Current version: $CURRENT_VERSION"

          python3 scripts/bump_version.py "$BUMP_TYPE"

          NEW_VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          echo "New version: $NEW_VERSION"
          echo "NEW_VERSION=$NEW_VERSION" >> "$GITHUB_ENV"

          git add backend/pyproject.toml client/package.json CLAUDE.md
          git commit -m "chore: bump version to v${NEW_VERSION}"
          git push origin main
```

- [ ] **Step 2: Modify the step to regenerate stats and include README in the commit**

Replace the step body with:

```yaml
      - name: Bump version from release label
        if: env.RELEASE_LABEL != ''
        working-directory: /tmp/repo
        run: |
          BUMP_TYPE="${RELEASE_LABEL#release:}"
          echo "Release label: $RELEASE_LABEL → bump type: $BUMP_TYPE"

          CURRENT_VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          echo "Current version: $CURRENT_VERSION"

          python3 scripts/bump_version.py "$BUMP_TYPE"

          NEW_VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          echo "New version: $NEW_VERSION"
          echo "NEW_VERSION=$NEW_VERSION" >> "$GITHUB_ENV"

          # Regenerate README stats (counts only tracked files via git ls-files)
          python3 scripts/generate_readme_stats.py --write

          git add backend/pyproject.toml client/package.json CLAUDE.md README.md
          git commit -m "chore: bump version to v${NEW_VERSION}"
          git push origin main
```

The change is two lines: one comment + the script invocation, and adding `README.md` to the `git add` list. If stats didn't change, `git add README.md` is a no-op and the commit still works.

- [ ] **Step 3: Verify the YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/auto-merge.yml'))"`
Expected: no output (success). If `yaml` is not installed, fall back to:
Run: `python -c "import json,subprocess; subprocess.check_call(['python','-c','open(\".github/workflows/auto-merge.yml\").read()'])"`

- [ ] **Step 4: Run the full test suite once more**

Run: `python -m pytest scripts/test_generate_readme_stats.py -v`
Expected: 27 PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/auto-merge.yml
git commit -m "ci(release): regenerate README stats during version bump"
```

---

## Self-Review Notes

**Spec coverage:**
- "Don't track gitignored files" → Task 4 uses `git ls-files` exclusively. ✓
- "No dependencies" → script imports only stdlib (`argparse`, `ast`, `dataclasses`, `datetime`, `pathlib`, `re`, `subprocess`, `sys`, `typing`). Tests use only pytest (existing dev dep). ✓
- "Bei zukünftigen releases (und pre-releases)" → Task 10 wires into `auto-merge.yml` which fires on every release-label PR merge to `main`, including pre-release versions (`-alpha`/`-beta`/`-rc` suffixes). ✓
- "Sauber" → tasks remove inline architecture counts (single source of truth), add idempotent marker splice, full TDD coverage. ✓

**Type consistency:** all functions use names introduced earlier — `count_lines`, `count_test_functions`, `tracked_files`, `under`, `with_ext`, `compute_stats`, `Bucket`, `Stats`, `render_project_stats_block`, `render_test_count`, `render_test_files`, `replace_between_markers`, `apply_to_text`, `main`. No drift.

**Placeholder scan:** No TBDs. Each step has full code or full command. The README placeholder line in Task 9 Step 3 is intentional — it gets overwritten by Step 4 in the same task.

**Skip list confirmed:**
- We do NOT count `dependencies` (e.g., `node_modules/`, `.venv/`, vendored libs) — `git ls-files` excludes them.
- We do NOT count `.metadata.json`, `dev-storage/`, `dist/`, `htmlcov/` — all gitignored.
- We do NOT touch `CLAUDE.md` Version line — that's already handled by `bump_version.py`.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-06-readme-stats-automation.md`.
