"""Tests for scripts/repo_map.py and scripts/repo_map_html.py."""
from __future__ import annotations

import json

import repo_map
import repo_map_html
import repo_map_metrics as metrics


class TestCountLines:
    def test_counts_every_line(self):
        counts = metrics.count_lines("a = 1\nb = 2\n", ".py")
        assert counts.total == 2

    def test_counts_final_line_without_trailing_newline(self):
        counts = metrics.count_lines("a = 1\nb = 2", ".py")
        assert counts.total == 2

    def test_empty_text_has_no_lines(self):
        counts = metrics.count_lines("", ".py")
        assert counts.total == 0
        assert counts.code == 0

    def test_separates_blank_comment_and_code_in_python(self):
        text = "# header\n\nvalue = 1\n"
        counts = metrics.count_lines(text, ".py")
        assert (counts.total, counts.blank, counts.comment, counts.code) == (3, 1, 1, 1)

    def test_trailing_comment_is_code_not_comment(self):
        counts = metrics.count_lines("value = 1  # why\n", ".py")
        assert counts.comment == 0
        assert counts.code == 1

    def test_counts_typescript_line_comments(self):
        counts = metrics.count_lines("// note\nconst a = 1;\n", ".ts")
        assert (counts.comment, counts.code) == (1, 1)

    def test_counts_typescript_block_comments(self):
        text = "/*\n * doc\n */\nconst a = 1;\n"
        counts = metrics.count_lines(text, ".tsx")
        assert (counts.comment, counts.code) == (3, 1)

    def test_code_after_block_comment_close_counts_as_code(self):
        counts = metrics.count_lines("/* doc */ const a = 1;\n", ".ts")
        assert counts.code == 1

    def test_unknown_extension_counts_no_comments(self):
        counts = metrics.count_lines("# not a comment here\n", ".bin")
        assert (counts.comment, counts.code) == (0, 1)


class TestAnalyzePython:
    def test_counts_top_level_classes_and_functions(self):
        m = metrics.analyze_python("class A:\n    pass\n\n\ndef f():\n    pass\n")
        assert (m.classes, m.functions) == (1, 1)

    def test_counts_methods_as_functions(self):
        text = (
            "class A:\n"
            "    def one(self):\n"
            "        pass\n"
            "\n"
            "    def two(self):\n"
            "        pass\n"
        )
        m = metrics.analyze_python(text)
        assert (m.classes, m.functions) == (1, 2)

    def test_counts_async_functions(self):
        m = metrics.analyze_python("async def f():\n    pass\n")
        assert m.functions == 1

    def test_reports_longest_function_name_and_span(self):
        text = "def small():\n    pass\n\n\ndef big():\n    a = 1\n    b = 2\n    c = 3\n"
        m = metrics.analyze_python(text)
        assert m.longest_fn == "big"
        assert m.longest_fn_loc == 4

    def test_module_without_functions_has_no_longest(self):
        m = metrics.analyze_python("VALUE = 1\n")
        assert m.longest_fn is None
        assert m.longest_fn_loc == 0

    def test_top_level_function_body_is_depth_one(self):
        m = metrics.analyze_python("def f():\n    return 1\n")
        assert m.max_depth == 1

    def test_nested_blocks_increase_depth(self):
        text = "def f():\n    if x:\n        for i in y:\n            pass\n"
        m = metrics.analyze_python(text)
        assert m.max_depth == 3

    def test_flat_module_has_depth_zero(self):
        m = metrics.analyze_python("A = 1\nB = 2\n")
        assert m.max_depth == 0

    def test_unparseable_source_returns_none(self):
        assert metrics.analyze_python("def (:\n") is None


class TestAnalyzeTypescript:
    def test_counts_export_statements(self):
        text = "const a = 1;\nexport const b = 2;\nexport default function C() {}\n"
        m = metrics.analyze_typescript(text)
        assert m.exports == 2

    def test_counts_react_hook_call_sites(self):
        text = "const [a, b] = useState(0);\nuseEffect(() => {}, []);\nuser.name;\n"
        m = metrics.analyze_typescript(text)
        assert m.hooks == 2

    def test_measures_top_level_block_span_by_brace_balance(self):
        text = "function big() {\n  const a = 1;\n  const b = 2;\n}\n"
        m = metrics.analyze_typescript(text)
        assert m.longest_block == "big"
        assert m.longest_block_loc == 4

    def test_nested_braces_do_not_close_the_block_early(self):
        text = (
            "export function outer() {\n"
            "  if (x) {\n"
            "    run();\n"
            "  }\n"
            "  return 1;\n"
            "}\n"
        )
        m = metrics.analyze_typescript(text)
        assert m.longest_block_loc == 6

    def test_picks_the_largest_of_several_blocks(self):
        text = (
            "function small() {\n"
            "  return 1;\n"
            "}\n"
            "const Big = () => {\n"
            "  const a = 1;\n"
            "  const b = 2;\n"
            "  return a + b;\n"
            "};\n"
        )
        m = metrics.analyze_typescript(text)
        assert m.longest_block == "Big"
        assert m.longest_block_loc == 5

    def test_module_without_blocks_reports_nothing(self):
        m = metrics.analyze_typescript("export const A = 1;\n")
        assert m.longest_block is None
        assert m.longest_block_loc == 0


class TestIsGenerated:
    def test_alembic_revisions_are_generated(self):
        assert metrics.is_generated("backend/alembic/versions/a1b2c3_add_fan.py")

    def test_i18n_locale_bundles_are_generated(self):
        assert metrics.is_generated("client/src/i18n/locales/de/common.json")

    def test_lockfiles_are_generated(self):
        assert metrics.is_generated("client/package-lock.json")

    def test_hand_written_service_is_not_generated(self):
        assert not metrics.is_generated("backend/app/services/power/manager.py")


class TestComputeScore:
    def score(self, **kwargs):
        params = {"loc": 0, "longest_fn_loc": 0, "max_depth": 0, "generated": False}
        params.update(kwargs)
        return metrics.compute_score(thresholds=metrics.Thresholds(), **params)

    def test_file_below_every_threshold_scores_zero(self):
        result = self.score(loc=200, longest_fn_loc=40, max_depth=3)
        assert result.score == 0
        assert result.reasons == ()

    def test_double_the_line_limit_costs_the_full_size_budget(self):
        assert self.score(loc=1000).score == 50

    def test_size_points_are_capped(self):
        assert self.score(loc=50_000).score == 50

    def test_long_function_adds_points(self):
        assert self.score(loc=100, longest_fn_loc=160).score == 30

    def test_deep_nesting_adds_points(self):
        assert self.score(loc=100, max_depth=7).score == 20

    def test_score_never_exceeds_one_hundred(self):
        assert self.score(loc=50_000, longest_fn_loc=5_000, max_depth=20).score == 100

    def test_generated_files_are_damped(self):
        assert self.score(loc=1000, generated=True).score == 5

    def test_reasons_name_each_exceeded_metric(self):
        result = self.score(loc=1000, longest_fn_loc=160, max_depth=7)
        joined = " | ".join(result.reasons)
        assert "1000 LOC" in joined
        assert "longest function 160" in joined
        assert "nesting depth 7" in joined

    def test_generated_file_below_thresholds_gets_no_damping_note(self):
        result = self.score(loc=100, generated=True)
        assert result.score == 0
        assert result.reasons == ()

    def test_thresholds_are_configurable(self):
        result = metrics.compute_score(
            loc=1000,
            longest_fn_loc=0,
            max_depth=0,
            generated=False,
            thresholds=metrics.Thresholds(max_loc=1000),
        )
        assert result.score == 0


def make_entry(path: str, text: str, **kwargs):
    kwargs.setdefault("thresholds", metrics.Thresholds())
    return metrics.analyze_file(path, text, **kwargs)


class TestAnalyzeFile:
    def test_python_file_carries_ast_metrics(self):
        entry = make_entry("backend/app/x.py", "def f():\n    if a:\n        pass\n")
        assert entry.kind == "python"
        assert entry.functions == 1
        assert entry.max_depth == 2
        assert entry.estimated is False

    def test_typescript_metrics_are_flagged_as_estimated(self):
        entry = make_entry("client/src/X.tsx", "export function A() {\n  return 1;\n}\n")
        assert entry.kind == "typescript"
        assert entry.symbols == 1
        assert entry.estimated is True

    def test_other_extensions_get_line_counts_only(self):
        entry = make_entry("docs/guide.md", "# Title\n\ntext\n")
        assert entry.kind == "other"
        assert entry.loc == 3
        assert entry.symbols == 0
        assert entry.longest_loc == 0

    def test_unparseable_python_falls_back_to_line_counts(self):
        entry = make_entry("backend/broken.py", "def (:\n" + "x\n" * 700)
        assert entry.kind == "other"
        assert entry.loc == 701

    def test_generated_python_is_damped_by_default(self):
        text = "x = 1\n" * 1000
        assert make_entry("backend/alembic/versions/a1.py", text).score == 5

    def test_include_generated_disables_the_damping(self):
        text = "x = 1\n" * 1000
        entry = make_entry(
            "backend/alembic/versions/a1.py", text, include_generated=True
        )
        assert entry.score == 50

    def test_windows_separators_are_normalised(self):
        entry = make_entry("backend\\app\\x.py", "a = 1\n")
        assert entry.path == "backend/app/x.py"


class TestBuildTree:
    def entries(self):
        return [
            make_entry("a/b/deep.py", "x = 1\n" * 10),
            make_entry("a/shallow.py", "x = 1\n" * 5),
            make_entry("root.md", "text\n" * 2),
        ]

    def test_root_totals_cover_every_file(self):
        tree = repo_map.build_tree(self.entries())
        assert (tree.loc, tree.files) == (17, 3)

    def test_directory_totals_include_nested_directories(self):
        tree = repo_map.build_tree(self.entries())
        assert tree.children["a"].loc == 15
        assert tree.children["a"].files == 2

    def test_leaf_directory_holds_only_its_own_files(self):
        tree = repo_map.build_tree(self.entries())
        assert tree.children["a"].children["b"].loc == 10
        assert tree.children["a"].children["b"].files == 1

    def test_directory_knows_its_repo_relative_path(self):
        tree = repo_map.build_tree(self.entries())
        assert tree.children["a"].children["b"].path == "a/b"

    def test_empty_input_yields_an_empty_root(self):
        tree = repo_map.build_tree([])
        assert (tree.loc, tree.files, tree.children) == (0, 0, {})


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


class TestBuildReport:
    def test_reads_each_listed_file_from_disk(self, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        report = repo_map.build_report(
            repo_map.WorktreeSource(tmp_path),
            ["pkg/a.py"],
            thresholds=metrics.Thresholds(),
            commit="c0ffee",
        )
        assert [e.path for e in report.entries] == ["pkg/a.py"]
        assert report.entries[0].loc == 2
        assert report.tree.loc == 2

    def test_missing_file_is_skipped_not_fatal(self, tmp_path):
        (tmp_path / "there.py").write_text("x = 1\n", encoding="utf-8")
        report = repo_map.build_report(
            repo_map.WorktreeSource(tmp_path),
            ["there.py", "gone.py"],
            thresholds=metrics.Thresholds(),
            commit="c0ffee",
        )
        assert [e.path for e in report.entries] == ["there.py"]

    def test_binary_file_is_skipped(self, tmp_path):
        (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00\x01\x80")
        (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
        report = repo_map.build_report(
            repo_map.WorktreeSource(tmp_path),
            ["blob.bin", "ok.py"],
            thresholds=metrics.Thresholds(),
            commit="c0ffee",
        )
        assert [e.path for e in report.entries] == ["ok.py"]

    def test_commit_travels_into_the_report(self, tmp_path):
        report = repo_map.build_report(
            repo_map.WorktreeSource(tmp_path),
            [],
            thresholds=metrics.Thresholds(),
            commit="c0ffee",
        )
        assert report.commit == "c0ffee"


class TestWorktreeSource:
    def test_reads_a_file_relative_to_its_root(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        source = repo_map.WorktreeSource(tmp_path)
        assert source.read("a.py") == "x = 1\n"

    def test_missing_file_reads_as_none(self, tmp_path):
        assert repo_map.WorktreeSource(tmp_path).read("nope.py") is None

    def test_binary_file_reads_as_none(self, tmp_path):
        (tmp_path / "b.bin").write_bytes(b"\xff\xfe\x00\x01")
        assert repo_map.WorktreeSource(tmp_path).read("b.bin") is None

    def test_identity_is_none_because_the_worktree_has_no_blob_ids(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert repo_map.WorktreeSource(tmp_path).identity("a.py") is None


class TestAnalyzePaths:
    def test_cache_hit_skips_reanalysis(self):
        class FakeSource:
            def __init__(self):
                self.reads = 0

            def read(self, path):
                self.reads += 1
                return "x = 1\n"

            def identity(self, path):
                return "blob1"

        cache = {}
        src_a, src_b = FakeSource(), FakeSource()
        first = repo_map.analyze_paths(
            src_a, ["a.py"], thresholds=metrics.Thresholds(), cache=cache
        )
        second = repo_map.analyze_paths(
            src_b, ["a.py"], thresholds=metrics.Thresholds(), cache=cache
        )
        assert first[0] == second[0]
        assert src_b.reads == 0, "cache hit must not read content at all"

    def test_same_blob_at_a_different_path_is_analysed_again(self):
        class FakeSource:
            def read(self, path):
                return "x = 1\n"

            def identity(self, path):
                return "blob1"

        cache = {}
        repo_map.analyze_paths(
            FakeSource(), ["a.py"], thresholds=metrics.Thresholds(), cache=cache
        )
        repo_map.analyze_paths(
            FakeSource(), ["b.py"], thresholds=metrics.Thresholds(), cache=cache
        )
        assert len(cache) == 2, "path is part of the key: it drives kind and generated"

    def test_none_identity_bypasses_the_cache(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        cache = {}
        repo_map.analyze_paths(
            repo_map.WorktreeSource(tmp_path),
            ["a.py"],
            thresholds=metrics.Thresholds(),
            cache=cache,
        )
        assert cache == {}


class TestMain:
    def test_writes_a_report_for_the_real_repository(self, tmp_path):
        out = tmp_path / "map.html"
        assert repo_map.main(["-o", str(out)]) == 0
        html = out.read_text(encoding="utf-8")
        tracked = repo_map.tracked_files(repo_map.ROOT)
        first_module = next(p for p in tracked if p.endswith(".py"))
        assert first_module in html
        assert "https://" not in html

    def test_threshold_flags_reach_the_report(self, tmp_path):
        out = tmp_path / "map.html"
        assert repo_map.main(["-o", str(out), "--max-loc", "1234"]) == 0
        assert '"max_loc": 1234' in out.read_text(encoding="utf-8")

    def test_history_flag_writes_a_json_sidecar(self, tmp_path):
        out = tmp_path / "map.html"
        data = tmp_path / "history.json"
        code = repo_map.main(
            ["-o", str(out), "--history", "--since", "2026-06-01", "--json", str(data)]
        )
        assert code == 0
        payload = json.loads(data.read_text(encoding="utf-8"))
        assert payload["points"], "history run must produce at least one point"

    def test_without_the_flag_no_history_work_happens(self, tmp_path, monkeypatch):
        def explode(*args, **kwargs):
            raise AssertionError("history must not run unless --history is passed")

        import repo_map_history

        monkeypatch.setattr(repo_map_history, "build_history", explode)
        assert repo_map.main(["-o", str(tmp_path / "map.html")]) == 0
