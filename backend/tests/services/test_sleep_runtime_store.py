"""Der Sleep-Zustand des Primary in einer Singleton-Zeile (#823).

Der Store ist die Leseseite fuer alle Prozesse, die die Loops nicht betreiben.
`read_state` muss "unbekannt" (None) klar von "wach" trennen: eine frisch
migrierte Datenbank oder ein kaputter Wert darf nicht als Tatsache gelten.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.sleep import SleepRuntimeState
from app.schemas.sleep import SleepState
from app.services.power import sleep_runtime_store as store


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_nothing_published_reads_as_unknown(db):
    assert store.read_state(db) is None


def test_publish_then_read_round_trip(db):
    since = datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc)

    assert store.publish_state(db, SleepState.SOFT_SLEEP, since) is True

    state, read_since = store.read_state(db)
    assert state is SleepState.SOFT_SLEEP
    assert read_since == since
    assert read_since.tzinfo is not None


def test_publish_overwrites_the_singleton_row(db):
    store.publish_state(db, SleepState.SOFT_SLEEP, datetime.now(timezone.utc))
    store.publish_state(db, SleepState.AWAKE, datetime.now(timezone.utc))

    assert db.query(SleepRuntimeState).count() == 1
    assert store.read_state(db)[0] is SleepState.AWAKE


def test_publish_records_the_writer_pid(db, monkeypatch):
    monkeypatch.setattr(store.os, "getpid", lambda: 4242)

    store.publish_state(db, SleepState.AWAKE, None)

    assert db.get(SleepRuntimeState, 1).updated_by_pid == 4242


def test_unknown_state_value_reads_as_unknown(db):
    db.add(SleepRuntimeState(id=1, current_state="napping"))
    db.commit()

    assert store.read_state(db) is None


def test_unreadable_database_reads_as_unknown():
    engine = create_engine("sqlite://")  # keine Tabellen
    session = sessionmaker(bind=engine)()

    assert store.read_state(session) is None


def test_failed_publish_returns_false():
    engine = create_engine("sqlite://")
    session = sessionmaker(bind=engine)()

    assert store.publish_state(session, SleepState.AWAKE, None) is False


# ─── Statusdetails (#834) ────────────────────────────────────────────


def test_snapshot_of_nothing_published_is_unknown(db):
    assert store.read_snapshot(db) is None


def test_details_round_trip(db):
    details = store.SleepRuntimeDetails(
        idle_seconds=450.0,
        paused_services=["monitoring_orchestrator", "disk_io_monitor"],
        spun_down_disks=["/dev/sda"],
    )

    assert store.publish_state(db, SleepState.SOFT_SLEEP, None, details) is True

    snap = store.read_snapshot(db)
    assert snap.state is SleepState.SOFT_SLEEP
    assert snap.idle_seconds == 450.0
    assert snap.paused_services == ["monitoring_orchestrator", "disk_io_monitor"]
    assert snap.spun_down_disks == ["/dev/sda"]


def test_publish_without_details_reads_as_empty_details(db):
    store.publish_state(db, SleepState.AWAKE, None)

    snap = store.read_snapshot(db)
    assert (snap.idle_seconds, snap.paused_services, snap.spun_down_disks) == (0.0, [], [])


def test_publish_without_details_clears_older_details(db):
    """Jede Veroeffentlichung ist der ganze Stand -- nichts bleibt von der
    vorigen stehen."""
    store.publish_state(
        db, SleepState.SOFT_SLEEP, None,
        store.SleepRuntimeDetails(spun_down_disks=["/dev/sda"]),
    )
    store.publish_state(db, SleepState.AWAKE, None)

    assert store.read_snapshot(db).spun_down_disks == []


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        '"text"',
        '{"idle_seconds": "viel", "paused_services": "x", "spun_down_disks": 3}',
        '{"paused_services": [1, null, "ok"]}',
    ],
)
def test_unreadable_details_cost_the_details_not_the_state(db, raw):
    store.publish_state(db, SleepState.SOFT_SLEEP, None)
    db.get(SleepRuntimeState, 1).details_json = raw
    db.commit()

    snap = store.read_snapshot(db)

    assert snap.state is SleepState.SOFT_SLEEP
    assert snap.idle_seconds == 0.0
    assert all(isinstance(s, str) for s in snap.paused_services)
    assert snap.spun_down_disks == []


def test_read_state_still_returns_state_and_since(db):
    since = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    store.publish_state(
        db, SleepState.SOFT_SLEEP, since, store.SleepRuntimeDetails(idle_seconds=5.0),
    )

    assert store.read_state(db) == (SleepState.SOFT_SLEEP, since)
