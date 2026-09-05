"""Tests for scripts/repo_map_html.py."""
from __future__ import annotations

import repo_map
import repo_map_html
import repo_map_metrics as metrics
from repo_map_test_helpers import make_entry


def make_report(entries=None, commit="abc1234"):
    entries = list(entries or [])
    return repo_map.Report(
        commit=commit,
        generated_at="2026-09-05T10:00:00",
        thresholds=metrics.Thresholds(),
        entries=entries,
        tree=repo_map.build_tree(entries),
    )


class TestBuildPayload:
    def test_files_are_ordered_by_score_descending(self):
        entries = [
            make_entry("small.py", "x = 1\n"),
            make_entry("huge.py", "x = 1\n" * 2000),
            make_entry("medium.py", "x = 1\n" * 700),
        ]
        payload = repo_map_html.build_payload(make_report(entries))
        assert [f["p"] for f in payload["files"]] == ["huge.py", "medium.py", "small.py"]

    def test_equal_scores_fall_back_to_size(self):
        entries = [
            make_entry("tiny.py", "x = 1\n" * 10),
            make_entry("bigger.py", "x = 1\n" * 200),
        ]
        payload = repo_map_html.build_payload(make_report(entries))
        assert [f["p"] for f in payload["files"]] == ["bigger.py", "tiny.py"]

    def test_totals_sum_every_file(self):
        entries = [make_entry("a.py", "x = 1\n" * 3), make_entry("b.md", "t\n" * 4)]
        payload = repo_map_html.build_payload(make_report(entries))
        assert payload["totals"]["files"] == 2
        assert payload["totals"]["loc"] == 7

    def test_tree_is_nested_by_directory(self):
        entries = [make_entry("a/b/x.py", "x = 1\n" * 6)]
        payload = repo_map_html.build_payload(make_report(entries))
        assert payload["tree"]["children"][0]["name"] == "a"
        assert payload["tree"]["children"][0]["children"][0]["loc"] == 6

    def test_commit_and_thresholds_travel_with_the_payload(self):
        payload = repo_map_html.build_payload(make_report(commit="deadbee"))
        assert payload["commit"] == "deadbee"
        assert payload["thresholds"]["max_loc"] == 500


class TestRender:
    def test_report_makes_no_external_requests(self):
        html = repo_map_html.render(make_report([make_entry("a.py", "x = 1\n")]))
        assert "http://" not in html
        assert "https://" not in html
        assert "<script src=" not in html
        assert "<link rel=\"stylesheet\"" not in html

    def test_script_terminator_in_a_path_cannot_break_out_of_the_payload(self):
        entry = make_entry("weird/</script><b>x.py", "x = 1\n")
        html = repo_map_html.render(make_report([entry]))
        assert "</script><b>x.py" not in html

    def test_every_file_reaches_the_document(self):
        entries = [make_entry("a/one.py", "x = 1\n"), make_entry("b/two.tsx", "const a=1;\n")]
        html = repo_map_html.render(make_report(entries))
        assert "a/one.py" in html
        assert "b/two.tsx" in html

    def test_document_is_a_complete_html_page(self):
        html = repo_map_html.render(make_report())
        assert html.startswith("<!doctype html>")
        assert html.rstrip().endswith("</html>")
