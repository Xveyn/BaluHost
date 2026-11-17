"""Laufende Uploads ueber alle API-Prozesse (#834).

Die Idle-Erkennung laeuft nur im Primary, ein Upload aber in dem Prozess, der
die Anfrage bedient -- und ein Chunk-Upload in mehreren nacheinander. Der
Primary sah deshalb nur seine eigenen Uploads und konnte waehrend eines Uploads
auf einem anderen Worker einschlafen.

Jeder Prozess legt im SHM ab, welche Uploads er zuletzt angefasst hat und ob
sie noch laufen. Der Leser fuehrt das je Upload zusammen (die juengste Meldung
gilt) und zaehlt, was laeuft. Eine Meldung gilt nur fuer ein Zeitfenster: ein
Upload, der nie beendet wurde, darf den Idle-Sleep nicht bis zum naechsten
Neustart blockieren.
"""
import json
import os
from unittest.mock import MagicMock

import pytest

from app.schemas.sleep import ActivityMetrics
from app.services import upload_activity
from app.services import upload_progress as upload_progress_service
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.services.upload_activity import ACTIVE_WINDOW_SECONDS, UploadActivityTracker
from app.services.upload_progress import get_upload_progress_manager


class Clock:
    def __init__(self, now: float = 10_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def shm_dir(tmp_path):
    return tmp_path


def _tracker(clock, shm_dir, pid: int) -> UploadActivityTracker:
    return UploadActivityTracker(clock=clock, pid=pid, shm_dir=shm_dir)


def _file(shm_dir, pid: int):
    return shm_dir / f"upload_activity_{pid}.json"


# ─── Zaehlen ─────────────────────────────────────────────────────────


def test_nothing_reported_means_no_uploads(clock, shm_dir):
    assert _tracker(clock, shm_dir, 101).active_uploads() == 0


def test_single_process_counts_its_own_uploads(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")
    a.touch("u2")

    assert a.active_uploads() == 2


def test_touching_the_same_upload_again_counts_it_once(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    for _ in range(5):
        a.touch("u1")

    assert a.active_uploads() == 1


def test_two_processes_add_up(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    b = _tracker(clock, shm_dir, 202)
    a.touch("u1")
    b.touch("u2")
    b.touch("u3")

    assert a.active_uploads() == 3
    assert b.active_uploads() == 3


def test_primary_without_uploads_sees_a_follower_upload(clock, shm_dir):
    """Der Fall aus dem Issue."""
    primary = _tracker(clock, shm_dir, 101)
    follower = _tracker(clock, shm_dir, 202)
    follower.touch("u1")

    assert primary.active_uploads() == 1


def test_own_file_is_not_counted_twice(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")

    assert _file(shm_dir, 101).exists()
    assert a.active_uploads() == 1


def test_finished_upload_counts_no_longer_at_once(clock, shm_dir):
    primary = _tracker(clock, shm_dir, 101)
    follower = _tracker(clock, shm_dir, 202)
    follower.touch("u1")
    clock.now += 0.1  # weit unter dem Schreibabstand
    follower.finish("u1")

    assert primary.active_uploads() == 0
    assert follower.active_uploads() == 0


# ─── Ein Upload, den mehrere Prozesse anfassen (Chunk-Upload) ────────


def test_upload_touched_by_three_processes_counts_once(clock, shm_dir):
    a, b, c = (_tracker(clock, shm_dir, pid) for pid in (101, 202, 303))
    a.touch("u1")
    clock.now += 5
    b.touch("u1")
    clock.now += 5
    c.touch("u1")

    for tracker in (a, b, c):
        assert tracker.active_uploads() == 1


def test_finish_in_another_process_ends_the_upload_everywhere(clock, shm_dir):
    """`init` auf A, Chunks auf B, `complete` auf C."""
    a, b, c = (_tracker(clock, shm_dir, pid) for pid in (101, 202, 303))
    a.touch("u1")
    clock.now += 5
    b.touch("u1")
    clock.now += 5
    c.finish("u1")

    for tracker in (a, b, c):
        assert tracker.active_uploads() == 0


def test_finish_wins_over_a_touch_at_the_same_instant(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    b = _tracker(clock, shm_dir, 202)
    a.touch("u1")
    b.finish("u1")  # gleiche Uhrzeit

    assert a.active_uploads() == 0
    assert b.active_uploads() == 0


def test_older_finish_does_not_end_a_newer_upload_with_the_same_id(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    b = _tracker(clock, shm_dir, 202)
    a.finish("u1")
    clock.now += 5
    b.touch("u1")

    assert a.active_uploads() == 1


# ─── Ein haengengebliebener Upload blockiert nicht dauerhaft ─────────


def test_own_upload_expires_without_further_activity(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")

    clock.now += ACTIVE_WINDOW_SECONDS - 1
    assert a.active_uploads() == 1
    clock.now += 2
    assert a.active_uploads() == 0


def test_upload_of_another_process_expires_without_further_activity(clock, shm_dir):
    primary = _tracker(clock, shm_dir, 101)
    follower = _tracker(clock, shm_dir, 202)
    follower.touch("u1")

    clock.now += ACTIVE_WINDOW_SECONDS - 1
    assert primary.active_uploads() == 1
    clock.now += 2
    assert primary.active_uploads() == 0


def test_ongoing_activity_keeps_an_upload_counted(clock, shm_dir):
    """Ein langer Upload meldet sich mit jedem Fortschritt neu."""
    primary = _tracker(clock, shm_dir, 101)
    follower = _tracker(clock, shm_dir, 202)
    for _ in range(10):
        follower.touch("u1")
        clock.now += ACTIVE_WINDOW_SECONDS / 2

    assert primary.active_uploads() == 1


def test_one_stuck_upload_does_not_keep_a_live_one_company(clock, shm_dir):
    """Je Upload, nicht je Prozess: der haengende laeuft aus, auch wenn
    derselbe Prozess weiter Aktivitaet hat."""
    a = _tracker(clock, shm_dir, 101)
    a.touch("stuck")
    for _ in range(4):
        clock.now += ACTIVE_WINDOW_SECONDS / 2
        a.touch("live")

    assert a.active_uploads() == 1


def test_expired_entries_are_forgotten(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")
    a.finish("u2")
    clock.now += ACTIVE_WINDOW_SECONDS + 1
    a.touch("u3")

    assert set(json.loads(_file(shm_dir, 101).read_text())["uploads"]) == {"u3"}


# ─── Schreiben ───────────────────────────────────────────────────────


def test_repeated_touch_is_written_at_most_every_two_seconds(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")
    first = json.loads(_file(shm_dir, 101).read_text())

    clock.now += 1.0
    a.touch("u1")
    assert json.loads(_file(shm_dir, 101).read_text()) == first

    clock.now += 1.5
    a.touch("u1")
    assert json.loads(_file(shm_dir, 101).read_text())["written_at"] == clock.now


def test_new_upload_is_written_immediately(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")
    clock.now += 0.1
    a.touch("u2")

    assert set(json.loads(_file(shm_dir, 101).read_text())["uploads"]) == {"u1", "u2"}


def test_finish_is_written_immediately(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")
    clock.now += 0.1
    a.finish("u1")

    assert json.loads(_file(shm_dir, 101).read_text())["uploads"]["u1"][1] is False


# ─── Nie eine Anfrage scheitern lassen ───────────────────────────────


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"uploads": []}',
        '{"uploads": {"u1": "aktiv"}}',
        '{"uploads": {"u1": [true, true]}}',
        '{"uploads": {"u1": ["gestern", true]}}',
        '{"uploads": {"u1": [10000.0, "ja"]}}',
        '{"uploads": {"u1": [10000.0]}}',
        '{"written_at": 10000.0}',
    ],
)
def test_broken_file_is_ignored(clock, shm_dir, content):
    _file(shm_dir, 202).write_text(content)

    assert _tracker(clock, shm_dir, 101).active_uploads() == 0


def test_broken_entry_does_not_cost_the_good_ones(clock, shm_dir):
    _file(shm_dir, 202).write_text(json.dumps(
        {"uploads": {"bad": "x", "good": [clock.now, True]}}
    ))

    assert _tracker(clock, shm_dir, 101).active_uploads() == 1


def test_entry_from_the_future_is_ignored(clock, shm_dir):
    """Eine Uhr, die zurueckgestellt wurde, darf keinen Upload erfinden, der
    dann ueber das Fenster hinaus zaehlt."""
    _file(shm_dir, 202).write_text(json.dumps(
        {"uploads": {"u1": [clock.now + 3600, True]}}
    ))

    assert _tracker(clock, shm_dir, 101).active_uploads() == 0


def test_missing_directory_never_raises(clock, tmp_path):
    a = _tracker(clock, tmp_path / "gone", 101)
    a.touch("u1")

    assert a.active_uploads() == 1


def test_unwritable_directory_never_raises(clock, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    a = _tracker(clock, blocker / "sub", 101)

    a.touch("u1")
    a.finish("u2")

    assert a.active_uploads() == 1


def test_old_files_of_gone_processes_are_removed(clock, shm_dir):
    old = _file(shm_dir, 303)
    old.write_text(json.dumps({"uploads": {"u1": [0.0, True]}}))
    os.utime(old, (clock.now - 7200, clock.now - 7200))
    unrelated = shm_dir / "telemetry.json"
    unrelated.write_text("{}")
    os.utime(unrelated, (clock.now - 7200, clock.now - 7200))

    assert _tracker(clock, shm_dir, 101).active_uploads() == 0
    assert not old.exists()
    assert unrelated.exists()


def test_symlinks_are_neither_read_nor_removed(clock, shm_dir, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "target.json"
    outside.write_text(json.dumps({"uploads": {"u1": [clock.now, True]}}))
    link = _file(shm_dir, 202)
    link.symlink_to(outside)

    assert _tracker(clock, shm_dir, 101).active_uploads() == 0
    assert outside.exists()
    assert link.is_symlink()


def test_default_directory_follows_shm_module(clock, monkeypatch, tmp_path):
    from app.services.monitoring import shm

    monkeypatch.setattr(shm, "SHM_DIR", tmp_path)
    a = UploadActivityTracker(clock=clock, pid=101)
    a.touch("u1")

    assert _file(tmp_path, 101).exists()


def test_reset_forgets_everything(clock, shm_dir):
    a = _tracker(clock, shm_dir, 101)
    a.touch("u1")

    a.reset()

    assert a.active_uploads() == 0


# ─── UploadProgressManager meldet seine Sitzungen ────────────────────


@pytest.fixture
def module_tracker(clock, shm_dir, monkeypatch):
    """Der Modul-Tracker auf einem eigenen Verzeichnis, mit dem echten Manager."""
    upload_progress_service._manager = None
    tracker = UploadActivityTracker(clock=clock, pid=101, shm_dir=shm_dir)
    monkeypatch.setattr(upload_activity, "_tracker", tracker)
    yield tracker
    upload_progress_service._manager = None


@pytest.mark.asyncio
async def test_manager_reports_a_new_session(module_tracker, clock, shm_dir):
    other_process = _tracker(clock, shm_dir, 202)

    get_upload_progress_manager().create_upload_session("a.bin", 100)

    assert upload_activity.active_uploads() == 1
    assert other_process.active_uploads() == 1


@pytest.mark.asyncio
async def test_manager_reports_completion_at_once(module_tracker, clock, shm_dir):
    """Die Sitzung bleibt nach dem Abschluss noch stehen (bis zu 60 s), zaehlt
    aber nicht mehr als laufender Upload."""
    other_process = _tracker(clock, shm_dir, 202)
    manager = get_upload_progress_manager()
    upload_id = manager.create_upload_session("a.bin", 100)

    await manager.complete_upload(upload_id)

    assert upload_activity.active_uploads() == 0
    assert other_process.active_uploads() == 0


@pytest.mark.asyncio
async def test_manager_reports_failure_at_once(module_tracker, clock, shm_dir):
    other_process = _tracker(clock, shm_dir, 202)
    manager = get_upload_progress_manager()
    upload_id = manager.create_upload_session("a.bin", 100)

    await manager.fail_upload(upload_id, "boom")

    assert other_process.active_uploads() == 0


@pytest.mark.asyncio
async def test_progress_updates_keep_a_long_upload_counted(module_tracker, clock, shm_dir):
    other_process = _tracker(clock, shm_dir, 202)
    manager = get_upload_progress_manager()
    upload_id = manager.create_upload_session("a.bin", 100)

    for uploaded in range(10, 60, 10):
        clock.now += ACTIVE_WINDOW_SECONDS / 2
        await manager.update_progress(upload_id, uploaded)

    assert other_process.active_uploads() == 1


@pytest.mark.asyncio
async def test_abandoned_session_stops_counting_after_the_window(module_tracker, clock, shm_dir):
    """Kein complete, kein fail."""
    other_process = _tracker(clock, shm_dir, 202)
    manager = get_upload_progress_manager()
    upload_id = manager.create_upload_session("a.bin", 100)

    clock.now += ACTIVE_WINDOW_SECONDS + 1

    assert manager.get_progress(upload_id).status == "uploading"
    assert upload_activity.active_uploads() == 0
    assert other_process.active_uploads() == 0


@pytest.mark.asyncio
async def test_reporting_failure_never_reaches_the_upload(module_tracker, monkeypatch):
    monkeypatch.setattr(
        upload_activity, "touch", MagicMock(side_effect=RuntimeError("shm down"))
    )
    monkeypatch.setattr(
        upload_activity, "finish", MagicMock(side_effect=RuntimeError("shm down"))
    )
    manager = get_upload_progress_manager()

    upload_id = manager.create_upload_session("a.bin", 100)
    await manager.update_progress(upload_id, 10)
    await manager.complete_upload(upload_id)

    assert manager.get_progress(upload_id).status == "completed"


# ─── Idle-Erkennung ──────────────────────────────────────────────────


def test_idle_detection_counts_uploads_of_other_processes(module_tracker, clock, shm_dir):
    SleepManagerService._instance = None
    svc = SleepManagerService(DevSleepBackend())
    _tracker(clock, shm_dir, 202).touch("u1")

    metrics = svc._get_activity_metrics()

    assert metrics.active_uploads == 1
    config = MagicMock(
        idle_cpu_threshold=100.0, idle_disk_io_threshold=1e9, idle_http_threshold=1e9,
    )
    quiet = ActivityMetrics(active_uploads=metrics.active_uploads)
    assert svc._is_system_idle(config, quiet) is False


def test_idle_detection_without_uploads_anywhere(module_tracker):
    SleepManagerService._instance = None
    svc = SleepManagerService(DevSleepBackend())

    assert svc._get_activity_metrics().active_uploads == 0


# ─── Statusleiste ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_bar_counts_uploads_of_all_processes(module_tracker, clock, shm_dir):
    from app.services.status_bar import collectors

    get_upload_progress_manager().create_upload_session("a.bin", 100)
    _tracker(clock, shm_dir, 202).touch("other")

    result = await collectors.collect_uploads(MagicMock(), "admin")

    assert result["label_key"] == "pills.uploads.live"
    assert result["value"] == "2"


@pytest.mark.asyncio
async def test_status_bar_shows_nothing_without_uploads(module_tracker):
    from app.services.status_bar import collectors

    assert await collectors.collect_uploads(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_status_bar_forgets_an_abandoned_upload(module_tracker, clock):
    """Bisher stand die Anzeige bis zum Neustart des Workers."""
    from app.services.status_bar import collectors

    get_upload_progress_manager().create_upload_session("a.bin", 100)
    clock.now += ACTIVE_WINDOW_SECONDS + 1

    assert await collectors.collect_uploads(MagicMock(), "admin") is None
