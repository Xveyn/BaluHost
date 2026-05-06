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
