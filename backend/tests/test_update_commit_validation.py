"""Commit-identifier validation before git checkout (audit #6)."""
import pytest

from app.services.update.prod_backend import ProdUpdateBackend


@pytest.mark.asyncio
async def test_apply_updates_rejects_option_like_commit(tmp_path, monkeypatch):
    backend = ProdUpdateBackend(repo_path=tmp_path)
    called = []
    monkeypatch.setattr(backend, "_run_git", lambda *a, **k: called.append(a) or (True, "", ""))
    ok, err = await backend.apply_updates("--force")
    assert ok is False
    assert err is not None and "commit" in err.lower()
    assert called == []  # git was never invoked


@pytest.mark.asyncio
async def test_apply_updates_rejects_metachar_commit(tmp_path, monkeypatch):
    backend = ProdUpdateBackend(repo_path=tmp_path)
    monkeypatch.setattr(backend, "_run_git", lambda *a, **k: (True, "", ""))
    ok, err = await backend.apply_updates("abc123; rm -rf /")
    assert ok is False


@pytest.mark.asyncio
async def test_apply_updates_accepts_valid_sha(tmp_path, monkeypatch):
    backend = ProdUpdateBackend(repo_path=tmp_path)
    # stash, checkout, rev-parse all "succeed"; rev-parse returns detached HEAD
    def fake_git(*args, **kwargs):
        if args[:1] == ("rev-parse",):
            return True, "HEAD", ""
        return True, "", ""
    monkeypatch.setattr(backend, "_run_git", fake_git)
    ok, err = await backend.apply_updates("a" * 40)
    assert ok is True
    assert err is None


def test_launch_update_script_rejects_bad_commit(tmp_path):
    backend = ProdUpdateBackend(repo_path=tmp_path)
    ok, err = backend.launch_update_script(
        update_id=1, from_commit="abc1234", to_commit="--exec=evil",
        from_version="1.0.0", to_version="1.0.1",
    )
    assert ok is False
    assert err is not None and "commit" in err.lower()
