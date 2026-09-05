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
        # %x00 is git's own hex-byte placeholder for the NUL marker: passing
        # a literal NUL inside a subprocess argv string raises "ValueError:
        # embedded null character" on Windows (CreateProcess command lines
        # are NUL-terminated), so git must emit the byte, not Python.
        "--format=%x00%H %as",
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
