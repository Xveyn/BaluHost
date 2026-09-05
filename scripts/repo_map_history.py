#!/usr/bin/env python3
"""History mode for the repo map: metric series over git snapshots.

Everything is reconstructed from git on every run - no stored state, so
nothing can drift. What makes that affordable is git's own deduplication:
unchanged files share a blob across commits, so each file version is
analysed exactly once.
"""
from __future__ import annotations

import datetime as _dt
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

INTERVALS = ("monthly", "weekly")


@dataclass(frozen=True)
class Snapshot:
    """One point on the time axis: the last commit of a period."""

    commit: str
    date: str
    label: str


def period_label(date: str, interval: str) -> str:
    """Bucket an ISO date into the period it belongs to."""
    if interval == "monthly":
        return date[:7]
    if interval == "weekly":
        year, month, day = (int(part) for part in date.split("-"))
        iso_year, iso_week, _ = _dt.date(year, month, day).isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    raise ValueError(f"unknown interval: {interval!r} (expected one of {INTERVALS})")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace"
    )


def select_snapshots(
    root: Path, *, interval: str = "monthly", since: str | None = None
) -> list[Snapshot]:
    """Pick the last commit of each period, oldest first.

    Walks --first-parent so the series reflects the state of the mainline
    rather than whichever feature-branch commit happened to land last.
    """
    args = ["log", "--first-parent", "--format=%H %as"]
    if since:
        args.append(f"--since={since}")
    out = _git(root, *args)

    seen: dict[str, Snapshot] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        commit, _, date = line.partition(" ")
        if not date:
            continue
        label = period_label(date, interval)
        # git log runs newest-first, so the first hit for a period is that
        # period's last commit; older hits must not overwrite it.
        seen.setdefault(label, Snapshot(commit=commit, date=date, label=label))

    return sorted(seen.values(), key=lambda s: s.date)
