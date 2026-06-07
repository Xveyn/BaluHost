"""Tests for the type-to-confirm helper used by ConfirmDialog."""
from __future__ import annotations

from baluhost_tui.widgets.confirm import confirm_matches


def test_exact_match():
    assert confirm_matches("md0", "md0") is True


def test_trims_whitespace_around_typed():
    assert confirm_matches("md0", "  md0  ") is True


def test_mismatch():
    assert confirm_matches("md0", "md1") is False


def test_empty_typed_against_nonempty_expected():
    assert confirm_matches("md0", "") is False


def test_case_sensitive():
    assert confirm_matches("md0", "MD0") is False
