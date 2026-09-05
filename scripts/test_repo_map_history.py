"""Tests for the repo map's history mode."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import repo_map
import repo_map_history as history
import repo_map_html
import repo_map_metrics as metrics


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

    def test_non_ascii_filename_comes_back_unquoted(self, tmp_path):
        """Under git's default core.quotePath, ls-tree without -z renders a
        non-ASCII path as an octal-escaped, double-quoted string (e.g.
        '"\\342\\234\\205 done.txt"'). -z disables that quoting, so the path
        parsed out of GitTreeSource must be the plain original string."""
        repo = make_repo(tmp_path)
        commit_file(repo, "sub/✅ done.txt", "x\n", date="2026-01-10")

        source = history.GitTreeSource(repo, "HEAD")

        assert "sub/✅ done.txt" in source.paths()
        assert source.read("sub/✅ done.txt") == "x\n"

    def test_prefetch_leaves_already_known_content_alone(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        source = history.GitTreeSource(repo, "HEAD")
        assert source.read("a.py") == "1\n"
        source.prefetch(["a.py"])
        assert source.read("a.py") == "1\n"


class TestSplitRename:
    def test_plain_path_has_no_old_name(self):
        assert history.split_rename("a/b.py") == ("a/b.py", None)

    def test_plain_rename(self):
        assert history.split_rename("a.py => b.py") == ("b.py", "a.py")

    def test_braced_rename_inside_a_directory(self):
        assert history.split_rename("src/{old.py => new.py}") == (
            "src/new.py",
            "src/old.py",
        )

    def test_braced_rename_that_moves_into_a_new_directory(self):
        assert history.split_rename("{ => sub}/a.py") == ("sub/a.py", "a.py")

    def test_braced_rename_that_moves_out_of_a_directory(self):
        assert history.split_rename("{sub => }/a.py") == ("a.py", "sub/a.py")


class TestCollectChurn:
    def test_counts_commits_and_line_deltas(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        commit_file(repo, "a.py", "1\n2\n3\n", date="2026-01-11")

        churn = history.collect_churn(repo)

        assert churn["a.py"].commits == 2
        assert churn["a.py"].added == 3
        assert churn["a.py"].deleted == 0

    def test_last_date_is_the_most_recent_touch(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        commit_file(repo, "a.py", "2\n", date="2026-03-20")
        assert history.collect_churn(repo)["a.py"].last_date == "2026-03-20"

    def test_history_survives_a_rename_under_the_new_name(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "old.py", "1\n", date="2026-01-10")
        git(repo, "mv", "old.py", "new.py")
        commit_all(repo, "rename", date="2026-01-11")
        commit_file(repo, "new.py", "1\n2\n", date="2026-01-12")

        churn = history.collect_churn(repo)

        assert "old.py" not in churn, "the old name must not survive as its own row"
        assert churn["new.py"].commits == 3, "all three commits belong to this file"

    def test_history_survives_a_double_rename_under_the_final_name(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        git(repo, "mv", "a.py", "b.py")
        commit_all(repo, "rename a to b", date="2026-01-11")
        commit_file(repo, "b.py", "1\n2\n", date="2026-01-12")
        git(repo, "mv", "b.py", "c.py")
        commit_all(repo, "rename b to c", date="2026-01-13")

        churn = history.collect_churn(repo)

        assert "a.py" not in churn, "the first name must not survive as its own row"
        assert "b.py" not in churn, "the intermediate name must not survive as its own row"
        assert churn["c.py"].commits == 4, "all four commits belong to this file"

    def test_binary_changes_count_as_a_commit_with_no_line_delta(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo / "b.bin").write_bytes(b"\x00\x01\x02")
        git(repo, "add", "b.bin")
        commit_all(repo, "bin", date="2026-01-10")

        churn = history.collect_churn(repo)

        assert churn["b.bin"].commits == 1
        assert churn["b.bin"].added == 0
        assert churn["b.bin"].deleted == 0

    def test_since_clips_the_range(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        commit_file(repo, "a.py", "2\n", date="2026-03-10")
        churn = history.collect_churn(repo, since="2026-02-01")
        assert churn["a.py"].commits == 1


class TestClassifyArea:
    def test_backend_tests_wins_over_backend(self):
        assert history.classify_area("backend/tests/test_x.py") == "backend/tests"

    def test_backend_app_catches_the_rest_of_backend(self):
        assert history.classify_area("backend/app/services/x.py") == "backend/app"

    def test_backend_non_app_subdirs_land_in_the_rest_bucket(self):
        """backend/app must measure exactly that directory, not all of
        backend/ - alembic, scripts and baluhost_tui live under backend/ too
        but are not part of the FastAPI app."""
        assert history.classify_area("backend/alembic/versions/x.py") == history.REST_AREA
        assert history.classify_area("backend/scripts/debug/reset.py") == history.REST_AREA
        assert history.classify_area("backend/baluhost_tui/app.py") == history.REST_AREA

    def test_client_source(self):
        assert history.classify_area("client/src/pages/X.tsx") == "client/src"

    def test_docs(self):
        assert history.classify_area("docs/ARCHITECTURE.md") == "docs"

    def test_anything_else_lands_in_the_rest_bucket(self):
        assert history.classify_area("scripts/repo_map.py") == history.REST_AREA

    def test_rest_bucket_is_part_of_the_area_list(self):
        assert history.REST_AREA in history.AREAS


class TestFlaggedThreshold:
    def test_matches_the_renderer_so_the_series_and_the_card_agree(self):
        assert history.FLAGGED_SCORE == repo_map_html.CANDIDATE_SCORE


class TestBuildHistory:
    def test_one_point_per_snapshot_oldest_first(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "backend/app/a.py", "x = 1\n", date="2026-01-10")
        commit_file(repo, "backend/app/a.py", "x = 1\ny = 2\n", date="2026-02-10")

        snaps = history.select_snapshots(repo, interval="monthly")
        points = history.build_history(repo, snaps, thresholds=metrics.Thresholds())

        assert [p.label for p in points] == ["2026-01", "2026-02"]
        assert points[0].loc == 1
        assert points[1].loc == 2

    def test_area_totals_sum_to_the_overall_loc(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "backend/app/a.py", "1\n", date="2026-01-10")
        commit_file(repo, "backend/tests/t.py", "1\n2\n", date="2026-01-11")
        commit_file(repo, "scripts/s.py", "1\n2\n3\n", date="2026-01-12")

        points = history.build_history(
            repo,
            history.select_snapshots(repo, interval="monthly"),
            thresholds=metrics.Thresholds(),
        )

        point = points[-1]
        assert sum(point.areas.values()) == point.loc
        assert point.areas["backend/tests"] == 2
        assert point.areas[history.REST_AREA] == 3

    def test_directory_rollup_reaches_every_ancestor(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "backend/app/services/a.py", "1\n2\n", date="2026-01-10")

        point = history.build_history(
            repo,
            history.select_snapshots(repo, interval="monthly"),
            thresholds=metrics.Thresholds(),
        )[-1]

        assert point.dirs[""] == 2, "root carries the total"
        assert point.dirs["backend"] == 2
        assert point.dirs["backend/app/services"] == 2

    def test_flagged_counts_files_over_the_threshold(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "big.py", "x = 1\n" * 40, date="2026-01-10")

        points = history.build_history(
            repo,
            history.select_snapshots(repo, interval="monthly"),
            thresholds=metrics.Thresholds(max_loc=10),
        )

        assert points[-1].flagged == 1
        assert points[-1].score_sum > 0

    def test_unchanged_files_are_analysed_once_across_snapshots(self, tmp_path):
        """The blob cache is the whole reason history mode is affordable."""
        repo = make_repo(tmp_path)
        commit_file(repo, "stable.py", "x = 1\n", date="2026-01-10")
        commit_file(repo, "other.py", "y = 2\n", date="2026-02-10")

        calls = []
        original = repo_map.analyze_file

        def counting(path, text, **kwargs):
            calls.append(path)
            return original(path, text, **kwargs)

        repo_map.analyze_file = counting
        try:
            history.build_history(
                repo,
                history.select_snapshots(repo, interval="monthly"),
                thresholds=metrics.Thresholds(),
            )
        finally:
            repo_map.analyze_file = original

        assert calls.count("stable.py") == 1, "unchanged blob must not be re-analysed"

    def test_no_snapshots_yields_no_points(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        assert history.build_history(repo, [], thresholds=metrics.Thresholds()) == []


class TestHistoryJson:
    def test_carries_points_and_churn(self, tmp_path):
        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        points = history.build_history(
            repo,
            history.select_snapshots(repo, interval="monthly"),
            thresholds=metrics.Thresholds(),
        )
        churn = history.collect_churn(repo)

        payload = history.history_json(points, churn)

        assert payload["areas"] == list(history.AREAS)
        assert payload["points"][0]["label"] == "2026-01"
        assert payload["churn"]["a.py"]["commits"] == 1

    def test_is_json_serialisable(self, tmp_path):
        import json

        repo = make_repo(tmp_path)
        commit_file(repo, "a.py", "1\n", date="2026-01-10")
        points = history.build_history(
            repo,
            history.select_snapshots(repo, interval="monthly"),
            thresholds=metrics.Thresholds(),
        )
        json.dumps(history.history_json(points, history.collect_churn(repo)))
