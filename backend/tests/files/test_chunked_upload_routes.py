"""Chunked upload routes: any worker can serve any step (#834 follow-up).

Production runs several API processes and a chunked upload is one request per
chunk. The session used to live in the memory of the worker that handled
``init``; a chunk or the ``complete`` on any other worker answered 404
"Upload session not found". Sessions are on disk now.

"Another worker" here is a fresh set of per-process singletons on the same
upload directory — exactly what a second Uvicorn worker has.

The session file is input, not a credential: these tests also plant session
files by hand and check that they authorize nothing.
"""
import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.api.routes.chunked_upload as chunked_routes
import app.services.files.chunked_upload as cu
from app.services import upload_activity
from app.services import upload_progress as upload_progress_service
from app.services.files.operations import ROOT_DIR
from app.services.upload_progress import get_upload_progress_manager

INIT = "/api/files/upload/chunked/init"


def _url(upload_id: str, step: str = "") -> str:
    return f"/api/files/upload/chunked/{upload_id}" + (f"/{step}" if step else "")


def _switch_worker() -> None:
    """Continue on a worker that has seen nothing of what happened so far."""
    cu._manager = None
    upload_progress_service._manager = None


def _not_uploading(upload_id: str) -> bool:
    """Whether this worker's progress session ended (dev mode removes an
    ended session at once, production keeps it for a minute)."""
    progress = get_upload_progress_manager().get_progress(upload_id)
    return progress is None or progress.status != "uploading"


@pytest.fixture(autouse=True)
def _patch_session_local(db_session, monkeypatch):
    """Metadata, audit and VCL open their own session (`db=None`); point it
    at the test database, as `test_files_api_integration.py` does."""
    test_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    monkeypatch.setattr("app.core.database.SessionLocal", test_session_local)
    monkeypatch.setattr("app.services.files.metadata_db.SessionLocal", test_session_local)
    monkeypatch.setattr("app.services.files.ownership.SessionLocal", test_session_local)


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    directory = tmp_path / "uploads"
    monkeypatch.setattr(cu, "TMP_UPLOAD_DIR", directory)
    _switch_worker()
    yield directory
    _switch_worker()


@pytest.fixture
def target(admin_headers):
    """A destination folder inside the storage root, removed afterwards."""
    name = "chunked-route-test"
    path = ROOT_DIR / name
    shutil.rmtree(path, ignore_errors=True)
    yield name
    shutil.rmtree(path, ignore_errors=True)


def _init(client, headers, target_path, filename="big.bin", total_size=13):
    r = client.post(
        INIT,
        json={"filename": filename, "total_size": total_size, "target_path": target_path},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["upload_id"]


def _chunk(client, headers, upload_id, index, data):
    return client.post(
        _url(upload_id, "chunk"), params={"chunk_index": index}, content=data,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )


def _leftovers(upload_dir):
    return sorted(p.name for p in upload_dir.iterdir()) if upload_dir.exists() else []


# ─── Any worker, any step ────────────────────────────────────────────


def test_every_step_on_a_different_worker(client: TestClient, admin_headers, target, upload_dir):
    upload_id = _init(client, admin_headers, target)

    _switch_worker()
    first = _chunk(client, admin_headers, upload_id, 0, b"Hello, ")
    _switch_worker()
    second = _chunk(client, admin_headers, upload_id, 1, b"World!")
    _switch_worker()
    done = client.post(_url(upload_id, "complete"), headers=admin_headers)

    assert first.status_code == 200 and first.json() == {"received_bytes": 7}
    assert second.status_code == 200 and second.json() == {"received_bytes": 13}
    assert done.status_code == 200, done.text
    assert done.json() == {"path": f"{target}/big.bin", "size": 13}
    assert (ROOT_DIR / target / "big.bin").read_bytes() == b"Hello, World!"
    assert _leftovers(upload_dir) == []


def test_checksum_in_metadata_is_right_after_worker_switches(
    client: TestClient, admin_headers, target, db_session,
):
    from app.models.file_metadata import FileMetadata

    upload_id = _init(client, admin_headers, target)
    _chunk(client, admin_headers, upload_id, 0, b"Hello, ")
    _switch_worker()
    _chunk(client, admin_headers, upload_id, 1, b"World!")
    _switch_worker()
    assert client.post(_url(upload_id, "complete"), headers=admin_headers).status_code == 200

    db_session.expire_all()
    meta = db_session.query(FileMetadata).filter_by(path=f"{target}/big.bin").one()
    assert meta.checksum == hashlib.sha256(b"Hello, World!").hexdigest()
    assert meta.size_bytes == 13


def test_abort_on_a_different_worker(client: TestClient, admin_headers, target, upload_dir):
    upload_id = _init(client, admin_headers, target)
    _chunk(client, admin_headers, upload_id, 0, b"Hello, ")

    _switch_worker()
    aborted = client.delete(_url(upload_id), headers=admin_headers)
    _switch_worker()
    late = _chunk(client, admin_headers, upload_id, 1, b"World!")

    assert aborted.status_code == 200
    assert late.status_code == 404
    assert _leftovers(upload_dir) == []
    assert not (ROOT_DIR / target / "big.bin").exists()


@pytest.mark.parametrize("upload_id", ["not-a-uuid", "00000000-0000-4000-8000-000000000000"])
def test_unknown_session_is_a_404_on_every_step(client: TestClient, admin_headers, upload_id):
    assert _chunk(client, admin_headers, upload_id, 0, b"x").status_code == 404
    assert client.post(_url(upload_id, "complete"), headers=admin_headers).status_code == 404
    assert client.delete(_url(upload_id), headers=admin_headers).status_code == 200


def test_out_of_order_chunk_is_a_400(client: TestClient, admin_headers, target):
    upload_id = _init(client, admin_headers, target)
    _switch_worker()

    r = _chunk(client, admin_headers, upload_id, 2, b"x")

    assert r.status_code == 400
    assert "Expected chunk 0, got 2" in r.json()["detail"]


# ─── Whose session ───────────────────────────────────────────────────


def test_another_users_session_is_refused_on_every_step(
    client: TestClient, admin_headers, user_headers, target, upload_dir,
):
    upload_id = _init(client, admin_headers, target)
    _chunk(client, admin_headers, upload_id, 0, b"Hello, ")
    _switch_worker()

    assert _chunk(client, user_headers, upload_id, 1, b"World!").status_code == 403
    assert client.post(_url(upload_id, "complete"), headers=user_headers).status_code == 403
    assert client.delete(_url(upload_id), headers=user_headers).status_code == 403

    # ... and it left the owner's upload alone.
    assert _chunk(client, admin_headers, upload_id, 1, b"World!").status_code == 200
    assert client.post(_url(upload_id, "complete"), headers=admin_headers).status_code == 200
    assert (ROOT_DIR / target / "big.bin").read_bytes() == b"Hello, World!"


# ─── A planted session file authorizes nothing ───────────────────────

_PLANTED_ID = "55555555-5555-4555-8555-555555555555"


def _plant(upload_dir, *, user_id, target_path, filename="planted.txt", data=b"planted"):
    """What someone with write access to the upload directory could put there."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{_PLANTED_ID}.json").write_text(json.dumps({
        "upload_id": _PLANTED_ID, "target_path": target_path, "filename": filename,
        "total_size": len(data), "chunk_size": 1024, "received_bytes": len(data),
        "next_chunk_index": 1, "user_id": user_id, "username": "whoever",
        "created_at": 1_800_000_000.0, "last_activity": 1_800_000_000.0,
    }))
    (upload_dir / f"{_PLANTED_ID}.lock").write_text("")
    (upload_dir / _PLANTED_ID).write_bytes(data)


def test_planted_session_cannot_write_into_another_users_folder(
    client: TestClient, user_headers, regular_user, another_user, upload_dir,
):
    """The session names the attacker as owner and someone else's home as the
    destination. `complete` asks again what `init` would have asked."""
    victim_dir = ROOT_DIR / another_user.username
    victim_dir.mkdir(parents=True, exist_ok=True)
    _plant(upload_dir, user_id=regular_user.id, target_path=another_user.username)

    r = client.post(_url(_PLANTED_ID, "complete"), headers=user_headers)

    assert r.status_code == 403
    assert not (victim_dir / "planted.txt").exists()
    assert _leftovers(upload_dir) == []


@pytest.mark.parametrize("filename", ["../escaped.txt", "sub/escaped.txt", "..", ""])
def test_planted_session_cannot_choose_a_path_as_file_name(
    client: TestClient, admin_headers, admin_user, target, upload_dir, filename,
):
    _plant(upload_dir, user_id=admin_user.id, target_path=target, filename=filename)

    r = client.post(_url(_PLANTED_ID, "complete"), headers=admin_headers)

    assert r.status_code == 400
    assert not (ROOT_DIR / "escaped.txt").exists()
    assert not (ROOT_DIR / target / "sub").exists()
    assert _leftovers(upload_dir) == []


def test_planted_session_for_an_allowed_target_is_just_an_upload(
    client: TestClient, admin_headers, admin_user, target, upload_dir,
):
    """Control: the same planted session is fine where the user may write —
    it grants nothing the user could not have done with `init`."""
    _plant(upload_dir, user_id=admin_user.id, target_path=target)

    r = client.post(_url(_PLANTED_ID, "complete"), headers=admin_headers)

    assert r.status_code == 200, r.text
    assert (ROOT_DIR / target / "planted.txt").read_bytes() == b"planted"


def test_permission_lost_after_init_stops_the_upload(
    client: TestClient, user_headers, regular_user, upload_dir, monkeypatch,
):
    """`complete` goes by the permissions of now, not of `init`."""
    home = ROOT_DIR / regular_user.username
    home.mkdir(parents=True, exist_ok=True)
    upload_id = _init(client, user_headers, regular_user.username, filename="late.bin", total_size=4)
    _chunk(client, user_headers, upload_id, 0, b"data")

    def _denied(target_path, user, db):
        from app.services.permissions import PermissionDeniedError
        raise PermissionDeniedError("Operation not permitted")

    monkeypatch.setattr(chunked_routes, "_validate_target", _denied)
    r = client.post(_url(upload_id, "complete"), headers=user_headers)

    assert r.status_code == 403
    assert not (home / "late.bin").exists()
    assert _leftovers(upload_dir) == []


# ─── The upload is known to idle detection and ends for it ───────────


def test_upload_counts_as_running_from_init_to_complete(client: TestClient, admin_headers, target):
    upload_id = _init(client, admin_headers, target)
    after_init = upload_activity.active_uploads()

    _switch_worker()
    _chunk(client, admin_headers, upload_id, 0, b"Hello, ")
    _chunk(client, admin_headers, upload_id, 1, b"World!")
    during = upload_activity.active_uploads()

    _switch_worker()
    assert client.post(_url(upload_id, "complete"), headers=admin_headers).status_code == 200

    assert (after_init, during) == (1, 1)
    assert upload_activity.active_uploads() == 0


def test_chunk_on_a_worker_without_the_progress_session_still_reports(
    client: TestClient, admin_headers, target,
):
    upload_id = _init(client, admin_headers, target)
    _switch_worker()
    upload_activity._tracker.reset()  # this worker has reported nothing yet

    _chunk(client, admin_headers, upload_id, 0, b"Hello, ")

    assert get_upload_progress_manager().get_progress(upload_id) is None
    assert upload_activity.active_uploads() == 1


def test_upload_counts_while_a_chunk_is_still_coming_in(
    client: TestClient, admin_headers, target, monkeypatch,
):
    """A 32 MB chunk on a slow line takes minutes. The worker receiving it
    reports the upload before the chunk is complete, not only after."""
    upload_id = _init(client, admin_headers, target)
    _switch_worker()
    upload_activity._tracker.reset()  # this worker has reported nothing yet
    seen_during_write = []
    manager = cu.get_chunked_upload_manager()
    real_write = manager.write_chunk_stream

    async def _watched(*args, **kwargs):
        seen_during_write.append(upload_activity.active_uploads())
        return await real_write(*args, **kwargs)

    monkeypatch.setattr(manager, "write_chunk_stream", _watched)

    assert _chunk(client, admin_headers, upload_id, 0, b"Hello, ").status_code == 200
    assert seen_during_write == [1]


def test_overflow_on_a_worker_without_the_progress_session_ends_the_upload(
    client: TestClient, admin_headers, target,
):
    """Nothing but the route itself can report the end here: this worker
    holds no progress session that would."""
    upload_id = _init(client, admin_headers, target, total_size=4)
    _switch_worker()

    r = _chunk(client, admin_headers, upload_id, 0, b"too much")

    assert r.status_code == 400
    assert get_upload_progress_manager().get_progress(upload_id) is None
    assert upload_activity.active_uploads() == 0


def test_user_can_abort_their_own_upload(
    client: TestClient, user_headers, regular_user, upload_dir,
):
    """The abort route sat behind the catch-all file-delete route: anyone but
    an admin got its 403 "Access denied" and the session stayed."""
    (ROOT_DIR / regular_user.username).mkdir(parents=True, exist_ok=True)
    upload_id = _init(client, user_headers, regular_user.username, filename="mine.bin")
    _chunk(client, user_headers, upload_id, 0, b"Hello, ")

    r = client.delete(_url(upload_id), headers=user_headers)

    assert r.status_code == 200
    assert r.json() == {"message": "Upload aborted"}
    assert _leftovers(upload_dir) == []
    assert upload_activity.active_uploads() == 0


def test_abort_ends_the_upload_for_idle_detection(client: TestClient, admin_headers, target):
    upload_id = _init(client, admin_headers, target)
    _chunk(client, admin_headers, upload_id, 0, b"Hello, ")
    _switch_worker()

    client.delete(_url(upload_id), headers=admin_headers)

    assert upload_activity.active_uploads() == 0


def test_overflowing_chunk_ends_the_upload(client: TestClient, admin_headers, target, upload_dir):
    upload_id = _init(client, admin_headers, target, total_size=4)

    r = _chunk(client, admin_headers, upload_id, 0, b"too much")

    assert r.status_code == 400
    assert "exceeds declared total_size" in r.json()["detail"]
    assert upload_activity.active_uploads() == 0
    assert _not_uploading(upload_id)
    assert _leftovers(upload_dir) == []


def test_failed_complete_leaves_nothing_running_and_no_temp_file(
    client: TestClient, admin_headers, target, upload_dir, monkeypatch,
):
    """The session is closed before the move. If the move fails, nothing may
    stay behind that still looks like an upload."""
    upload_id = _init(client, admin_headers, target)
    _chunk(client, admin_headers, upload_id, 0, b"Hello, World!")

    def _broken_move(src, dst):
        raise OSError("disk says no")

    monkeypatch.setattr(chunked_routes.shutil, "move", _broken_move)
    try:
        r = client.post(_url(upload_id, "complete"), headers=admin_headers)
        assert r.status_code == 500
    except OSError:
        pass  # TestClient re-raises server errors

    assert upload_activity.active_uploads() == 0
    assert _not_uploading(upload_id)
    assert _leftovers(upload_dir) == []
    assert not (ROOT_DIR / target / "big.bin").exists()


def test_abort_of_an_unknown_id_does_not_touch_someone_elses_progress(
    client: TestClient, admin_headers, user_headers,
):
    """A progress session of a plain (non-chunked) upload has an id too. The
    DELETE used to fail whatever progress session carried the id it was given."""
    foreign = get_upload_progress_manager().create_upload_session("theirs.bin", 10)

    r = client.delete(_url(foreign), headers=user_headers)

    assert r.status_code == 200
    assert get_upload_progress_manager().get_progress(foreign).status == "uploading"
    assert upload_activity.active_uploads() == 1


# ─── Plain uploads end their progress sessions too ───────────────────


@pytest.mark.parametrize("error", ["permission", "unexpected"])
def test_plain_upload_that_fails_leaves_no_session_uploading(
    client: TestClient, admin_headers, monkeypatch, error,
):
    """`save_uploads` raising before its own first `fail_upload` used to leave
    the session "uploading" until the worker restarted."""
    from io import BytesIO

    import app.api.routes.files as files_routes
    from app.services.permissions import PermissionDeniedError

    async def _boom(*_args, **_kwargs):
        if error == "permission":
            raise PermissionDeniedError("Operation not permitted")
        raise RuntimeError("unexpected")

    monkeypatch.setattr(files_routes.file_service, "save_uploads", _boom)
    manager = get_upload_progress_manager()
    created = []
    real_create = manager.create_upload_session

    def _create(*args, **kwargs):
        created.append(real_create(*args, **kwargs))
        return created[-1]

    manager.create_upload_session = _create
    try:
        r = client.post(
            "/api/files/upload",
            files={"files": ("a.txt", BytesIO(b"content"), "text/plain")},
            data={"path": ""},
            headers=admin_headers,
        )
        assert r.status_code in (403, 500)
    except RuntimeError:
        pass  # TestClient re-raises server errors

    assert created, "the route created no progress session — the test proves nothing"
    assert all(_not_uploading(upload_id) for upload_id in created)
    assert upload_activity.active_uploads() == 0


def test_plain_upload_that_succeeds_is_not_marked_failed(client: TestClient, admin_headers, target):
    from io import BytesIO

    (ROOT_DIR / target).mkdir(parents=True, exist_ok=True)
    seen = []
    manager = get_upload_progress_manager()
    real_fail = manager.fail_upload

    async def _watch(upload_id, error):
        seen.append(error)
        await real_fail(upload_id, error)

    manager.fail_upload = _watch
    r = client.post(
        "/api/files/upload",
        files={"files": ("ok.txt", BytesIO(b"content"), "text/plain")},
        data={"path": target},
        headers=admin_headers,
    )

    assert r.status_code == 200, r.text
    assert seen == []
    assert upload_activity.active_uploads() == 0
