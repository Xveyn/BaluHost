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

    def test_history_is_none_when_not_requested(self):
        payload = repo_map_html.build_payload(make_report())
        assert payload["history"] is None

    def test_history_travels_into_the_payload(self):
        hist = {
            "areas": ["backend/app", "sonstiges"],
            "points": [
                {"label": "2026-01", "commit": "abc1234", "date": "2026-01-31",
                 "files": 1, "loc": 10, "flagged": 0, "score": 0,
                 "areas": {"backend/app": 10, "sonstiges": 0}},
            ],
            "churn": {},
        }
        payload = repo_map_html.build_payload(make_report(), history=hist)
        assert payload["history"]["points"][0]["label"] == "2026-01"

    def test_churn_lands_on_the_matching_file_row(self):
        entry = make_entry("a.py", "x = 1\n")
        hist = {
            "areas": [],
            "points": [],
            "churn": {"a.py": {"commits": 7, "added": 5, "deleted": 2,
                               "last": "2026-08-01"}},
        }
        payload = repo_map_html.build_payload(
            make_report([entry]), history=hist
        )
        row = payload["files"][0]
        assert row["ch"] == 7
        assert row["lt"] == "2026-08-01"

    def test_files_without_churn_report_zero_not_missing(self):
        entry = make_entry("a.py", "x = 1\n")
        payload = repo_map_html.build_payload(make_report([entry]))
        assert payload["files"][0]["ch"] == 0
        assert payload["files"][0]["lt"] is None

    def test_embedded_history_omits_the_churn_map(self):
        """No JS reads DATA.history.churn - every current file already
        carries its own churn via files[].ch/.lt. The full map (including
        paths that no longer exist) is dead weight in the embedded page."""
        hist = {
            "areas": ["backend/app"],
            "points": [],
            "churn": {"a.py": {"commits": 3, "added": 1, "deleted": 0,
                               "last": "2026-02-01"}},
        }
        payload = repo_map_html.build_payload(make_report(), history=hist)
        assert "churn" not in payload["history"]
        assert payload["history"]["areas"] == ["backend/app"]

    def test_build_payload_does_not_mutate_the_callers_history_dict(self):
        hist = {
            "areas": [],
            "points": [],
            "churn": {"a.py": {"commits": 1, "added": 0, "deleted": 0,
                               "last": "2026-01-01"}},
        }
        repo_map_html.build_payload(make_report(), history=hist)
        assert "churn" in hist, "the --json sidecar needs the original dict intact"


class TestRender:
    def test_report_makes_no_external_requests(self):
        """The SVG namespace URI (http://www.w3.org/2000/svg) is a name, not
        a fetch, so this checks resource-load patterns rather than a blanket
        "http://" substring - see test_page_loads_nothing_from_the_network."""
        html = repo_map_html.render(make_report([make_entry("a.py", "x = 1\n")]))
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

    def test_history_section_starts_hidden_without_data(self):
        plain = repo_map_html.render(make_report())
        assert "id=\"history\" hidden" in plain, (
            "the section is always in the markup; JS reveals it when data exists"
        )
        assert "\"history\": null" in plain or "\"history\":null" in plain

    def test_history_section_is_rendered_when_data_is_present(self):
        hist = {
            "areas": ["backend/app"],
            "points": [
                {"label": "2026-01", "commit": "a", "date": "2026-01-31",
                 "files": 1, "loc": 10, "flagged": 0, "score": 0,
                 "areas": {"backend/app": 10}},
                {"label": "2026-02", "commit": "b", "date": "2026-02-28",
                 "files": 1, "loc": 20, "flagged": 1, "score": 5,
                 "areas": {"backend/app": 20}},
            ],
            "churn": {},
        }
        page = repo_map_html.render(make_report(), history=hist)
        assert "id=\"history\"" in page
        assert "2026-02" in page

    def test_history_chart_and_hotspots_are_wired_up(self):
        hist = {
            "areas": ["backend/app", "sonstiges"],
            "points": [
                {"label": "2026-01", "commit": "a", "date": "2026-01-31",
                 "files": 1, "loc": 10, "flagged": 0, "score": 0,
                 "areas": {"backend/app": 10, "sonstiges": 0}},
                {"label": "2026-02", "commit": "b", "date": "2026-02-28",
                 "files": 1, "loc": 20, "flagged": 1, "score": 5,
                 "areas": {"backend/app": 20, "sonstiges": 0}},
            ],
            "churn": {"a.py": {"commits": 3, "added": 1, "deleted": 0,
                               "last": "2026-02-01"}},
        }
        page = repo_map_html.render(make_report([make_entry("a.py", "x = 1\n")]),
                                    history=hist)
        assert "history-chart" in page
        assert "history-hotspots" in page
        assert "renderHistory" in page, "the chart must be built, not just declared"
        assert "dirDelta" in page, "the tree needs its per-directory delta column"

    def test_flagged_and_score_get_separate_charts(self):
        """flagged-file counts (tens to low hundreds) and the score sum
        (thousands to tens of thousands) differ enough in scale that a
        shared axis flattens the smaller series into an unreadable
        near-flat line - a visual-pass finding, not something a structural
        test alone would have caught. They now render as two independent
        charts, each with its own host/legend and own-series label."""
        hist = {
            "areas": ["backend/app"],
            "points": [
                {"label": "2026-01", "commit": "a", "date": "2026-01-31",
                 "files": 1, "loc": 10, "flagged": 0, "score": 0,
                 "areas": {"backend/app": 10}},
                {"label": "2026-02", "commit": "b", "date": "2026-02-28",
                 "files": 1, "loc": 20, "flagged": 1, "score": 5,
                 "areas": {"backend/app": 20}},
            ],
            "churn": {},
        }
        page = repo_map_html.render(make_report(), history=hist)
        assert 'id="flagged-chart"' in page
        assert 'id="flagged-legend"' in page
        assert 'id="score-chart"' in page
        assert 'id="score-legend"' in page
        assert "geflaggte Dateien" in page
        assert "Score-Summe" in page

    def test_chart_does_not_use_non_uniform_svg_scaling(self):
        """preserveAspectRatio="none" on a percentage-width svg stretches a
        fixed viewBox horizontally, distorting every glyph and gap (a visual
        bug found only by actually rendering the page). The chart now sizes
        its viewBox from the host element instead, so this attribute must
        never reappear."""
        hist = {
            "areas": ["backend/app"],
            "points": [
                {"label": "2026-01", "commit": "a", "date": "2026-01-31",
                 "files": 1, "loc": 10, "flagged": 0, "score": 0,
                 "areas": {"backend/app": 10}},
                {"label": "2026-02", "commit": "b", "date": "2026-02-28",
                 "files": 1, "loc": 20, "flagged": 1, "score": 5,
                 "areas": {"backend/app": 20}},
            ],
            "churn": {},
        }
        page = repo_map_html.render(make_report(), history=hist)
        assert "preserveAspectRatio" not in page

    def test_rendered_page_does_not_contain_the_churn_map(self):
        hist = {
            "areas": ["backend/app"],
            "points": [
                {"label": "2026-01", "commit": "a", "date": "2026-01-31",
                 "files": 1, "loc": 10, "flagged": 0, "score": 0,
                 "areas": {"backend/app": 10}},
            ],
            "churn": {"gone.py": {"commits": 9, "added": 1, "deleted": 0,
                                   "last": "2026-02-01"}},
        }
        page = repo_map_html.render(make_report([make_entry("a.py", "x = 1\n")]),
                                    history=hist)
        assert '"churn"' not in page
        assert "gone.py" not in page

    def test_page_loads_nothing_from_the_network(self):
        """The SVG namespace URI is a name, not a fetch, so the check targets
        resource loads rather than the substring http://."""
        hist = {"areas": [], "points": [], "churn": {}}
        page = repo_map_html.render(make_report(), history=hist)
        for forbidden in ("<script src", "<link ", "@import", "url(http",
                          "src=\"http", "href=\"http"):
            assert forbidden not in page, f"page must stay self-contained: {forbidden}"
