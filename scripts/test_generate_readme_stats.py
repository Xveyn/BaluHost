"""Tests for scripts/generate_readme_stats.py — stdlib + pytest only."""
from __future__ import annotations

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
