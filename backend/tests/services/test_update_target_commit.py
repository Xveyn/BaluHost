"""The in-app update must reach the runner with a real target commit (#216).

Since the check moved to GitHub Releases (#173) the target VersionInfo carries
``commit=""``. ``start_update()`` passed that straight on, so every in-app
update since 2026-06-06 died: first inside ``run-update.sh`` ("exited without
reporting status"), later at ``_is_valid_commit()`` ("Invalid commit
identifier"). The release tag has to be resolved to a SHA before launch.

Also covers the stale-run gap in ``finalize_pending_updates()``: a status file
stuck on a running state was never finalized, even with the runner long gone.
"""
import json
from datetime import datetime, timezone

import pytest

from app.models.update_history import UpdateHistory, UpdateStatus
from app.schemas.update import UpdateCheckResponse, VersionInfo
from app.services.update.api import finalize_pending_updates
from app.services.update.prod_backend import ProdUpdateBackend
from app.services.update.service import UpdateService

SHA = "a" * 40
CURRENT_SHA = "b" * 40


def _git_fake(tags: dict[str, str], fetched_tags: dict[str, str], calls: list):
    """Fake ``_run_git``: ``tags`` exist locally, ``fetched_tags`` only after a fetch."""
    state = {"fetched": False}

    def run(*args):
        calls.append(args)
        if args[:1] == ("fetch",):
            state["fetched"] = True
            return True, "", ""
        if args[:1] == ("rev-parse",):
            ref = args[-1]
            known = dict(tags)
            if state["fetched"]:
                known.update(fetched_tags)
            for tag, sha in known.items():
                if ref == f"refs/tags/{tag}^{{commit}}":
                    return True, sha, ""
            return False, "", "unknown revision"
        return True, "", ""

    return run


class TestResolveTagCommit:
    def test_resolves_local_tag_without_fetching(self, tmp_path, monkeypatch):
        backend = ProdUpdateBackend(repo_path=tmp_path)
        calls: list = []
        monkeypatch.setattr(backend, "_run_git", _git_fake({"v1.38.0": SHA}, {}, calls))

        assert backend.resolve_tag_commit("v1.38.0") == SHA
        assert not any(c[:1] == ("fetch",) for c in calls)

    def test_fetches_tags_when_tag_is_not_local_yet(self, tmp_path, monkeypatch):
        backend = ProdUpdateBackend(repo_path=tmp_path)
        calls: list = []
        monkeypatch.setattr(backend, "_run_git", _git_fake({}, {"v1.38.0": SHA}, calls))

        assert backend.resolve_tag_commit("v1.38.0") == SHA
        assert any(c[:1] == ("fetch",) for c in calls)

    def test_returns_none_when_tag_does_not_exist(self, tmp_path, monkeypatch):
        backend = ProdUpdateBackend(repo_path=tmp_path)
        monkeypatch.setattr(backend, "_run_git", _git_fake({}, {}, []))

        assert backend.resolve_tag_commit("v9.9.9") is None

    def test_rejects_option_like_tag_without_calling_git(self, tmp_path, monkeypatch):
        # The tag comes from the GitHub API and ends up as a git argument.
        backend = ProdUpdateBackend(repo_path=tmp_path)
        calls: list = []
        monkeypatch.setattr(backend, "_run_git", _git_fake({}, {}, calls))

        assert backend.resolve_tag_commit("--upload-pack=touch /tmp/x") is None
        assert calls == []

    def test_rejects_non_sha_output(self, tmp_path, monkeypatch):
        backend = ProdUpdateBackend(repo_path=tmp_path)
        monkeypatch.setattr(backend, "_run_git", lambda *a: (True, "not-a-sha", ""))

        assert backend.resolve_tag_commit("v1.38.0") is None


def _prod_service(db_session, tmp_path, monkeypatch, resolved: str | None):
    backend = ProdUpdateBackend(repo_path=tmp_path)
    service = UpdateService(db_session, backend=backend)

    current = VersionInfo(version="1.37.1-pre.43", commit=CURRENT_SHA, commit_short="bbbbbbb")
    # Exactly what the GitHub-based check produces: a tag, but no commit.
    latest = VersionInfo(version="1.38.0", commit="", commit_short="", tag="v1.38.0")

    async def _current():
        return current

    async def _check():
        return UpdateCheckResponse(
            update_available=True, current_version=current, latest_version=latest,
            changelog=[], channel="stable", blockers=[], can_update=True,
        )

    async def _no_blockers():
        return []

    monkeypatch.setattr(backend, "get_current_version", _current)
    monkeypatch.setattr(service, "check_for_updates", _check)
    monkeypatch.setattr(service, "_check_blockers", _no_blockers)
    monkeypatch.setattr(backend, "resolve_tag_commit", lambda tag: resolved)

    launched: list[dict] = []

    def _launch(**kwargs):
        launched.append(kwargs)
        return True, None

    monkeypatch.setattr(backend, "launch_update_script", _launch)
    return service, launched


class TestStartUpdateTargetCommit:
    @pytest.mark.asyncio
    async def test_launches_runner_with_resolved_commit(self, db_session, tmp_path, monkeypatch):
        service, launched = _prod_service(db_session, tmp_path, monkeypatch, resolved=SHA)

        result = await service.start_update(user_id=1)

        assert result.success is True
        assert launched and launched[0]["to_commit"] == SHA
        row = db_session.query(UpdateHistory).one()
        assert row.to_commit == SHA

    @pytest.mark.asyncio
    async def test_unresolvable_tag_fails_before_recording_or_launching(
        self, db_session, tmp_path, monkeypatch
    ):
        service, launched = _prod_service(db_session, tmp_path, monkeypatch, resolved=None)

        result = await service.start_update(user_id=1)

        assert result.success is False
        assert "v1.38.0" in result.message
        assert launched == []
        assert db_session.query(UpdateHistory).count() == 0


def _stuck_update(db_session, status_dir, file_status: str = "installing") -> UpdateHistory:
    row = UpdateHistory(
        from_version="1.34.1-pre.7", to_version="1.35.0", channel="stable",
        from_commit=CURRENT_SHA, to_commit=SHA,
        status=UpdateStatus.INSTALLING.value,
    )
    db_session.add(row)
    db_session.commit()
    # SQLite hands DateTime(timezone=True) back naive; Postgres (prod) doesn't.
    # Keep it aware in the identity map so fail()'s duration math matches prod.
    row.started_at = datetime.now(timezone.utc)
    (status_dir / f"{row.id}.json").write_text(json.dumps({
        "update_id": row.id, "status": file_status, "progress_percent": 45,
        "current_step": "Running module 08: database-migrate...", "completed_at": None,
        "error_message": None, "rollback_commit": None,
    }), encoding="utf-8")
    return row


class TestFinalizeStaleRun:
    def test_running_status_with_dead_runner_is_marked_failed(
        self, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(ProdUpdateBackend, "_STATUS_DIR", tmp_path)
        monkeypatch.setattr(ProdUpdateBackend, "update_unit_running", staticmethod(lambda: False))
        row = _stuck_update(db_session, tmp_path)

        assert finalize_pending_updates(db_session) == 1

        db_session.refresh(row)
        assert row.status == UpdateStatus.FAILED.value
        assert "database-migrate" in (row.error_message or "")

    def test_running_status_with_live_runner_is_left_alone(
        self, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(ProdUpdateBackend, "_STATUS_DIR", tmp_path)
        monkeypatch.setattr(ProdUpdateBackend, "update_unit_running", staticmethod(lambda: True))
        row = _stuck_update(db_session, tmp_path)

        assert finalize_pending_updates(db_session) == 0

        db_session.refresh(row)
        assert row.status == UpdateStatus.INSTALLING.value

    def test_unknown_runner_state_is_left_alone(self, db_session, tmp_path, monkeypatch):
        # Can't ask systemd -> don't guess; failing a live update would be worse.
        monkeypatch.setattr(ProdUpdateBackend, "_STATUS_DIR", tmp_path)
        monkeypatch.setattr(ProdUpdateBackend, "update_unit_running", staticmethod(lambda: None))
        row = _stuck_update(db_session, tmp_path)

        assert finalize_pending_updates(db_session) == 0

        db_session.refresh(row)
        assert row.status == UpdateStatus.INSTALLING.value


class TestUpdateUnitRunning:
    @pytest.mark.parametrize("substate,expected", [
        ("running", True),
        ("start", True),
        ("exited", False),   # --remain-after-exit: script is done, unit still "active"
        ("failed", False),
        ("dead", False),     # also what systemd reports for a unit that no longer exists
    ])
    def test_maps_substate(self, monkeypatch, substate, expected):
        import subprocess

        class _Result:
            returncode = 0
            stdout = f"{substate}\n"
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
        assert ProdUpdateBackend.update_unit_running() is expected

    def test_returns_none_when_systemctl_is_unavailable(self, monkeypatch):
        import subprocess

        def _boom(*a, **k):
            raise FileNotFoundError("systemctl")

        monkeypatch.setattr(subprocess, "run", _boom)
        assert ProdUpdateBackend.update_unit_running() is None
