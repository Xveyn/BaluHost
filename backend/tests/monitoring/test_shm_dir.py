"""Where the SHM files live (#779).

`/dev/shm` is per host, not per install: a dev instance next to production
used to share `/dev/shm/baluhost` with it — the dev monitoring worker wiped
the live files on start and then wrote mock data that production read back,
including the disk temperatures the fan control acts on.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.services.monitoring import shm

PROD_DIR = Path("/dev/shm/baluhost")
DEV_DIR = Path("/dev/shm/baluhost-dev")
BACKEND_DIR = Path(__file__).resolve().parents[2]


class TestResolveShmDir:
    def test_production_keeps_its_directory(self):
        assert shm.resolve_shm_dir({}, dev_mode=False, platform="linux") == PROD_DIR

    def test_dev_mode_gets_a_directory_of_its_own(self):
        resolved = shm.resolve_shm_dir({}, dev_mode=True, platform="linux")

        assert resolved == DEV_DIR
        assert resolved != PROD_DIR

    @pytest.mark.parametrize("dev_mode", [True, False])
    def test_explicit_override_wins_in_either_mode(self, dev_mode):
        env = {shm.SHM_DIR_ENV: "/dev/shm/baluhost-checkout-b"}

        resolved = shm.resolve_shm_dir(env, dev_mode=dev_mode, platform="linux")

        assert resolved == Path("/dev/shm/baluhost-checkout-b")

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_override_falls_back_to_the_mode_default(self, blank):
        env = {shm.SHM_DIR_ENV: blank}

        assert shm.resolve_shm_dir(env, dev_mode=True, platform="linux") == DEV_DIR
        assert shm.resolve_shm_dir(env, dev_mode=False, platform="linux") == PROD_DIR

    def test_relative_override_is_rejected(self):
        with pytest.raises(ValueError, match=shm.SHM_DIR_ENV):
            shm.resolve_shm_dir(
                {shm.SHM_DIR_ENV: "baluhost-dev"}, dev_mode=True, platform="linux",
            )

    @pytest.mark.parametrize("foreign", ["/tmp", "/dev/shm", "/home/someone", "/"])
    def test_override_must_name_a_baluhost_directory(self, foreign):
        """`cleanup_shm()` deletes every file in the directory — it must never
        be pointed at a directory BaluHost does not own."""
        with pytest.raises(ValueError, match="baluhost"):
            shm.resolve_shm_dir(
                {shm.SHM_DIR_ENV: foreign}, dev_mode=True, platform="linux",
            )

    @pytest.mark.parametrize(
        "elsewhere",
        [
            "/opt/baluhost",  # the install: cleanup would take .env.production
            "/etc/baluhost",
            "/var/lib/baluhost",
            "/dev/shm/nested/baluhost-dev",
            "/home/someone/baluhost-shm",
        ],
    )
    def test_override_must_sit_directly_in_shm_or_the_temp_dir(self, elsewhere):
        """A fitting name is not enough: the install directory is called
        `baluhost` too."""
        with pytest.raises(ValueError, match=shm.SHM_DIR_ENV):
            shm.resolve_shm_dir(
                {shm.SHM_DIR_ENV: elsewhere}, dev_mode=True, platform="linux",
            )

    def test_override_in_the_temp_dir_is_accepted(self):
        target = Path(tempfile.gettempdir()) / "baluhost_test_shm_example"

        resolved = shm.resolve_shm_dir(
            {shm.SHM_DIR_ENV: str(target)}, dev_mode=True, platform="linux",
        )

        assert resolved == target

    def test_override_must_not_be_a_symlink(self, tmp_path):
        """`cleanup_shm()` iterates the directory and would follow the link."""
        victim = tmp_path / "somebody_elses_files"
        victim.mkdir()
        link = Path(tempfile.gettempdir()) / f"baluhost-link-{os.getpid()}-{tmp_path.name}"
        link.symlink_to(victim, target_is_directory=True)
        try:
            with pytest.raises(ValueError, match="symlink"):
                shm.resolve_shm_dir(
                    {shm.SHM_DIR_ENV: str(link)}, dev_mode=True, platform="linux",
                )
        finally:
            link.unlink()

    def test_dev_mode_refuses_the_production_directory(self):
        """The override must not be a way to quietly undo the separation."""
        with pytest.raises(ValueError, match="production"):
            shm.resolve_shm_dir(
                {shm.SHM_DIR_ENV: str(PROD_DIR)}, dev_mode=True, platform="linux",
            )

    def test_production_may_name_its_own_directory(self):
        resolved = shm.resolve_shm_dir(
            {shm.SHM_DIR_ENV: str(PROD_DIR)}, dev_mode=False, platform="linux",
        )

        assert resolved == PROD_DIR

    @pytest.mark.parametrize("dev_mode", [True, False])
    def test_windows_default_is_unchanged(self, dev_mode):
        resolved = shm.resolve_shm_dir({}, dev_mode=dev_mode, platform="win32")

        assert resolved == Path(tempfile.gettempdir()) / "baluhost-shm"


class TestSuiteIsolation:
    """The suite itself runs next to production on the dev box."""

    def test_the_suite_uses_a_directory_of_its_own(self):
        """Not "neither of the two defaults" but "one conftest made itself":
        a `BALUHOST_SHM_DIR` exported in the calling shell — the documented
        way to run a second dev checkout — would otherwise point the suite at
        the live directory of that instance."""
        assert shm.SHM_DIR == Path(os.environ[shm.SHM_DIR_ENV])
        assert shm.SHM_DIR.parent == Path(tempfile.gettempdir())
        assert shm.SHM_DIR.name.startswith("baluhost_test_shm_")

    def test_write_and_cleanup_stay_inside_the_suite_directory(self):
        shm.write_shm("probe_779.json", {"ok": True})
        try:
            assert (shm.SHM_DIR / "probe_779.json").is_file()
            assert shm.read_shm("probe_779.json") == {"ok": True}
        finally:
            (shm.SHM_DIR / "probe_779.json").unlink(missing_ok=True)


@pytest.mark.skipif(sys.platform == "win32", reason="/dev/shm is Linux-only")
class TestModuleWiring:
    """The module constant must come from the real mode of the process."""

    def _shm_dir_of_a_fresh_process(self, extra_env: dict[str, str]) -> str:
        env = {k: v for k, v in os.environ.items() if k != shm.SHM_DIR_ENV}
        env.update(extra_env)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.services.monitoring import shm; print('SHM_DIR=' + str(shm.SHM_DIR))",
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        lines = [ln for ln in result.stdout.splitlines() if ln.startswith("SHM_DIR=")]
        assert lines, result.stdout[-2000:]
        return lines[-1].removeprefix("SHM_DIR=")

    def test_a_dev_process_without_override_uses_the_dev_directory(self):
        """Covers a hand-started `uvicorn`/worker too, not just start_dev.py."""
        assert self._shm_dir_of_a_fresh_process({"NAS_MODE": "dev"}) == str(DEV_DIR)

    def test_a_dev_process_honours_the_override(self):
        resolved = self._shm_dir_of_a_fresh_process(
            {"NAS_MODE": "dev", shm.SHM_DIR_ENV: "/dev/shm/baluhost-checkout-b"},
        )

        assert resolved == "/dev/shm/baluhost-checkout-b"
