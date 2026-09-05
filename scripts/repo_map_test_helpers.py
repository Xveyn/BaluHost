"""Shared test fixtures for scripts/test_repo_map.py and test_repo_map_html.py.

`make_entry` builds a FileEntry via the real analysis path, so both sides of
the test split exercise actual behaviour rather than a hand-rolled stub.
"""
from __future__ import annotations

import repo_map_metrics as metrics


def make_entry(path: str, text: str, **kwargs):
    kwargs.setdefault("thresholds", metrics.Thresholds())
    return metrics.analyze_file(path, text, **kwargs)
