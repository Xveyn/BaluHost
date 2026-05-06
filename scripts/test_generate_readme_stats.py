"""Tests for scripts/generate_readme_stats.py — stdlib + pytest only."""
from __future__ import annotations

from pathlib import Path

import generate_readme_stats as grs


def test_module_imports():
    assert hasattr(grs, "main")


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


def test_count_test_functions_skips_missing_file(tmp_path):
    missing = tmp_path / "does-not-exist.py"
    good = tmp_path / "test_good.py"
    good.write_text("def test_y():\n    pass\n", encoding="utf-8")
    assert grs.count_test_functions([missing, good]) == 1


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


def test_count_lines_resolves_relative_against_ROOT(tmp_path, monkeypatch):
    """count_lines should open relative paths against ROOT, not process cwd."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.py").write_text("a\nb\n", encoding="utf-8")
    monkeypatch.setattr(grs, "ROOT", repo)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert grs.count_lines([Path("file.py")]) == 2


def test_count_test_functions_resolves_relative_against_ROOT(tmp_path, monkeypatch):
    """count_test_functions should open relative paths against ROOT, not process cwd."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_x.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(grs, "ROOT", repo)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert grs.count_test_functions([Path("test_x.py")]) == 1


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
        "backend/alembic/env.py": "# alembic env\n",
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
        "backend/alembic/env.py",
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
    assert s.db_migrations == 2      # only versions/, env.py excluded
    assert s.frontend_pages == 2
    assert s.workflows == 2
    assert s.test_functions == 3     # 1 + 2

    assert s.backend_app.files == 10  # all .py under backend/app/
    assert s.backend_tests.files == 2
    assert s.backend_scripts.files == 1
    assert s.backend_alembic.files == 3  # versions/ + env.py — broader than db_migrations
    assert s.backend_tui.files == 1
    assert s.backend_total.files == 17  # sum of subdirs

    assert s.frontend.files == 5  # .tsx, .ts, .css under client/src/


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
