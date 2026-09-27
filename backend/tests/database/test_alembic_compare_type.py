"""Autogenerate on SQLite must not report the pill_id phantom (#549).

Migration 71fe791d28d6 widens status_bar_pill_config.pill_id from
VARCHAR(32) to VARCHAR(96) on PostgreSQL only - SQLite neither can
ALTER COLUMN TYPE nor enforces the length. So every SQLite dev database
keeps VARCHAR(32), and autogenerate reported a modify_type for it on every
run until someone deleted it by hand.

The filter must stay narrow. A blanket "ignore VARCHAR length on SQLite"
would have hidden exactly the missing widening that 71fe791d28d6 fixed after
it 500'd in production. So the tests also pin that every OTHER length
mismatch is still reported, including a different length on this column.

The database is built with create_all() rather than `alembic upgrade head`:
the chain does not run from an empty database (#648).
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

import app.models  # noqa: F401  - registers every model on Base.metadata
from app.core.alembic_compare import compare_type
from app.models.base import Base

TABLE = "status_bar_pill_config"


def _engine_with_status_bar_lengths(tmp_path, **lengths: int) -> sa.Engine:
    """SQLite DB matching the models, except given String columns of TABLE."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'autogen.db'}")
    Base.metadata.create_all(engine)

    shrunk = Base.metadata.tables[TABLE].to_metadata(sa.MetaData())
    for column, length in lengths.items():
        shrunk.c[column].type = sa.String(length)
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE {TABLE}"))
        shrunk.create(conn)
    return engine


def _type_changes(engine: sa.Engine, compare) -> list[tuple[str, str, object, object]]:
    """(table, column, db type, model type) for every modify_type diff."""
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": compare})
        diffs = compare_metadata(ctx, Base.metadata)
    changes = []
    for diff in diffs:
        # modify_* ops come wrapped in a list, add/remove ops as bare tuples
        for op in diff if isinstance(diff, list) else [diff]:
            if op[0] == "modify_type":
                changes.append((op[2], op[3], op[5], op[6]))
    return changes


def _columns(changes) -> list[tuple[str, str]]:
    return [(table, column) for table, column, _old, _new in changes]


def test_default_comparison_reports_the_phantom(tmp_path):
    """Precondition: the fixture reproduces the dev-DB state of #549."""
    engine = _engine_with_status_bar_lengths(tmp_path, pill_id=32)

    assert _columns(_type_changes(engine, True)) == [(TABLE, "pill_id")]


def test_hook_silences_the_phantom(tmp_path):
    engine = _engine_with_status_bar_lengths(tmp_path, pill_id=32)

    assert _type_changes(engine, compare_type) == []


def test_hook_still_reports_other_length_mismatches(tmp_path):
    engine = _engine_with_status_bar_lengths(tmp_path, pill_id=32, visibility=4)

    assert _columns(_type_changes(engine, compare_type)) == [(TABLE, "visibility")]


def test_hook_defers_on_postgresql():
    """On PostgreSQL the widening really ran - a 32 there is real drift."""
    from types import SimpleNamespace

    context = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    column = Base.metadata.tables[TABLE].c.pill_id

    assert compare_type(context, None, column, sa.String(32), sa.String(96)) is None


@pytest.mark.parametrize("db_length", [64, 128])
def test_hook_still_reports_any_other_pill_id_length(tmp_path, db_length):
    """Only 32 -> 96 is the known phantom; anything else is a real drift."""
    engine = _engine_with_status_bar_lengths(tmp_path, pill_id=db_length)

    assert _columns(_type_changes(engine, compare_type)) == [(TABLE, "pill_id")]
