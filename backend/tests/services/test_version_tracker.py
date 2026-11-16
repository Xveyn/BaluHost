"""`record_version_on_startup` under concurrent starts (#715).

Every process runs it at startup. With check-then-insert, several workers of
one deploy saw no row for the new commit, all inserted, and all but one died
on `uq_version_commit` — an ERROR line per deploy and a `times_started` that
lost counts.

The interleavings below are produced on purpose, not by threads: a hook on
the engine lets "the other worker" commit its statement at the exact point
between two statements of the call under test. That is the order PostgreSQL
allows under READ COMMITTED; SQLite alone would serialise the writers and
never show it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import __version__
from app.models.version_history import VersionHistory
from app.services import version_tracker

COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(autouse=True)
def fixed_git(monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple[bool, str]]:
    """Answer the two git questions without a repository."""
    answers = {"HEAD": (True, COMMIT), "--abbrev-ref": (True, "main")}

    def fake_git(*args: str) -> tuple[bool, str]:
        return answers["--abbrev-ref" if "--abbrev-ref" in args else "HEAD"]

    monkeypatch.setattr(version_tracker, "_run_git", fake_git)
    return answers


def _rows(db: Session) -> list[VersionHistory]:
    db.expire_all()
    return db.query(VersionHistory).all()


def _before_first(db: Session, statement_start: str, raw_sql: str, params: tuple) -> None:
    """Let another worker commit `raw_sql` just before the call under test
    sends its first statement beginning with `statement_start`."""
    engine = db.get_bind()
    fired: list[bool] = []

    def other_worker(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if fired or not statement.lstrip().upper().startswith(statement_start):
            return
        fired.append(True)
        dbapi = conn.connection.dbapi_connection
        dbapi.execute(raw_sql, params)
        dbapi.commit()

    event.listen(engine, "before_cursor_execute", other_worker)


def test_a_new_build_gets_its_row(db_session: Session):
    version_tracker.record_version_on_startup(db_session)

    (row,) = _rows(db_session)
    assert row.version == __version__
    assert row.git_commit == COMMIT
    assert row.git_commit_short == COMMIT[:7]
    assert row.git_branch == "main"
    assert row.python_version
    assert row.times_started == 1


def test_a_known_build_is_counted_again(db_session: Session):
    version_tracker.record_version_on_startup(db_session)
    long_ago = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.query(VersionHistory).update({"last_seen": long_ago, "python_version": "3.0.0"})
    db_session.commit()

    version_tracker.record_version_on_startup(db_session)

    (row,) = _rows(db_session)
    assert row.times_started == 2
    assert row.python_version != "3.0.0"
    assert row.last_seen.replace(tzinfo=timezone.utc) > long_ago + timedelta(days=29)


def test_the_branch_is_kept_when_git_cannot_name_it(db_session: Session, fixed_git):
    version_tracker.record_version_on_startup(db_session)
    fixed_git["--abbrev-ref"] = (False, "")

    version_tracker.record_version_on_startup(db_session)

    (row,) = _rows(db_session)
    assert row.git_branch == "main"
    assert row.times_started == 2


def test_without_git_the_commit_is_unknown(db_session: Session, fixed_git):
    fixed_git["HEAD"] = (False, "")

    version_tracker.record_version_on_startup(db_session)

    (row,) = _rows(db_session)
    assert row.git_commit == "unknown"
    assert row.git_commit_short == "unknown"


def test_another_worker_inserting_first_is_not_an_error(db_session: Session, caplog):
    """Both workers found no row; the other one's INSERT lands first."""
    _before_first(
        db_session,
        "INSERT INTO VERSION_HISTORY",
        "INSERT INTO version_history (version, git_commit, git_commit_short) VALUES (?, ?, ?)",
        (__version__, COMMIT, COMMIT[:7]),
    )

    with caplog.at_level(logging.WARNING, logger=version_tracker.logger.name):
        version_tracker.record_version_on_startup(db_session)

    assert [r.getMessage() for r in caplog.records] == []
    (row,) = _rows(db_session)
    assert row.times_started == 2, "both starts count: the other worker's and ours"


def test_a_concurrent_count_is_not_overwritten(db_session: Session):
    """The count is raised in the database, not written back from a value this
    process read earlier — another worker's increment in between survives."""
    version_tracker.record_version_on_startup(db_session)
    _before_first(
        db_session,
        "UPDATE VERSION_HISTORY",
        "UPDATE version_history SET times_started = 41 WHERE git_commit = ?",
        (COMMIT,),
    )

    version_tracker.record_version_on_startup(db_session)

    (row,) = _rows(db_session)
    assert row.times_started == 42


def test_a_database_error_never_stops_the_startup(db_session: Session, monkeypatch, caplog):
    def broken(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("database is gone")

    monkeypatch.setattr(db_session, "execute", broken)
    monkeypatch.setattr(db_session, "query", broken)

    with caplog.at_level(logging.ERROR, logger=version_tracker.logger.name):
        version_tracker.record_version_on_startup(db_session)

    assert "non-fatal" in caplog.text
