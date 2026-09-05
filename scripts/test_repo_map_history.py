"""Tests for the repo map's history mode."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import repo_map_history as history


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8", errors="replace"
    )


def make_repo(tmp_path: Path) -> Path:
    """A throwaway repo with pinned identity, so tests never depend on the
    developer's global git config."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def commit_all(repo: Path, message: str, *, date: str | None = None) -> None:
    """Commit whatever is staged, at a fixed author AND committer date."""
    env = dict(os.environ)
    args = ["git", "commit", "-q", "-m", message]
    if date is not None:
        stamp = f"{date}T12:00:00"
        env["GIT_COMMITTER_DATE"] = stamp
        args += ["--date", stamp]
    subprocess.check_call(args, cwd=repo, env=env)


def commit_file(repo: Path, path: str, text: str, *, date: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(repo, "add", path)
    commit_all(repo, f"touch {path}", date=date)


class TestPeriodLabel:
    def test_monthly_label_is_year_and_month(self):
        assert history.period_label("2026-09-05", "monthly") == "2026-09"

    def test_weekly_label_is_iso_year_and_week(self):
        assert history.period_label("2026-09-05", "weekly") == "2026-W36"

    def test_unknown_interval_is_rejected(self):
        with pytest.raises(ValueError):
            history.period_label("2026-09-05", "hourly")


class TestSelectSnapshots:
    def test_one_snapshot_per_month_and_it_is_the_last_one(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "x = 1\n", date="2026-01-10")
        commit_file(repo, "a.py", "x = 2\n", date="2026-01-20")
        commit_file(repo, "a.py", "x = 3\n", date="2026-02-05")

        snaps = history.select_snapshots(repo, interval="monthly")

        assert [s.label for s in snaps] == ["2026-01", "2026-02"]
        assert snaps[0].date == "2026-01-20", "must take the LAST commit of the month"

    def test_snapshots_come_back_oldest_first(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        commit_file(repo, "a.py", "2\n", date="2026-03-10")
        snaps = history.select_snapshots(repo, interval="monthly")
        assert [s.date for s in snaps] == ["2026-01-10", "2026-03-10"]

    def test_since_clips_the_range(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        commit_file(repo, "a.py", "2\n", date="2026-03-10")
        snaps = history.select_snapshots(repo, interval="monthly", since="2026-02-01")
        assert [s.label for s in snaps] == ["2026-03"]

    def test_empty_range_yields_no_snapshots(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        assert history.select_snapshots(repo, interval="monthly", since="2027-01-01") == []
