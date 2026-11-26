"""Unit tests for the collector's attribute status mapping (#873)."""
from __future__ import annotations

import pytest

from app.services.hardware.smart.collector import _attribute_status


@pytest.mark.parametrize(
    ("when_failed", "expected"),
    [
        (None, "OK"),
        ("", "OK"),
        ("-", "OK"),
        ("  ", "OK"),
        ("past", "PAST"),
        ("In_the_past", "PAST"),
        ("PAST", "PAST"),
        ("now", "FAILING"),
        ("FAILING_NOW", "FAILING"),
        ("something-new", "FAILING"),
    ],
)
def test_attribute_status(when_failed, expected):
    assert _attribute_status(when_failed) == expected
