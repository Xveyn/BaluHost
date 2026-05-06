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
