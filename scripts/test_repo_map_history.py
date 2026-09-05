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


class TestGitTreeSource:
    def test_reads_content_as_it_was_at_that_commit(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "old = 1\n", date="2026-01-10")
        old = git(repo, "rev-parse", "HEAD").strip()
        commit_file(repo, "a.py", "new = 2\n", date="2026-02-10")

        source = history.GitTreeSource(repo, old)

        assert source.read("a.py") == "old = 1\n"

    def test_paths_lists_the_tree_at_that_commit(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        commit_file(repo, "sub/b.py", "2\n", date="2026-01-11")
        source = history.GitTreeSource(repo, "HEAD")
        assert sorted(source.paths()) == ["a.py", "sub/b.py"]

    def test_identity_is_the_blob_sha_so_equal_content_shares_a_key(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "same\n", date="2026-01-10")
        commit_file(repo, "b.py", "same\n", date="2026-01-11")
        source = history.GitTreeSource(repo, "HEAD")
        assert source.identity("a.py") == source.identity("b.py")

    def test_unknown_path_reads_as_none(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        assert history.GitTreeSource(repo, "HEAD").read("gone.py") is None

    def test_binary_blob_reads_as_none(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo / "b.bin").write_bytes(b"\xff\xfe\x00\x01\x80")
        git(repo, "add", "b.bin")
        commit_all(repo, "bin")
        assert history.GitTreeSource(repo, "HEAD").read("b.bin") is None

    def test_prefetch_serves_many_files_without_deadlocking(self, tmp_path):
        """The naive 'write every sha, then read' fills the pipe buffer and
        hangs. 300 files is enough to blow past that buffer if it regresses."""
        repo = make_repo(tmp_path)
        for i in range(300):
            (repo / f"f{i}.py").write_text(f"x = {i}\n" * 40, encoding="utf-8")
        git(repo, "add", "-A")
        commit_all(repo, "many")

        source = history.GitTreeSource(repo, "HEAD")
        source.prefetch(source.paths())

        assert source.read("f0.py") == "x = 0\n" * 40
        assert source.read("f299.py") == "x = 299\n" * 40

    def test_prefetch_leaves_already_known_content_alone(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        source = history.GitTreeSource(repo, "HEAD")
        assert source.read("a.py") == "1\n"
        source.prefetch(["a.py"])
        assert source.read("a.py") == "1\n"
