"""HTTP-Anfragen je Minute ueber alle API-Prozesse (#823).

Die Idle-Erkennung laeuft nur im Primary, Anfragen landen aber bei sechs
Prozessen. Jeder Prozess legt seine Zaehler-Eimer im SHM ab, der Leser
summiert die eigenen (aus dem Speicher) und die der anderen (aus den Dateien).
"""
import json
import os

import pytest

from app.services.power import http_activity
from app.services.power.http_activity import HttpActivityCounter


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


def _counter(clock, shm_dir, pid: int) -> HttpActivityCounter:
    return HttpActivityCounter(clock=clock, pid=pid, shm_dir=shm_dir)


def test_single_process_counts_its_own_requests(clock, shm_dir):
    a = _counter(clock, shm_dir, 101)
    for _ in range(10):
        a.record()

    assert a.requests_per_minute() == 10.0


def test_two_processes_add_up(clock, shm_dir):
    a = _counter(clock, shm_dir, 101)
    b = _counter(clock, shm_dir, 202)
    for _ in range(3):
        a.record()  # jeweils >= 2 s auseinander: jeder Stand landet in der Datei
        clock.now += 2.0
    b.record()  # erster Aufruf schreibt sofort

    assert a.requests_per_minute() == 4.0
    assert b.requests_per_minute() == 4.0


def test_own_file_is_not_counted_twice(clock, shm_dir):
    a = _counter(clock, shm_dir, 101)
    a.record()
    clock.now += 3
    a.record()  # schreibt erneut, die Datei enthaelt jetzt beide

    assert (shm_dir / "http_activity_101.json").exists()
    assert a.requests_per_minute() == 2.0


def test_buckets_expire_after_sixty_seconds(clock, shm_dir):
    clock.now = 10_000.0  # Beginn eines 10-s-Eimers
    a = _counter(clock, shm_dir, 101)
    b = _counter(clock, shm_dir, 202)
    a.record()
    b.record()

    clock.now = 10_060.0
    assert a.requests_per_minute() == 2.0

    clock.now = 10_061.0
    assert a.requests_per_minute() == 0.0


def test_writes_are_throttled_to_every_two_seconds(clock, shm_dir):
    a = _counter(clock, shm_dir, 101)
    reader = _counter(clock, shm_dir, 202)

    a.record()  # erster Aufruf: geschrieben
    a.record()
    a.record()
    clock.now += 1.0
    a.record()
    assert reader.requests_per_minute() == 1.0  # nur der erste Stand ist sichtbar

    clock.now += 1.0
    a.record()  # 2 s nach dem letzten Schreiben
    assert reader.requests_per_minute() == 5.0


def test_broken_file_is_ignored(clock, shm_dir):
    (shm_dir / "http_activity_303.json").write_text("{nicht json")
    (shm_dir / "http_activity_304.json").write_text(json.dumps({"buckets": "kaputt"}))
    (shm_dir / "http_activity_305.json").write_text(json.dumps([1, 2]))
    a = _counter(clock, shm_dir, 101)
    a.record()

    assert a.requests_per_minute() == 1.0


def test_missing_directory_never_raises(clock, tmp_path):
    a = _counter(clock, tmp_path / "gibt-es-nicht" / "tiefer", 101)
    a.record()

    assert a.requests_per_minute() == 1.0


def test_unwritable_directory_never_raises(clock, tmp_path):
    blocker = tmp_path / "datei"
    blocker.write_text("x")
    a = _counter(clock, blocker, 101)  # kein Verzeichnis

    a.record()
    assert a.requests_per_minute() == 1.0


def test_cleanup_removes_only_old_matching_files(clock, shm_dir):
    old = clock.now - 700
    names = [
        "http_activity_404.json",      # passt, alt -> weg
        "http_activity_abc.json",      # Name passt nicht
        "http_activity_405.json.tmp",  # Name passt nicht
        "xhttp_activity_406.json",     # Name passt nicht
        "telemetry.json",              # fremd
    ]
    for name in names:
        (shm_dir / name).write_text("{}")
        os.utime(shm_dir / name, (old, old))
    fresh = shm_dir / "http_activity_407.json"
    fresh.write_text("{}")
    os.utime(fresh, (clock.now - 30, clock.now - 30))
    nested = shm_dir / "sub"
    nested.mkdir()
    (nested / "http_activity_408.json").write_text("{}")
    os.utime(nested / "http_activity_408.json", (old, old))

    _counter(clock, shm_dir, 101).requests_per_minute()

    assert not (shm_dir / "http_activity_404.json").exists()
    for name in names[1:]:
        assert (shm_dir / name).exists(), name
    assert fresh.exists()
    assert (nested / "http_activity_408.json").exists()


def test_default_directory_follows_shm_module(clock, monkeypatch, tmp_path):
    from app.services.monitoring import shm

    monkeypatch.setattr(shm, "SHM_DIR", tmp_path)
    a = HttpActivityCounter(clock=clock, pid=111)
    a.record()

    assert (tmp_path / "http_activity_111.json").exists()


def test_sleep_wrappers_delegate_to_the_module_counter(clock, shm_dir, monkeypatch):
    from app.services.power import sleep as sleep_mode

    monkeypatch.setattr(http_activity, "_counter", _counter(clock, shm_dir, 101))
    sleep_mode.record_http_request()
    sleep_mode.record_http_request()

    assert sleep_mode.get_http_requests_per_minute() == 2.0


def test_symlinks_are_neither_read_nor_removed(clock, shm_dir, tmp_path_factory):
    """Geschrieben werden nur regulaere Dateien. Ein Link mit passendem Namen
    darf weder zum Lesen aus dem Verzeichnis hinausfuehren noch geloescht
    werden."""
    outside = tmp_path_factory.mktemp("outside") / "target.json"
    bucket = int(clock() // http_activity.BUCKET_SECONDS)
    outside.write_text('{"buckets": {"%d": 500}}' % bucket)
    link = shm_dir / "http_activity_4242.json"
    link.symlink_to(outside)

    counter = http_activity.HttpActivityCounter(clock=clock, pid=1, shm_dir=shm_dir)

    assert counter.requests_per_minute() == 0.0
    assert link.is_symlink()
    assert outside.exists()
