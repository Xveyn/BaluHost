"""The test suite must never read the host's logind inhibitor list (#771).

`SleepManagerService` asks `foreign_inhibitors.first_blocking()` before every
suspend, and that reads the real machine via `busctl`. On a box where some
other program holds a sleep block (the production box during an mdraid check:
"Disk Manager"), every test that expects a suspend to go through failed — red
locally, green in CI. The guard in `conftest.py` answers "no inhibitors"
instead of asking the host.

The probes below fake the *host*, not the guard: `shutil.which` finds a
`busctl` and `subprocess.run` would report a foreign block. A missing guard
therefore fails these tests on every machine, with or without a real lock.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from app.services.power import foreign_inhibitors as fi

HOST_BLOCK = json.dumps(
    {
        "type": "a(ssssuu)",
        "data": [[["sleep:idle", "Disk Manager", "mdraid-check-job", "block", 0, 4242]]],
    }
)


@pytest.fixture
def host_with_a_foreign_block(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """A machine on which `busctl` exists and reports a foreign sleep block."""
    calls: list[list[str]] = []

    def fake_run(argv, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(argv))
        return SimpleNamespace(stdout=HOST_BLOCK, returncode=0)

    monkeypatch.setattr(fi.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(fi.subprocess, "run", fake_run)
    return calls


def test_the_guard_does_not_ask_the_host(host_with_a_foreign_block):
    assert fi.first_blocking("sleep") is None
    assert fi.first_blocking("idle") is None
    assert host_with_a_foreign_block == []


def test_the_sleep_service_sees_no_foreign_block(host_with_a_foreign_block):
    from app.services.power.sleep import SleepManagerService

    assert SleepManagerService._foreign_inhibitor(object(), "sleep") is None  # type: ignore[arg-type]
    assert host_with_a_foreign_block == []


def test_the_guard_survives_a_monkeypatch_undo(host_with_a_foreign_block, monkeypatch):
    """Some tests call `monkeypatch.undo()` mid-test; the guard must outlive it.

    The undo also removes this test's fake host, so the real `subprocess.run`
    is back — with a guard that hung on the test's monkeypatch, the next line
    would run the machine's real `busctl`.
    """
    monkeypatch.undo()
    real_run = subprocess.run
    calls: list[object] = []

    def recording_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(args)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(fi.subprocess, "run", recording_run)

    assert fi.first_blocking("sleep") is None
    assert calls == []


def test_the_real_reader_stays_reachable(host_with_a_foreign_block, real_busctl_reader):
    """A test of `_run_busctl` itself needs the original, not the stand-in."""
    assert real_busctl_reader() == HOST_BLOCK
    assert len(host_with_a_foreign_block) == 1
    assert host_with_a_foreign_block[0][0] == "/usr/bin/busctl"


def test_an_explicit_runner_is_still_honoured():
    """The guard replaces the default reader only — tests of the filter logic
    pass their own `runner=` and must keep seeing what it returns."""
    found = fi.first_blocking("sleep", runner=lambda: HOST_BLOCK)

    assert found is not None
    assert found.who == "Disk Manager"


class TestCacheDoesNotLeakBetweenTests:
    """A reading cached by one test must be gone in the next.

    The module caches for four seconds of monotonic time — longer than most
    tests take. The two tests are an ordered pair: the first leaves a foreign
    block in the cache, the second must not see it. Run alone (or split across
    xdist workers) the second passes trivially; it can only ever fail for the
    reason it names.
    """

    def test_1_leaves_a_block_in_the_cache(self):
        assert fi.first_blocking("sleep", runner=lambda: HOST_BLOCK) is not None

    def test_2_starts_with_an_empty_cache(self):
        assert fi.first_blocking("sleep") is None
