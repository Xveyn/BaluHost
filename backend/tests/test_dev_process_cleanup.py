"""Dev launchers must only terminate processes that belong to THEIR checkout (#763).

``start_dev.py`` / ``kill_dev.py`` used ``pkill -f <pattern>``, which matches the
whole command line and knows neither user nor directory. On a host where the
production services run under the same user, that shot production down.
"""
import importlib.util
import os
import pathlib
import re
import signal
import subprocess
import sys
import time

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "dev_process_cleanup", REPO_ROOT / "dev_process_cleanup.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cleanup = _load()

pytestmark = pytest.mark.skipif(
    not pathlib.Path("/proc/self/cmdline").exists(), reason="needs /proc (Linux)"
)

MARKER = "balu-test-marker-763"


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    (root / "backend").mkdir(parents=True)
    return root


@pytest.fixture
def elsewhere(tmp_path):
    other = tmp_path / "opt-baluhost" / "backend"
    other.mkdir(parents=True)
    return other


@pytest.fixture
def spawn():
    """Start sleeping processes whose command line carries MARKER; reap them after."""
    procs: list[subprocess.Popen] = []

    def _spawn(cwd, *extra_args):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", MARKER, *extra_args],
            cwd=cwd,
        )
        procs.append(proc)
        # The command line is visible as soon as exec has happened.
        deadline = time.monotonic() + 5
        while MARKER.encode() not in pathlib.Path(f"/proc/{proc.pid}/cmdline").read_bytes():
            assert time.monotonic() < deadline, "child never exec'd"
            time.sleep(0.01)
        return proc

    yield _spawn
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


class TestIsOwned:
    """The ownership rule on its own: cwd under the root OR a path under the root
    in the command line. Anything undecidable is NOT ours."""

    root = pathlib.Path("/home/sven/projects/BaluHost")

    def test_cwd_inside_root(self):
        assert cleanup.is_owned(self.root / "backend", ["python", "x.py"], self.root)

    def test_cwd_outside_root(self):
        assert not cleanup.is_owned(
            pathlib.Path("/opt/baluhost/backend"), ["python", "x.py"], self.root
        )

    def test_unreadable_cwd_and_no_path_is_not_ours(self):
        """The production backend's main process refuses /proc/<pid>/cwd even to
        its own user, so 'cannot tell' has to mean 'leave it alone'."""
        assert not cleanup.is_owned(None, ["uvicorn", "app.main:app"], self.root)

    def test_unreadable_cwd_but_absolute_path_inside_root(self):
        argv = [str(self.root / "backend/.venv/bin/python"), "-m", "uvicorn", "app.main:app"]
        assert cleanup.is_owned(None, argv, self.root)

    def test_unreadable_cwd_and_absolute_path_outside_root(self):
        argv = [
            "/opt/baluhost/backend/.venv/bin/python3",
            "/opt/baluhost/backend/.venv/bin/uvicorn",
            "app.main:app",
        ]
        assert not cleanup.is_owned(None, argv, self.root)

    def test_sibling_directory_sharing_the_prefix_is_not_inside(self):
        """A string-prefix check would call /…/BaluHost-old part of /…/BaluHost."""
        sibling = pathlib.Path("/home/sven/projects/BaluHost-old/backend")
        assert not cleanup.is_owned(sibling, ["python"], self.root)
        assert not cleanup.is_owned(
            None, ["/home/sven/projects/BaluHost-old/backend/.venv/bin/python"], self.root
        )

    def test_dotdot_does_not_smuggle_a_path_into_the_root(self):
        argv = [str(self.root / ".." / ".." / "elsewhere" / "python")]
        assert not cleanup.is_owned(None, argv, self.root)

    def test_relative_argument_is_not_resolved_against_anything(self):
        assert not cleanup.is_owned(None, ["python", "backend/app/main.py"], self.root)

    def test_symlinked_interpreter_is_judged_by_the_path_as_written(self):
        """A venv python is a symlink into /usr/bin; resolving it would push every
        venv process out of the checkout."""
        argv = [str(self.root / "backend/.venv/bin/python")]
        assert cleanup.is_owned(None, argv, self.root)


class TestFindOwnedProcesses:
    def test_process_with_cwd_inside_the_checkout_is_found(self, checkout, spawn):
        proc = spawn(checkout / "backend")

        assert proc.pid in cleanup.find_owned_processes([MARKER], checkout)

    def test_process_elsewhere_is_not_found(self, checkout, elsewhere, spawn):
        proc = spawn(elsewhere)

        assert proc.pid not in cleanup.find_owned_processes([MARKER], checkout)

    def test_process_elsewhere_with_a_path_inside_the_checkout_is_found(
        self, checkout, elsewhere, spawn
    ):
        proc = spawn(elsewhere, str(checkout / "backend/.venv/bin/uvicorn"))

        assert proc.pid in cleanup.find_owned_processes([MARKER], checkout)

    def test_only_matching_patterns_count(self, checkout, spawn):
        proc = spawn(checkout / "backend")

        assert proc.pid not in cleanup.find_owned_processes(["no-such-pattern-763"], checkout)

    def test_never_returns_itself_or_its_parent(self):
        """With the whole filesystem as 'checkout' and a pattern that matches the
        test run's own command line, the launcher must still not shoot itself."""
        pids = cleanup.find_owned_processes([re.escape(sys.executable)], pathlib.Path("/"))

        assert os.getpid() not in pids
        assert os.getppid() not in pids


class TestTerminateOwnedProcesses:
    def test_terminates_own_and_spares_foreign(self, checkout, elsewhere, spawn):
        mine = spawn(checkout / "backend")
        foreign = spawn(elsewhere)

        cleanup.terminate_owned_processes([MARKER], checkout, grace_seconds=0)

        assert mine.wait(timeout=5) == -signal.SIGTERM
        assert foreign.poll() is None

    def test_escalates_to_sigkill_when_sigterm_is_ignored(self, checkout):
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "print('ready', flush=True); time.sleep(60)",
                MARKER,
            ],
            cwd=checkout,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout.readline().strip() == "ready"  # handler installed

            cleanup.terminate_owned_processes([MARKER], checkout, grace_seconds=0.2)

            assert proc.wait(timeout=5) == -signal.SIGKILL
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()

    def test_without_proc_it_does_nothing_instead_of_guessing(
        self, checkout, spawn, monkeypatch, tmp_path
    ):
        """macOS has no /proc. Falling back to pkill -f would bring the bug back."""
        proc = spawn(checkout / "backend")
        monkeypatch.setattr(cleanup, "PROC", tmp_path / "no-proc-here")

        cleanup.terminate_owned_processes([MARKER], checkout, grace_seconds=0)

        assert proc.poll() is None


class TestReturnValue:
    def test_returns_how_many_processes_it_terminated(self, checkout, elsewhere, spawn):
        mine = [spawn(checkout / "backend"), spawn(checkout / "backend")]
        spawn(elsewhere)

        count = cleanup.terminate_owned_processes([MARKER], checkout, grace_seconds=0)

        assert count == 2
        for proc in mine:
            proc.wait(timeout=5)

    def test_returns_zero_when_nothing_is_ours(self, checkout, elsewhere, spawn):
        spawn(elsewhere)

        assert cleanup.terminate_owned_processes([MARKER], checkout, grace_seconds=0) == 0

    def test_returns_zero_without_proc(self, checkout, monkeypatch, tmp_path):
        monkeypatch.setattr(cleanup, "PROC", tmp_path / "no-proc-here")

        assert cleanup.terminate_owned_processes([MARKER], checkout, grace_seconds=0) == 0


@pytest.mark.parametrize("script", ["start_dev.py", "kill_dev.py", "start_prod.py", "kill_prod.py"])
def test_launcher_scripts_do_not_shell_out_to_pkill_or_pgrep(script):
    """All four launchers share dev_process_cleanup. A fresh `pkill -f` in one of
    them brings #763 back for that script."""
    source = (REPO_ROOT / script).read_text(encoding="utf-8")

    assert not re.search(r"\bp(kill|grep)\b", source), f"{script} matches by command line again"
    assert "dev_process_cleanup" in source


class TestCleanStaleState:
    """start_prod.py used to delete the primary-worker lock and /dev/shm/baluhost
    unconditionally. /dev/shm is NOT covered by PrivateTmp, so a launcher run from
    another checkout wiped the live production telemetry. Only orphaned state may
    go: a lock nobody holds, and a SHM dir nobody is writing to."""

    @pytest.fixture
    def state(self, tmp_path):
        lock = tmp_path / "primary.lock"
        shm = tmp_path / "shm"
        shm.mkdir()
        (shm / "telemetry.json").write_text("{}")
        return lock, shm

    @pytest.fixture
    def lock_holder(self):
        """A process holding flock on a file, like the primary worker."""
        procs: list[subprocess.Popen] = []

        def _hold(path):
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import fcntl, sys, time; f = open(sys.argv[1], 'a'); "
                    "fcntl.flock(f, fcntl.LOCK_EX); print('locked', flush=True); time.sleep(60)",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            procs.append(proc)
            assert proc.stdout.readline().strip() == "locked"
            return proc

        yield _hold
        for proc in procs:
            proc.kill()
            proc.wait()
            proc.stdout.close()

    def test_lock_held_by_a_live_process_is_kept(self, state, lock_holder):
        lock, shm = state
        lock_holder(lock)

        lock_removed, _ = cleanup.clean_stale_state(lock, shm, ["no-writer-763"])

        assert lock_removed is False
        assert lock.exists()

    def test_lock_nobody_holds_is_removed(self, state):
        lock, shm = state
        lock.write_text("12345")

        lock_removed, _ = cleanup.clean_stale_state(lock, shm, ["no-writer-763"])

        assert lock_removed is True
        assert not lock.exists()

    def test_missing_lock_is_not_an_error(self, state):
        lock, shm = state

        lock_removed, _ = cleanup.clean_stale_state(lock, shm, ["no-writer-763"])

        assert lock_removed is False

    def test_shm_with_a_live_writer_is_kept(self, state, checkout, spawn):
        lock, shm = state
        spawn(checkout / "backend")  # command line carries MARKER

        _, shm_removed = cleanup.clean_stale_state(lock, shm, [MARKER])

        assert shm_removed is False
        assert (shm / "telemetry.json").exists()

    def test_shm_nobody_writes_is_removed(self, state):
        lock, shm = state

        _, shm_removed = cleanup.clean_stale_state(lock, shm, ["no-writer-763"])

        assert shm_removed is True
        assert not shm.exists()

    def test_a_writer_of_ANOTHER_install_also_keeps_the_shm(self, state, elsewhere, spawn):
        """The SHM dir is per host, not per checkout - whoever writes it, owns it."""
        lock, shm = state
        spawn(elsewhere)

        _, shm_removed = cleanup.clean_stale_state(lock, shm, [MARKER])

        assert shm_removed is False
