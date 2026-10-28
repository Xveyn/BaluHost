"""Pfade *innerhalb* eines Datentraegers/einer ISO duerfen 7z nie als Schalter erreichen.

Der Pfad-Jail schuetzt das Ziel; die Mitgliedspfade (`paths`) gingen bisher
unveraendert als Argument an `7z`. `-o<dir>` hinter dem gejailten `-o` haette das
Ziel ueberschrieben, `@datei` liest eine Dateiliste.
"""
import asyncio

import pytest

from app.core.config import settings
from app.plugins.installed.optical_drive.service import OpticalDriveService

EVIL = ["-o/etc", "-ao", "@/etc/passwd", "../up.txt", "a/../../up.txt", "a\x00b", ""]


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    (root / "alice").mkdir(parents=True)
    (root / "alice" / "d.iso").write_bytes(b"x")
    monkeypatch.setattr(settings, "nas_storage_path", str(root))
    monkeypatch.setattr(settings, "nas_backup_path", str(tmp_path / "backups"))
    return root


def _service(dev: bool) -> OpticalDriveService:
    svc = OpticalDriveService()
    svc._is_dev_mode = dev
    return svc


class _FakeProc:
    returncode = 0

    class _Out:
        async def readline(self):
            return b""

    stdout = _Out()

    async def wait(self):
        return 0

    async def communicate(self):
        return b"", b""


@pytest.fixture
def exec_calls(monkeypatch):
    calls = []

    async def fake_exec(*cmd, **kwargs):
        calls.append(list(cmd))
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


@pytest.mark.parametrize("evil", EVIL)
class TestEvilMemberPathsAreRefused:
    async def test_extract_from_iso(self, storage, evil):
        svc = _service(dev=True)
        with pytest.raises(ValueError):
            await svc.extract_from_iso(
                str(storage / "alice" / "d.iso"), [evil], str(storage / "alice" / "out")
            )
        assert not (storage / "alice" / "out").exists()

    async def test_extract_files(self, storage, evil):
        svc = _service(dev=True)
        with pytest.raises(ValueError):
            await svc.extract_files("/dev/sr1", [evil], str(storage / "alice" / "out"))
        assert not (storage / "alice" / "out").exists()


class TestSevenZipGetsADoubleDash:
    async def test_extract_from_iso(self, storage, exec_calls):
        svc = _service(dev=False)
        out = storage / "alice" / "out"
        job = await svc.extract_from_iso(
            str(storage / "alice" / "d.iso"), ["/docs/-weird.txt", "/b.txt"], str(out)
        )
        await svc._job_tasks[job.id]
        (cmd,) = exec_calls
        assert cmd[0] == "7z"
        assert cmd[cmd.index("--") + 1 :] == ["docs/-weird.txt", "b.txt"]
        assert f"-o{out}" in cmd[: cmd.index("--")]

    async def test_preview_iso_file(self, storage, monkeypatch):
        svc = _service(dev=False)
        seen = []

        async def fake_run(cmd, timeout=30):
            seen.append(cmd)
            return 0, "hello", ""

        monkeypatch.setattr(svc, "_run_command", fake_run)
        await svc.preview_iso_file(str(storage / "alice" / "d.iso"), "/docs/x.txt")
        (cmd,) = seen
        assert cmd[cmd.index("--") + 1 :] == ["docs/x.txt"]

    @pytest.mark.parametrize("evil", ["/-o/x.txt", "/@list.txt", "/a/../../x.txt"])
    async def test_preview_refuses_evil_member(self, storage, monkeypatch, evil):
        svc = _service(dev=False)
        monkeypatch.setattr(svc, "_run_command", lambda *a, **k: pytest.fail("ran 7z"))
        with pytest.raises(ValueError):
            await svc.preview_iso_file(str(storage / "alice" / "d.iso"), evil)


class TestFineMemberPathsStillWork:
    async def test_dev_mode_extract_from_iso(self, storage):
        svc = _service(dev=True)
        job = await svc.extract_from_iso(
            str(storage / "alice" / "d.iso"), ["/docs/a.txt"], str(storage / "alice" / "out")
        )
        await svc._job_tasks[job.id]
        assert (storage / "alice" / "out" / "a.txt").exists()
