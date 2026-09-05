# Repo-Map-Zeitachse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Repo-Map um eine Zeitachse erweitern — Metrik-Verlauf über Git-Snapshots plus Änderungshäufigkeit je Datei.

**Architecture:** Eine `ContentSource`-Naht ersetzt das direkte Lesen von der Platte, sodass derselbe Analyzer gegen einen Git-Commit laufen kann. Ein Cache nach `(Blob-SHA, Pfad)` reduziert 60.443 Pfad-Einträge über 40 Snapshots auf 6.844 echte Analysen. Churn kommt aus einem einzigen `git log --numstat`-Durchlauf. Kein Persistenz-Layer: jeder Lauf rekonstruiert aus Git.

**Tech Stack:** Python 3.11+ (Zielumgebung 3.14), stdlib only, pytest. Kein Frontend-Framework — die HTML-Seite baut sich aus einem eingebetteten JSON-Payload.

**Spec:** `docs/superpowers/specs/2026-09-05-repo-map-history-design.md`

## Global Constraints

- **Keine Third-Party-Dependencies.** Weder Python-Pakete noch CDN/Chart-Library im HTML. Das ist die Kernregel des Tools.
- **Keine Datei über 500 Zeilen.** Das Tool setzt diese Konvention (#301) durch und muss sie selbst einhalten. Mit `wc -l` prüfen, nicht mit PowerShell `Measure-Object -Line` (zählt Leerzeilen nicht mit).
- **Alle `subprocess`-Aufrufe mit Argumentliste**, niemals `shell=True`.
- **Git-Aufrufe mit `text=True, encoding="utf-8", errors="replace"`.** Ohne das bricht der Lauf auf Windows an Umlauten in Pfaden oder Commit-Texten.
- **Commit-Messages ASCII-only** (Repo-Konvention: "Luefterkurve", nicht "Lüfterkurve"). Dateiinhalte dürfen Umlaute enthalten.
- **Tests laufen mit** `python -m pytest scripts/test_repo_map.py scripts/test_repo_map_history.py -q` aus dem Repo-Root. `scripts/conftest.py` legt `scripts/` auf den `sys.path`.
- **Branch:** `feat/repo-map-history`, baut auf PR #540 auf. Nach dessen Merge auf `main` rebasen.
- **Jeder Task endet mit einem eigenen Commit.**

---

### Task 1: Content-Source-Naht

Zieht das Lesen aus `build_report` heraus, damit derselbe Analyzer später gegen einen Git-Commit laufen kann. Verhalten bleibt identisch — reiner Umbau plus die Cache-Fähigkeit, die Task 3 braucht.

**Files:**
- Modify: `scripts/repo_map.py`
- Modify: `scripts/test_repo_map.py` (die bestehenden `TestBuildReport`-Tests rufen die alte Signatur)

**Interfaces:**
- Consumes: `repo_map_metrics.analyze_file`, `repo_map_metrics.FileEntry`, `repo_map_metrics.Thresholds`
- Produces:
  - `class ContentSource(Protocol)` mit `read(path: str) -> str | None` und `identity(path: str) -> str | None`
  - `class WorktreeSource` mit `__init__(root: Path)`, erfüllt das Protokoll, `identity()` gibt immer `None`
  - `analyze_paths(source, paths, *, thresholds, include_generated=False, cache=None) -> list[FileEntry]`
  - `build_report(source, paths, *, thresholds, commit, include_generated=False, generated_at=None, cache=None) -> Report` — **erstes Argument ist jetzt eine Source, kein `Path` mehr**

- [ ] **Step 1: Write the failing test**

In `scripts/test_repo_map.py`, neue Klassen hinter `TestBuildReport` anfügen:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map.py -k "WorktreeSource or AnalyzePaths" -q`
Expected: FAIL mit `AttributeError: module 'repo_map' has no attribute 'WorktreeSource'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/repo_map.py` die Imports ergänzen — `from typing import Iterable, Protocol` und `from repo_map_metrics import FileEntry, Thresholds, analyze_file` — dann direkt vor `build_report` einfügen:

```python
class ContentSource(Protocol):
    """Where file content comes from: the worktree, or a commit's tree."""

    def read(self, path: str) -> str | None:
        """Text of one repo-relative path, or None when binary or absent."""

    def identity(self, path: str) -> str | None:
        """Stable content id (a blob SHA), or None when there is none.

        None disables caching for that path rather than caching under a key
        that cannot tell two different contents apart.
        """


class WorktreeSource:
    """Reads from the checked-out working tree - the original behaviour."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, path: str) -> str | None:
        return _read_text(self.root / path)

    def identity(self, path: str) -> str | None:
        return None


def analyze_paths(
    source: ContentSource,
    paths: Iterable[str],
    *,
    thresholds: Thresholds,
    include_generated: bool = False,
    cache: dict[tuple[str, str], FileEntry] | None = None,
) -> list[FileEntry]:
    """Analyse every readable path from a source, reusing cached results.

    The cache key is (content id, path): the path belongs in the key because
    both the generated-file check and the kind detection are path-dependent.
    Across history snapshots most files are unchanged blobs, and that is what
    keeps a full-history run in the seconds range.
    """
    entries: list[FileEntry] = []
    for rel in paths:
        key: tuple[str, str] | None = None
        if cache is not None:
            ident = source.identity(rel)
            if ident is not None:
                key = (ident, rel)
                hit = cache.get(key)
                if hit is not None:
                    entries.append(hit)
                    continue

        text = source.read(rel)
        if text is None:
            continue
        entry = analyze_file(
            rel, text, thresholds=thresholds, include_generated=include_generated
        )
        if key is not None and cache is not None:
            cache[key] = entry
        entries.append(entry)
    return entries
```

`build_report` auf die Source umstellen — der ganze Body wird zu:

```python
def build_report(
    source: ContentSource,
    paths: Iterable[str],
    *,
    thresholds: Thresholds,
    commit: str,
    include_generated: bool = False,
    generated_at: str | None = None,
    cache: dict[tuple[str, str], FileEntry] | None = None,
) -> Report:
    """Analyse every readable path from the source and assemble the report.

    Unreadable and binary files are skipped rather than raising: a repo map
    that dies on one stray blob is useless.
    """
    entries = analyze_paths(
        source,
        paths,
        thresholds=thresholds,
        include_generated=include_generated,
        cache=cache,
    )
    return Report(
        commit=commit,
        generated_at=generated_at or datetime.now().strftime("%Y-%m-%d %H:%M"),
        thresholds=thresholds,
        entries=entries,
        tree=build_tree(entries),
    )
```

In `main()` den Aufruf anpassen:

```python
    report = build_report(
        WorktreeSource(ROOT),
        tracked_files(ROOT),
        thresholds=thresholds,
        commit=git_commit(ROOT),
        include_generated=args.include_generated,
    )
```

- [ ] **Step 4: Bestehende Tests auf die neue Signatur ziehen**

In `scripts/test_repo_map.py` jeden `repo_map.build_report(tmp_path, ...)`-Aufruf zu `repo_map.build_report(repo_map.WorktreeSource(tmp_path), ...)` ändern. Betroffen ist die Klasse `TestBuildReport` (4 Tests). Suche zur Kontrolle: `grep -n "build_report(" scripts/test_repo_map.py` — danach darf kein Aufruf mehr ein nacktes `tmp_path` als erstes Argument haben.

- [ ] **Step 5: Run the full existing suite**

Run: `python -m pytest scripts/test_repo_map.py -q`
Expected: PASS, 0 Failures (65 bestehende plus 7 neue).

- [ ] **Step 6: Verhalten gegen den echten Report gegenprüfen**

Run: `python scripts/repo_map.py -o repo-map-check.html`
Expected: eine Zusammenfassung in der Größenordnung `2685 files, 600,037 lines, 599 flagged`. Die genauen Zahlen wandern mit dem Repo; entscheidend ist, dass der Lauf durchläuft und nicht plötzlich Dateien verliert. Danach `rm repo-map-check.html` — die Datei ist ohnehin über `repo-map*.html` in `.gitignore`.

- [ ] **Step 7: Datei-Länge prüfen**

Run: `wc -l scripts/repo_map.py`
Expected: unter 500.

- [ ] **Step 8: Commit**

```bash
git add scripts/repo_map.py scripts/test_repo_map.py
git commit -m "refactor(scripts): Content-Source-Naht in der Repo-Map

build_report liest nicht mehr selbst von der Platte, sondern ueber eine
ContentSource. analyze_paths kapselt die Analyse-Schleife und kann
Ergebnisse nach (Blob-SHA, Pfad) cachen. Verhalten unveraendert; die Naht
traegt im naechsten Schritt die Git-Historie.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Snapshot-Auswahl

Wählt je Zeitraum einen Commit aus der First-Parent-Historie.

**Files:**
- Create: `scripts/repo_map_history.py`
- Create: `scripts/test_repo_map_history.py`

**Interfaces:**
- Consumes: nichts aus Task 1
- Produces:
  - `@dataclass(frozen=True) class Snapshot` mit `commit: str`, `date: str` (ISO `YYYY-MM-DD`), `label: str`
  - `select_snapshots(root: Path, *, interval: str = "monthly", since: str | None = None) -> list[Snapshot]` — aufsteigend nach Datum, ältester zuerst
  - `period_label(date: str, interval: str) -> str` — `"2026-09"` bei monthly, `"2026-W36"` bei weekly
  - `INTERVALS: tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

Neue Datei `scripts/test_repo_map_history.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map_history.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'repo_map_history'`

- [ ] **Step 3: Write minimal implementation**

Neue Datei `scripts/repo_map_history.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map_history.py -q`
Expected: PASS, 7 Tests.

- [ ] **Step 5: Gegen das echte Repo prüfen**

Run: `python -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import repo_map_history as h; s=h.select_snapshots(Path('.')); print(len(s), s[0].label, s[-1].label)"`
Expected: rund `11 2025-11 2026-09` — die Zahl wächst mit dem Repo.

- [ ] **Step 6: Commit**

```bash
git add scripts/repo_map_history.py scripts/test_repo_map_history.py
git commit -m "feat(scripts): Snapshot-Auswahl fuer die Repo-Map-Historie

Waehlt je Monat oder Woche den letzten Commit der First-Parent-Historie.
--first-parent, damit die Reihe den Zustand der Mainline abbildet und
nicht zufaellige Feature-Branch-Commits.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: GitTreeSource mit gebündeltem Blob-Lesen

Liest Dateiinhalte aus einem Commit statt von der Platte. Hier sitzt die Deadlock-Falle aus der Spec.

**Files:**
- Modify: `scripts/repo_map_history.py`
- Modify: `scripts/test_repo_map_history.py`

**Interfaces:**
- Consumes: das `repo_map.ContentSource`-Protokoll aus Task 1 (wird erfüllt, nicht importiert — `Protocol` ist strukturell)
- Produces:
  - `class GitTreeSource` mit `__init__(root: Path, commit: str)`, `paths() -> list[str]`, `identity(path) -> str | None`, `read(path) -> str | None`, `prefetch(paths: Iterable[str]) -> None`

- [ ] **Step 1: Write the failing test**

An `scripts/test_repo_map_history.py` anhängen:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map_history.py -k GitTreeSource -q`
Expected: FAIL mit `AttributeError: module 'repo_map_history' has no attribute 'GitTreeSource'`

- [ ] **Step 3: Write minimal implementation**

An `scripts/repo_map_history.py` anhängen (`threading` und `Iterable` sind bereits importiert):

```python
def _decode(raw: bytes) -> str | None:
    """Decode a blob as UTF-8 text, or None when it is binary."""
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


class GitTreeSource:
    """Reads file content out of one commit's tree.

    Satisfies repo_map.ContentSource. identity() returns the blob SHA, which
    is what lets the analysis cache skip files that did not change between
    two snapshots.
    """

    def __init__(self, root: Path, commit: str) -> None:
        self.root = root
        self.commit = commit
        self._blobs: dict[str, str] = {}
        self._content: dict[str, str | None] = {}
        for line in _git(root, "ls-tree", "-r", commit).splitlines():
            meta, _, path = line.partition("\t")
            fields = meta.split()
            if len(fields) >= 3 and fields[1] == "blob":
                self._blobs[path] = fields[2]

    def paths(self) -> list[str]:
        return list(self._blobs)

    def identity(self, path: str) -> str | None:
        return self._blobs.get(path)

    def read(self, path: str) -> str | None:
        if path in self._content:
            return self._content[path]
        blob = self._blobs.get(path)
        if blob is None:
            return None
        raw = subprocess.check_output(
            ["git", "cat-file", "blob", blob], cwd=self.root
        )
        text = _decode(raw)
        self._content[path] = text
        return text

    def prefetch(self, paths: Iterable[str]) -> None:
        """Load many blobs through a single `git cat-file --batch` process.

        The request SHAs are fed from a worker thread. Writing them all before
        reading any output fills the pipe buffer and deadlocks - that is not a
        theoretical risk, it hangs on this repo's real history.
        """
        wanted = [
            (p, self._blobs[p])
            for p in paths
            if p in self._blobs and p not in self._content
        ]
        if not wanted:
            return

        proc = subprocess.Popen(
            ["git", "cat-file", "--batch"],
            cwd=self.root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )

        def feed() -> None:
            try:
                for _path, blob in wanted:
                    proc.stdin.write((blob + "\n").encode("ascii"))
                proc.stdin.close()
            except (BrokenPipeError, ValueError, OSError):
                pass

        thread = threading.Thread(target=feed, daemon=True)
        thread.start()
        try:
            for path, _blob in wanted:
                header = proc.stdout.readline().split()
                if len(header) < 3:
                    self._content[path] = None
                    continue
                size = int(header[2])
                chunks: list[bytes] = []
                remaining = size
                while remaining > 0:
                    chunk = proc.stdout.read(remaining)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                proc.stdout.read(1)  # trailing newline after the payload
                self._content[path] = _decode(b"".join(chunks))
        finally:
            proc.stdout.close()
            thread.join(timeout=5)
            proc.wait(timeout=5)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map_history.py -k GitTreeSource -q`
Expected: PASS, 7 Tests. Wenn ein Test **hängt** statt zu failen, ist der Feeder-Thread falsch verdrahtet — genau die Falle aus der Spec.

- [ ] **Step 5: Run the whole file**

Run: `python -m pytest scripts/test_repo_map_history.py -q`
Expected: PASS, 14 Tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/repo_map_history.py scripts/test_repo_map_history.py
git commit -m "feat(scripts): GitTreeSource liest Dateiinhalte aus einem Commit

ls-tree einmal je Snapshot, Inhalte gebuendelt ueber git cat-file --batch.
Die SHAs werden aus einem Feeder-Thread geschrieben: erst alle schreiben
und dann lesen laesst den Pipe-Puffer volllaufen und haengt den Prozess.
Ein Test mit 300 Dateien haelt das fest.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 4: Churn aus einem einzigen git-log-Durchlauf

Zählt je Datei Commits, addierte und gelöschte Zeilen. Umbenennungen müssen zusammengeführt werden, sonst zerfällt die Historie einer Datei in zwei Hälften.

**Files:**
- Modify: `scripts/repo_map_history.py`
- Modify: `scripts/test_repo_map_history.py`

**Interfaces:**
- Consumes: `_git` aus Task 2
- Produces:
  - `@dataclass(frozen=True) class Churn` mit `path: str`, `commits: int`, `added: int`, `deleted: int`, `last_date: str`
  - `collect_churn(root: Path, *, since: str | None = None) -> dict[str, Churn]` — Schlüssel ist der **heutige** Pfad
  - `split_rename(raw: str) -> tuple[str, str | None]` — `(neuer Pfad, alter Pfad oder None)`

- [ ] **Step 1: Write the failing test**

An `scripts/test_repo_map_history.py` anhängen:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map_history.py -k "SplitRename or CollectChurn" -q`
Expected: FAIL mit `AttributeError: module 'repo_map_history' has no attribute 'split_rename'`

- [ ] **Step 3: Write minimal implementation**

An `scripts/repo_map_history.py` anhängen:

```python
# Marks a commit header line inside --numstat output. A NUL can never appear
# in a path, so it separates headers from stat lines without ambiguity.
_COMMIT_MARK = "\x00"


@dataclass(frozen=True)
class Churn:
    """How often and how heavily one file changed over the window."""

    path: str
    commits: int
    added: int
    deleted: int
    last_date: str


def _join_rename(head: str, middle: str, tail: str) -> str:
    return (head + middle + tail).replace("//", "/").lstrip("/")


def split_rename(raw: str) -> tuple[str, str | None]:
    """Split a --numstat path field into (new path, old path or None).

    git writes renames as `old => new` or, when only part of the path moved,
    as `keep/{old => new}/keep`.
    """
    if " => " not in raw:
        return raw, None
    if "{" in raw and "}" in raw:
        head, rest = raw.split("{", 1)
        middle, tail = rest.split("}", 1)
        old_middle, _, new_middle = middle.partition(" => ")
        return (
            _join_rename(head, new_middle, tail),
            _join_rename(head, old_middle, tail),
        )
    old, _, new = raw.partition(" => ")
    return new.strip(), old.strip()


def _canonical(alias: dict[str, str], path: str) -> str:
    """Follow a rename chain to the name the file carries today."""
    seen: set[str] = set()
    while path in alias and path not in seen:
        seen.add(path)
        path = alias[path]
    return path


def collect_churn(root: Path, *, since: str | None = None) -> dict[str, Churn]:
    """Commit counts and line deltas per file, keyed by the file's newest name.

    One pass over the log. Because git walks newest-first, a rename is seen
    before the commits that used the old name, so the alias map is always
    populated by the time an older name shows up.
    """
    args = [
        "log",
        "--first-parent",
        "--numstat",
        "-M",
        f"--format={_COMMIT_MARK}%H %as",
    ]
    if since:
        args.append(f"--since={since}")

    alias: dict[str, str] = {}
    totals: dict[str, list] = {}  # path -> [commits, added, deleted, last_date]
    date = ""

    for line in _git(root, *args).splitlines():
        if line.startswith(_COMMIT_MARK):
            _commit, _, date = line[len(_COMMIT_MARK):].partition(" ")
            continue
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            continue

        added_raw, deleted_raw, raw_path = fields
        new_path, old_path = split_rename(raw_path)
        path = _canonical(alias, new_path)
        if old_path is not None and old_path != path:
            alias[old_path] = path

        # Binary files report "-" for both counts; they still changed.
        added = int(added_raw) if added_raw.isdigit() else 0
        deleted = int(deleted_raw) if deleted_raw.isdigit() else 0

        row = totals.get(path)
        if row is None:
            totals[path] = [1, added, deleted, date]
        else:
            row[0] += 1
            row[1] += added
            row[2] += deleted

    return {
        path: Churn(
            path=path,
            commits=row[0],
            added=row[1],
            deleted=row[2],
            last_date=row[3],
        )
        for path, row in totals.items()
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map_history.py -k "SplitRename or CollectChurn" -q`
Expected: PASS, 10 Tests.

- [ ] **Step 5: Gegen das echte Repo prüfen**

Run: `python -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import repo_map_history as h; c=h.collect_churn(Path('.'), since='2026-03-05'); top=sorted(c.values(), key=lambda x: -x.commits)[:5]; [print(x.commits, x.path) for x in top]"`
Expected: oben stehen `CHANGELOG.md`, `client/package-lock.json`, `backend/app/services/power/sleep.py` — Dateien mit vielen Commits.

- [ ] **Step 6: Run the whole file und Länge prüfen**

Run: `python -m pytest scripts/test_repo_map_history.py -q ; wc -l scripts/repo_map_history.py`
Expected: PASS, 24 Tests. Datei unter 500 Zeilen.

- [ ] **Step 7: Commit**

```bash
git add scripts/repo_map_history.py scripts/test_repo_map_history.py
git commit -m "feat(scripts): Churn je Datei aus einem git-log-Durchlauf

Commits, addierte und geloeschte Zeilen je Datei. Umbenennungen werden
ueber eine Alias-Kette auf den heutigen Namen zusammengefuehrt, sonst
zerfaellt die Historie einer Datei in zwei Haelften. Binaerdateien melden
'-' statt Zahlen und zaehlen als Commit ohne Zeilendelta.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Verlaufsreihe über die Snapshots

Fügt Snapshot-Auswahl, GitTreeSource und Analyzer zur eigentlichen Zeitreihe zusammen.

**Files:**
- Modify: `scripts/repo_map_history.py`
- Modify: `scripts/test_repo_map_history.py`

**Interfaces:**
- Consumes: `Snapshot`, `GitTreeSource`, `select_snapshots` (Tasks 2–3); `repo_map.analyze_paths` (Task 1)
- Produces:
  - `AREA_RULES: tuple[tuple[str, str], ...]`, `REST_AREA: str`, `AREAS: tuple[str, ...]`
  - `FLAGGED_SCORE: int`
  - `classify_area(path: str) -> str`
  - `@dataclass(frozen=True) class HistoryPoint` mit `label`, `commit`, `date`, `files: int`, `loc: int`, `flagged: int`, `score_sum: int`, `areas: dict[str, int]`, `dirs: dict[str, int]`
  - `build_history(root, snapshots, *, thresholds, include_generated=False) -> list[HistoryPoint]`

- [ ] **Step 1: Write the failing test**

An `scripts/test_repo_map_history.py` anhängen (oben `import repo_map` und `import repo_map_html` sowie `import repo_map_metrics as metrics` ergänzen):

```python
class TestClassifyArea:
    def test_backend_tests_wins_over_backend(self):
        assert history.classify_area("backend/tests/test_x.py") == "backend/tests"

    def test_backend_app_catches_the_rest_of_backend(self):
        assert history.classify_area("backend/app/services/x.py") == "backend/app"

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
        commit_file(repo, "backend/app/services/a.py", "1
2
", date="2026-01-10")

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map_history.py -k "ClassifyArea or BuildHistory or FlaggedThreshold" -q`
Expected: FAIL mit `AttributeError: module 'repo_map_history' has no attribute 'classify_area'`

- [ ] **Step 3: Write minimal implementation**

An `scripts/repo_map_history.py` anhängen. Der `repo_map`-Import steht bewusst oben bei den anderen Imports — `repo_map` importiert dieses Modul nur lokal in `main()`, es gibt also keinen Zyklus.

Oben ergänzen: `import repo_map` und `from repo_map_metrics import FileEntry, Thresholds`.

```python
# First match wins, so backend/tests must precede the general backend rule.
AREA_RULES: tuple[tuple[str, str], ...] = (
    ("backend/tests", "backend/tests/"),
    ("backend/app", "backend/"),
    ("client/src", "client/src/"),
    ("docs", "docs/"),
)
REST_AREA = "sonstiges"
AREAS: tuple[str, ...] = tuple(name for name, _ in AREA_RULES) + (REST_AREA,)

# Mirrors repo_map_html.CANDIDATE_SCORE. Kept as its own constant so the data
# module does not import the renderer; a test asserts the two stay equal.
FLAGGED_SCORE = 1


def classify_area(path: str) -> str:
    """Bucket a repo-relative path into one top-level area."""
    for name, prefix in AREA_RULES:
        if path.startswith(prefix):
            return name
    return REST_AREA


@dataclass(frozen=True)
class HistoryPoint:
    """The repo's totals at one snapshot."""

    label: str
    commit: str
    date: str
    files: int
    loc: int
    flagged: int
    score_sum: int
    areas: dict[str, int]
    dirs: dict[str, int]


def _point(snapshot: Snapshot, entries: list[FileEntry]) -> HistoryPoint:
    areas = {name: 0 for name in AREAS}
    dirs: dict[str, int] = {}
    for entry in entries:
        areas[classify_area(entry.path)] += entry.loc
        # Roll the file's LOC up into every ancestor directory, so the tree
        # can show a per-directory delta against the previous snapshot. Key
        # "" is the root, matching DirNode.path.
        dirs[""] = dirs.get("", 0) + entry.loc
        prefix = ""
        for part in entry.path.split("/")[:-1]:
            prefix = f"{prefix}/{part}" if prefix else part
            dirs[prefix] = dirs.get(prefix, 0) + entry.loc
    return HistoryPoint(
        label=snapshot.label,
        commit=snapshot.commit[:7],
        date=snapshot.date,
        files=len(entries),
        loc=sum(e.loc for e in entries),
        flagged=sum(1 for e in entries if e.score >= FLAGGED_SCORE),
        score_sum=sum(e.score for e in entries),
        areas=areas,
        dirs=dirs,
    )


def build_history(
    root: Path,
    snapshots: Iterable[Snapshot],
    *,
    thresholds: Thresholds,
    include_generated: bool = False,
) -> list[HistoryPoint]:
    """Analyse each snapshot and return the series, oldest first.

    One cache spans every snapshot. Files that did not change between two
    snapshots are the overwhelming majority, and each is analysed once.
    """
    cache: dict[tuple[str, str], FileEntry] = {}
    points: list[HistoryPoint] = []
    for snapshot in snapshots:
        source = GitTreeSource(root, snapshot.commit)
        paths = source.paths()
        misses = [p for p in paths if (source.identity(p), p) not in cache]
        source.prefetch(misses)
        entries = repo_map.analyze_paths(
            source,
            paths,
            thresholds=thresholds,
            include_generated=include_generated,
            cache=cache,
        )
        points.append(_point(snapshot, entries))
    return points
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map_history.py -k "ClassifyArea or BuildHistory or FlaggedThreshold" -q`
Expected: PASS, 11 Tests.

- [ ] **Step 5: Laufzeit gegen das echte Repo messen**

Run: `python -c "import sys,time; sys.path.insert(0,'scripts'); from pathlib import Path; import repo_map_history as h; from repo_map_metrics import Thresholds; t=time.time(); s=h.select_snapshots(Path('.')); p=h.build_history(Path('.'), s, thresholds=Thresholds()); print(len(p),'Punkte in',round(time.time()-t,1),'s'); [print(x.label, x.loc, x.flagged) for x in p]"`
Expected: rund `11 Punkte in 3.0 s`, LOC steigend über die Zeit. **Falls das über 30 s dauert, greift der Cache nicht** — Schlüsselbildung in `build_history` gegen `analyze_paths` prüfen.

- [ ] **Step 6: Run everything und Länge prüfen**

Run: `python -m pytest scripts/test_repo_map.py scripts/test_repo_map_history.py -q ; wc -l scripts/repo_map_history.py`
Expected: PASS. Datei unter 500 Zeilen.

- [ ] **Step 7: Commit**

```bash
git add scripts/repo_map_history.py scripts/test_repo_map_history.py
git commit -m "feat(scripts): Verlaufsreihe ueber die Repo-Map-Snapshots

Fuegt Snapshot-Auswahl, GitTreeSource und Analyzer zur Zeitreihe zusammen:
LOC, Dateizahl, geflaggte Dateien und Score-Summe je Snapshot, aufgeteilt
auf die Bereiche backend/app, backend/tests, client/src, docs und einen
Sammelposten. Ein gemeinsamer Cache ueber alle Snapshots sorgt dafuer,
dass jede unveraenderte Dateiversion genau einmal analysiert wird.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: CLI-Flags und JSON-Ausgabe

Macht die Historie über die Kommandozeile erreichbar. Opt-in, damit der tägliche Lauf schnell bleibt.

**Files:**
- Modify: `scripts/repo_map.py`
- Modify: `scripts/test_repo_map.py`

**Interfaces:**
- Consumes: `repo_map_history.select_snapshots`, `build_history`, `collect_churn`, `INTERVALS`, `HistoryPoint`, `Churn`
- Produces:
  - `history_json(points, churn) -> dict` in `repo_map_history.py`
  - `main()` akzeptiert `--history`, `--interval`, `--since`, `--json`

- [ ] **Step 1: Write the failing test**

An `scripts/test_repo_map_history.py` anhängen:

```python
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
```

In `scripts/test_repo_map.py` an `TestMain` anhängen:

```python
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
```

`import json` oben in `scripts/test_repo_map.py` ergänzen, falls noch nicht vorhanden.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map_history.py -k HistoryJson -q`
Expected: FAIL mit `AttributeError: module 'repo_map_history' has no attribute 'history_json'`

Run: `python -m pytest scripts/test_repo_map.py -k history -q`
Expected: FAIL mit `unrecognized arguments: --history`

- [ ] **Step 3: `history_json` implementieren**

An `scripts/repo_map_history.py` anhängen:

```python
def history_json(
    points: Iterable[HistoryPoint], churn: dict[str, Churn]
) -> dict:
    """Plain-data view of a history run, for the report and for --json."""
    return {
        "areas": list(AREAS),
        "points": [
            {
                "label": point.label,
                "commit": point.commit,
                "date": point.date,
                "files": point.files,
                "loc": point.loc,
                "flagged": point.flagged,
                "score": point.score_sum,
                "areas": dict(point.areas),
                "dirs": dict(point.dirs),
            }
            for point in points
        ],
        "churn": {
            path: {
                "commits": entry.commits,
                "added": entry.added,
                "deleted": entry.deleted,
                "last": entry.last_date,
            }
            for path, entry in churn.items()
        },
    }
```

- [ ] **Step 4: CLI verdrahten**

In `scripts/repo_map.py` in `main()` die Argumente ergänzen (nach `--include-generated`):

```python
    parser.add_argument(
        "--history",
        action="store_true",
        help="add the time axis: metric series over git snapshots plus churn",
    )
    parser.add_argument(
        "--interval",
        default="monthly",
        choices=("monthly", "weekly"),
        help="snapshot density for --history (default: monthly)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="limit --history to commits after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--json",
        default=None,
        help="also write the raw history data to this path",
    )
```

Nach dem Bau von `report` und vor dem Schreiben der HTML-Datei einfügen:

```python
    history_data = None
    if args.history:
        # Imported here for the same reason repo_map_html is: this module is
        # what repo_map_history imports, and a top-level import would close
        # the cycle.
        import repo_map_history

        snapshots = repo_map_history.select_snapshots(
            ROOT, interval=args.interval, since=args.since
        )
        if len(snapshots) < 2:
            print(
                f"history skipped: {len(snapshots)} snapshot(s) in range - "
                "a series needs at least two points"
            )
        else:
            points = repo_map_history.build_history(
                ROOT,
                snapshots,
                thresholds=thresholds,
                include_generated=args.include_generated,
            )
            churn = repo_map_history.collect_churn(ROOT, since=args.since)
            history_data = repo_map_history.history_json(points, churn)

    if args.json and history_data is not None:
        data_path = Path(args.json)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(
            json.dumps(history_data, indent=2), encoding="utf-8"
        )
```

`import json` oben in `scripts/repo_map.py` ergänzen.

Der HTML-Schreibaufruf bleibt in diesem Task **unverändert** — `render` lernt das `history`-Argument erst in Task 7. Task 6 endet grün, nicht mit einem bekannten Fehlschlag.

Die Abschlussmeldung um einen Verlaufshinweis ergänzen:

```python
    flagged = sum(1 for e in report.entries if e.score > 0)
    suffix = ""
    if history_data is not None:
        suffix = f", {len(history_data['points'])} history points"
    print(
        f"{len(report.entries)} files, {report.tree.loc:,} lines, "
        f"{flagged} flagged{suffix} -> {out}"
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map.py scripts/test_repo_map_history.py -q`
Expected: PASS, alles grün — auch die beiden neuen `TestMain`-Tests. Der Report enthält den Verlauf noch nicht, aber `--json` schreibt ihn bereits.

- [ ] **Step 6: Commit**

```bash
git add scripts/repo_map.py scripts/repo_map_history.py scripts/test_repo_map.py scripts/test_repo_map_history.py
git commit -m "feat(scripts): CLI-Flags fuer die Repo-Map-Historie

--history schaltet Verlauf und Churn ein, --interval waehlt die Dichte,
--since grenzt den Zeitraum ein, --json schreibt die Rohdaten heraus.
Opt-in, damit der taegliche Lauf bei rund 2,6 s bleibt. Unter zwei
Snapshots wird der Verlauf mit Hinweis ausgelassen statt leer gerendert.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Payload um Verlauf und Churn erweitern

Bringt die neuen Daten in die eingebettete JSON-Struktur. Reine Python-Arbeit, ohne Pixel.

**Files:**
- Modify: `scripts/repo_map_html.py`
- Modify: `scripts/test_repo_map.py`

**Interfaces:**
- Consumes: `history_json`-Struktur aus Task 6
- Produces:
  - `build_payload(report, *, history=None) -> dict` — neuer Schlüssel `"history"` (`None`, wenn nicht angefordert); jede Datei bekommt `"ch"` (Commits) und `"lt"` (zuletzt angefasst)
  - `render(report, *, history=None) -> str`

- [ ] **Step 1: Write the failing test**

An `scripts/test_repo_map.py` in `TestBuildPayload` anhängen:

```python
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
```

Und an `TestRender`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map.py -k "history or churn" -q`
Expected: FAIL mit `TypeError: build_payload() got an unexpected keyword argument 'history'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/repo_map_html.py`:

```python
def build_payload(report: Report, *, history: dict | None = None) -> dict:
    """Turn a report into the plain-data structure the page renders from.

    Files come out ordered by score, then by size - that ordering IS the work
    list, so it belongs in the data rather than in the browser.
    """
    files = sorted(report.entries, key=lambda e: (-e.score, -e.loc, e.path))
    churn = (history or {}).get("churn", {})
    return {
        "commit": report.commit,
        "generatedAt": report.generated_at,
        "thresholds": {
            "max_loc": report.thresholds.max_loc,
            "max_fn_loc": report.thresholds.max_fn_loc,
            "max_depth": report.thresholds.max_depth,
        },
        "totals": _totals(report.entries),
        "tree": _tree_payload(report.tree),
        "files": [_file_payload(entry, churn.get(entry.path)) for entry in files],
        "history": history,
    }
```

`_file_payload` bekommt den Churn-Eintrag und zwei neue Felder:

```python
def _file_payload(entry: FileEntry, churn: dict | None = None) -> dict:
    return {
        "p": entry.path,
        "e": entry.ext,
        "k": entry.kind,
        "loc": entry.loc,
        "code": entry.code,
        "cm": entry.comment,
        "bl": entry.blank,
        "sym": entry.symbols,
        "cls": entry.classes,
        "fn": entry.functions,
        "hk": entry.hooks,
        "ln": entry.longest_name,
        "ll": entry.longest_loc,
        "d": entry.max_depth,
        "est": entry.estimated,
        "gen": entry.generated,
        "s": entry.score,
        "r": list(entry.reasons),
        "ch": (churn or {}).get("commits", 0),
        "lt": (churn or {}).get("last"),
    }
```

Und `render`:

```python
def render(report: Report, *, history: dict | None = None) -> str:
    """Render the full HTML document for a report."""
    payload = build_payload(report, history=history)
    return _TEMPLATE.replace("__PAYLOAD__", _embed(payload))
```

In `scripts/repo_map.py` reicht `main()` die Daten jetzt durch — die eine Zeile, die Task 6 bewusst offen gelassen hat:

```python
    out.write_text(
        repo_map_html.render(report, history=history_data), encoding="utf-8"
    )
```

Die Verlaufs-Sektion selbst kommt in Task 8; damit `test_history_section_is_rendered_when_data_is_present` schon hier grün wird, in `_TEMPLATE` direkt vor der Directories-Sektion einfügen:

```html
  <section id="history" hidden>
    <h2>Verlauf</h2>
    <div id="history-chart"></div>
    <div id="history-hotspots"></div>
  </section>
```

und ganz am Ende von `_SCRIPT` ergänzen:

```javascript
if (DATA.history && DATA.history.points.length > 1) {
  document.getElementById("history").hidden = false;
}
```

Der Test prüft auf das Vorkommen von `2026-02` im Dokument — das steht über den eingebetteten Payload bereits drin.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map.py -q`
Expected: PASS — auch die beiden `TestMain`-Historientests aus Task 6 werden hier grün, weil `render` das `history`-Argument jetzt kennt.

- [ ] **Step 5: End-to-End gegen das echte Repo**

Run: `python scripts/repo_map.py --history --json history.json -o repo-map.html`
Expected: Ausgabe der Form `2685 files, 600,037 lines, 599 flagged, 11 history points -> repo-map.html`. Danach `python -c "import json; d=json.load(open('history.json')); print(len(d['points']), len(d['churn']))"` — beide Zahlen > 0. `history.json` anschließend löschen, sie gehört nicht ins Repo.

- [ ] **Step 6: Commit**

```bash
git add scripts/repo_map.py scripts/repo_map_html.py scripts/test_repo_map.py
git commit -m "feat(scripts): Verlauf und Churn im Repo-Map-Payload

build_payload und render nehmen die Historie entgegen; jede Dateizeile
traegt zusaetzlich Commit-Anzahl und Datum der letzten Aenderung. Ohne
--history bleibt der Payload unveraendert bis auf zwei Nullfelder.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Verlaufs-Sektion im Report

Zeichnet die Reihe, ergänzt die Delta-Spalte im Baum und stellt die Hotspot-Tabelle neben die Score-Rangliste.

**REQUIRED SUB-SKILL:** Vor der ersten Zeile Chart-Code die `dataviz`-Skill laden. Sie legt Farbwahl, Achsen, Legende und Tooltip-Regeln fest. Die Palette muss gegen den bestehenden dunklen `:root`-Block in `_STYLE` funktionieren (`--accent: #6fa8ff`, `--warn: #f0b429`, `--hot: #f2686b`, `--ok: #4fbf7f`, `--muted: #8d95a5`).

**Files:**
- Modify: `scripts/repo_map_html.py`
- Modify: `scripts/test_repo_map.py`

**Interfaces:**
- Consumes: `DATA.history` aus Task 7, `DATA.files[].ch`
- Produces: keine Python-API — Ausgabe ist die gerenderte Seite

- [ ] **Step 1: Write the failing test**

An `TestRender` in `scripts/test_repo_map.py` anhängen. Die Tests prüfen **Struktur, nicht Pixel** — der Rest ist Augenschein in Step 5:

```python
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

    def test_page_still_has_no_external_references(self):
        hist = {"areas": [], "points": [], "churn": {}}
        page = repo_map_html.render(make_report(), history=hist)
        for forbidden in ("http://", "https://", "<script src", "<link "):
            assert forbidden not in page, f"page must stay self-contained: {forbidden}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/test_repo_map.py -k "history_chart or external_references" -q`
Expected: FAIL mit `assert 'renderHistory' in page`

- [ ] **Step 3: Chart und Hotspots implementieren**

Zuerst die `dataviz`-Skill laden (siehe oben). Dann in `scripts/repo_map_html.py`:

**a)** In `_STYLE` ergänzen:

```css
.hist { display: grid; gap: 18px; }
.hist svg { width: 100%; height: 260px; display: block; }
.hist .axis { stroke: var(--line); stroke-width: 1; }
.hist .grid { stroke: var(--line); stroke-width: 1; stroke-dasharray: 2 4; }
.hist .tick { fill: var(--muted); font-size: 11px; }
.hist .lbl { fill: var(--muted); font-size: 11px; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px;
  color: var(--muted); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-right: 5px; vertical-align: middle; }
.delta.up { color: var(--warn); }
.delta.down { color: var(--ok); }
```

**b)** Die Verlaufs-Sektion in `_TEMPLATE` (aus Task 7) auf ihre endgültige Form bringen:

```html
  <section id="history" hidden>
    <h2>Verlauf</h2>
    <div class="hist">
      <div>
        <div class="legend" id="history-legend"></div>
        <div id="history-chart"></div>
      </div>
      <div>
        <div class="legend" id="flagged-legend"></div>
        <div id="flagged-chart"></div>
      </div>
    </div>
    <h2>Hotspots &mdash; Score &times; Commits</h2>
    <div class="wrap"><table>
      <thead><tr><th>File</th><th class="num">Score</th>
        <th class="num">LOC</th><th class="num">Commits</th>
        <th class="num">Hotspot</th><th class="num">Last</th></tr></thead>
      <tbody id="history-hotspots"></tbody>
    </table></div>
  </section>
```

**c)** In `_SCRIPT` vor dem Boot-Block einfügen:

```javascript
const SERIES_COLORS = ["#6fa8ff", "#4fbf7f", "#f0b429", "#f2686b", "#8d95a5"];
const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
}

function lineChart(host, labels, series, fmt) {
  const W = 720, H = 260, L = 62, R = 12, T = 12, B = 34;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: "none", role: "img" });
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const x = (i) => L + (labels.length < 2 ? 0
    : (i * (W - L - R)) / (labels.length - 1));
  const y = (v) => H - B - (v / max) * (H - T - B);

  for (let g = 0; g <= 4; g++) {
    const gy = T + (g * (H - T - B)) / 4;
    root.append(svg("line", { class: "grid", x1: L, x2: W - R, y1: gy, y2: gy }));
    const t = svg("text", { class: "tick", x: L - 8, y: gy + 4,
      "text-anchor": "end" });
    t.textContent = fmt(Math.round(max * (1 - g / 4)));
    root.append(t);
  }
  root.append(svg("line", { class: "axis", x1: L, x2: W - R,
    y1: H - B, y2: H - B }));

  labels.forEach((label, i) => {
    if (labels.length > 12 && i % 2) return;
    const t = svg("text", { class: "lbl", x: x(i), y: H - B + 16,
      "text-anchor": "middle" });
    t.textContent = label;
    root.append(t);
  });

  series.forEach((s, si) => {
    const color = SERIES_COLORS[si % SERIES_COLORS.length];
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join(" ");
    root.append(svg("path", { d, fill: "none", stroke: color, "stroke-width": 2 }));
    s.values.forEach((v, i) => {
      const dot = svg("circle", { cx: x(i), cy: y(v), r: 3, fill: color });
      const title = svg("title");
      title.textContent = `${s.name} \\u00b7 ${labels[i]}: ${fmt(v)}`;
      dot.append(title);
      root.append(dot);
    });
  });

  host.textContent = "";
  host.append(root);
}

function legend(host, names) {
  host.textContent = "";
  names.forEach((name, i) => {
    const span = el("span");
    const dot = el("i");
    dot.style.background = SERIES_COLORS[i % SERIES_COLORS.length];
    span.append(dot, document.createTextNode(name));
    host.append(span);
  });
}

function renderHistory() {
  const h = DATA.history;
  if (!h || h.points.length < 2) return;
  document.getElementById("history").hidden = false;

  const labels = h.points.map((p) => p.label);
  const areaSeries = h.areas
    .map((name) => ({ name,
      values: h.points.map((p) => p.areas[name] || 0) }))
    .filter((s) => s.values.some((v) => v > 0));
  legend(document.getElementById("history-legend"),
    areaSeries.map((s) => s.name));
  lineChart(document.getElementById("history-chart"), labels, areaSeries,
    (v) => nf.format(v));

  const flagged = [
    { name: "flagged files", values: h.points.map((p) => p.flagged) },
    { name: "score sum", values: h.points.map((p) => p.score) },
  ];
  legend(document.getElementById("flagged-legend"), flagged.map((s) => s.name));
  lineChart(document.getElementById("flagged-chart"), labels, flagged,
    (v) => nf.format(v));

  const rows = DATA.files
    .filter((f) => f.s > 0 && f.ch > 0)
    .map((f) => ({ f, hot: f.s * f.ch }))
    .sort((a, b) => b.hot - a.hot)
    .slice(0, 25);
  const body = document.getElementById("history-hotspots");
  body.textContent = "";
  for (const { f, hot } of rows) {
    const tr = el("tr");
    tr.append(el("td", "path", f.p));
    const score = el("td", "num " + scoreClass(f.s), String(f.s));
    tr.append(score);
    tr.append(el("td", "num", nf.format(f.loc)));
    tr.append(el("td", "num", nf.format(f.ch)));
    tr.append(el("td", "num", nf.format(hot)));
    tr.append(el("td", "num", f.lt || ""));
    body.append(tr);
  }
}
```

**d)** Churn-Spalte in die Dateitabelle aufnehmen — `COLUMNS` erweitern, vor `"r"`:

```javascript
  { key: "ch", label: "Commits", num: true },
```

**d2)** Delta-Spalte im Verzeichnisbaum. Zuerst das Grid in `_STYLE` um eine
Spalte erweitern — beide Regeln, sonst laufen Kopf und Zeilen auseinander:

```css
.tree summary { cursor: pointer; padding: 1px 0; list-style: none;
  display: grid; grid-template-columns: 1fr 90px 70px 80px 160px; gap: 8px;
  align-items: center; }
```

Dieselbe `grid-template-columns`-Angabe auch auf `.tree .leaf` anwenden, falls
dort eine eigene Regel existiert.

Dann in `_SCRIPT` vor `treeRow` einfügen:

```javascript
// LOC change of a directory between the last two snapshots, or null when
// history is off or the directory did not exist in the earlier one.
function dirDelta(path) {
  const h = DATA.history;
  if (!h || h.points.length < 2) return null;
  const now = h.points[h.points.length - 1].dirs || {};
  const before = h.points[h.points.length - 2].dirs || {};
  if (!(path in now) && !(path in before)) return null;
  return (now[path] || 0) - (before[path] || 0);
}
```

`treeRow` bekommt den Pfad und rendert die Zelle:

```javascript
function treeRow(name, loc, files, share, isLeaf, path) {
  const frag = document.createDocumentFragment();
  frag.append(el("span", "nm", name));
  frag.append(el("span", "num", nf.format(loc)));
  frag.append(el("span", "num", files === null ? "" : nf.format(files)));
  const d = path === undefined ? null : dirDelta(path);
  const cls = d === null || d === 0 ? "num" : d > 0 ? "num delta up" : "num delta down";
  frag.append(el("span", cls,
    d === null ? "" : (d > 0 ? "+" : "") + nf.format(d)));
  const bar = el("div", "bar");
  const fill = el("i");
  fill.style.width = Math.max(1, Math.round(share * 100)) + "%";
  if (isLeaf) fill.style.background = "var(--muted)";
  bar.append(fill);
  frag.append(bar);
  return frag;
}
```

Beide Aufrufstellen in `renderTree` nachziehen: der Verzeichnis-Aufruf übergibt
`n.path`, der Datei-Aufruf lässt das Argument weg (Dateien haben keinen
Verzeichnis-Rollup, ihre Aktivität steht als Commit-Spalte in der Tabelle):

```javascript
    s.append(treeRow(n.name || "/", n.loc, n.files,
      total ? n.loc / total : 0, false, n.path));
```

**e)** Boot-Block am Ende von `_SCRIPT` ersetzen (der Einzeiler aus Task 7 entfällt):

```javascript
head();
renderTree(DATA.tree, document.getElementById("tree"), DATA.totals.loc, 0);
buildTable();
renderHistory();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/test_repo_map.py scripts/test_repo_map_history.py -q`
Expected: PASS, alles grün.

- [ ] **Step 5: Den Report ansehen — das ist der eigentliche Abnahmetest**

Run: `python scripts/repo_map.py --history -o repo-map.html` und die Datei im Browser öffnen.

Prüfen:
- Die Verlaufs-Sektion ist sichtbar und zeigt rund 11 Punkte von `2025-11` bis heute.
- Die Bereichskurven steigen und die Summe wirkt plausibel gegenüber der Karte „Lines" im Kopf.
- Die zweite Kurve (flagged / score) ist lesbar und nicht von der Score-Summe plattgedrückt — falls doch, die beiden Reihen auf zwei getrennte Charts aufteilen.
- Die Hotspot-Tabelle zeigt oben lebenden Code (`sleep.py`, `plugins.py`, `lifespan.py`), nicht Lockfiles.
- Der Verzeichnisbaum hat eine Delta-Spalte, gewachsene Verzeichnisse stehen in `--warn`, geschrumpfte in `--ok`, und die Spalten von Kopf und Zeilen fluchten.
- Die Achsenbeschriftung überlappt bei `--interval weekly` nicht: `python scripts/repo_map.py --history --interval weekly -o repo-map-weekly.html` gegenprüfen.

- [ ] **Step 6: Laufzeit und Selbstanwendung prüfen**

Run: `wc -l scripts/repo_map*.py`
Expected: **jede** Datei unter 500 Zeilen. Wenn `repo_map_html.py` reißt, das Chart-JS in ein eigenes Modul `repo_map_html_history.py` ziehen und als String einbinden.

Run: `python scripts/repo_map.py -o repo-map.html`
Expected: weiterhin rund 2,6 s ohne `--history`.

- [ ] **Step 7: Aufräumen und committen**

```bash
rm -f repo-map.html repo-map-weekly.html history.json
git add scripts/repo_map_html.py scripts/test_repo_map.py
git commit -m "feat(scripts): Verlaufs-Sektion und Hotspots im Repo-Map-Report

Zwei Liniencharts aus dem eingebetteten Payload — LOC je Bereich und die
Entwicklung der geflaggten Dateien — plus eine Hotspot-Tabelle aus Score
mal Commits neben der bestehenden Score-Rangliste. Inline-SVG ohne
Chart-Library; die Seite bleibt ohne Netzzugriff benutzbar.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Abschluss

Nach Task 8:

1. `python -m pytest scripts/test_repo_map.py scripts/test_repo_map_history.py -q` — alles grün.
2. `wc -l scripts/repo_map*.py` — jede Datei unter 500 Zeilen.
3. `git log --oneline origin/main..HEAD` — acht Commits plus der Spec-Commit.
4. PR gegen `main` öffnen, sobald **#540 gemergt** ist; vorher auf `main` rebasen.
5. Worktree nach dem Merge entfernen: `git worktree remove .claude/worktrees/feat-repo-map-history` und `git branch -d feat/repo-map-history`.
