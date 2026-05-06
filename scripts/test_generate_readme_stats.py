"""Tests for scripts/generate_readme_stats.py — stdlib + pytest only."""
from __future__ import annotations

import generate_readme_stats as grs


def test_module_imports():
    assert hasattr(grs, "main")
