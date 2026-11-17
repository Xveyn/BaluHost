"""
Tests for chunked upload session manager (services/files/chunked_upload.py).

Covers:
- Session creation and retrieval
- Sequential chunk writing
- Wrong chunk order rejection
- Session completion
- Session abort and cleanup
- Stale session cleanup
- Sessions shared by every API process: a second manager on the same
  directory stands for another Uvicorn worker
- What a session file may and may not decide (it is not trusted)
"""

import asyncio
import hashlib
import json
import os
import threading

import pytest

import app.services.files.chunked_upload as cu
from app.services.files.chunked_upload import (
    SESSION_MAX_AGE,
    ChunkedUploadManager,
)


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    directory = tmp_path / "uploads"
    monkeypatch.setattr(cu, "TMP_UPLOAD_DIR", directory)
    return directory


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def manager(upload_dir, clock):
    """One Uvicorn worker's manager."""
    return ChunkedUploadManager(clock=clock)


@pytest.fixture
def other_worker(upload_dir, clock):
    """Another worker: its own memory, the same upload directory."""
    return ChunkedUploadManager(clock=clock)


async def _create(manager, **overrides):
    values = dict(
        target_path="uploads", filename="test.txt", total_size=1024,
        user_id=1, username="testuser",
    )
    values.update(overrides)
    return await manager.create_session(**values)


async def _stream(*fragments):
    for fragment in fragments:
        yield fragment


# ============================================================================
# Session Creation
# ============================================================================

class TestSessionCreation:
    """Test upload session creation."""

    @pytest.mark.asyncio
    async def test_create_session(self, manager):
        session = await _create(manager)

        assert session.upload_id is not None
        assert session.filename == "test.txt"
        assert session.total_size == 1024
        assert session.received_bytes == 0
        assert session.next_chunk_index == 0
        assert session.user_id == 1

    @pytest.mark.asyncio
    async def test_create_session_default_chunk_size(self, manager):
        session = await _create(manager)

        assert session.chunk_size == ChunkedUploadManager.DEFAULT_CHUNK_SIZE

    @pytest.mark.asyncio
    async def test_create_session_custom_chunk_size(self, manager):
        session = await _create(manager, chunk_size=5 * 1024 * 1024)

        assert session.chunk_size == 5 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_create_multiple_sessions(self, manager):
        s1 = await _create(manager, filename="file1.txt")
        s2 = await _create(manager, filename="file2.txt")

        assert s1.upload_id != s2.upload_id

    @pytest.mark.asyncio
    async def test_temp_file_lives_in_the_upload_directory(self, manager, upload_dir):
        session = await _create(manager)

        assert session.temp_file_path == upload_dir / session.upload_id


class TestSessionRetrieval:
    """Test session get operations."""

    @pytest.mark.asyncio
    async def test_get_existing_session(self, manager):
        session = await _create(manager)

        fetched = manager.get_session(session.upload_id)
        assert fetched is not None
        assert fetched.upload_id == session.upload_id
        assert fetched.username == "testuser"
        assert fetched.target_path == "uploads"

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, manager):
        assert manager.get_session("nonexistent-id") is None
        assert manager.get_session("00000000-0000-4000-8000-000000000000") is None


# ============================================================================
# Chunk Writing
# ============================================================================

class TestChunkWriting:
    """Test writing chunks to sessions."""

    @pytest.mark.asyncio
    async def test_write_first_chunk(self, manager):
        session = await _create(manager, total_size=100)

        data = b"Hello, World!"
        received = await manager.write_chunk(session.upload_id, 0, data)

        assert received == len(data)
        assert manager.get_session(session.upload_id).next_chunk_index == 1

    @pytest.mark.asyncio
    async def test_write_sequential_chunks(self, manager):
        session = await _create(manager, total_size=100)

        await manager.write_chunk(session.upload_id, 0, b"chunk0")
        await manager.write_chunk(session.upload_id, 1, b"chunk1")
        received = await manager.write_chunk(session.upload_id, 2, b"chunk2")

        assert received == 18  # 6 + 6 + 6
        stored = manager.get_session(session.upload_id)
        assert stored.next_chunk_index == 3
        assert stored.received_bytes == 18

    @pytest.mark.asyncio
    async def test_write_wrong_chunk_order_rejected(self, manager):
        session = await _create(manager, total_size=100)

        # Skip chunk 0, try to write chunk 1
        with pytest.raises(ValueError, match="Expected chunk 0, got 1"):
            await manager.write_chunk(session.upload_id, 1, b"data")

    @pytest.mark.asyncio
    async def test_repeated_chunk_is_rejected_and_not_written_twice(self, manager):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"once")

        with pytest.raises(ValueError, match="Expected chunk 1, got 0"):
            await manager.write_chunk(session.upload_id, 0, b"once")

        assert session.temp_file_path.read_bytes() == b"once"

    @pytest.mark.asyncio
    async def test_write_unknown_session_rejected(self, manager):
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.write_chunk("nonexistent-id", 0, b"data")

    @pytest.mark.asyncio
    async def test_temp_file_has_correct_content(self, manager):
        session = await _create(manager, total_size=100)

        await manager.write_chunk(session.upload_id, 0, b"Hello, ")
        await manager.write_chunk(session.upload_id, 1, b"World!")

        assert session.temp_file_path.read_bytes() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_stream_variant_writes_the_fragments_in_order(self, manager):
        session = await _create(manager, total_size=100)

        received = await manager.write_chunk_stream(
            session.upload_id, 0, _stream(b"Hel", b"lo, ", b"World!")
        )

        assert received == 13
        assert session.temp_file_path.read_bytes() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_stream_with_wrong_index_is_rejected_before_reading_it(self, manager):
        session = await _create(manager, total_size=100)
        consumed = []

        async def _watched():
            consumed.append(True)
            yield b"data"

        with pytest.raises(ValueError, match="Expected chunk 0, got 3"):
            await manager.write_chunk_stream(session.upload_id, 3, _watched())

        assert consumed == []


# ============================================================================
# Session Completion
# ============================================================================

class TestSessionCompletion:
    """Test completing upload sessions."""

    @pytest.mark.asyncio
    async def test_complete_session(self, manager):
        session = await _create(manager, total_size=5)
        await manager.write_chunk(session.upload_id, 0, b"Hello")

        temp_path, sha256_hex = await manager.complete_session(session.upload_id)

        assert temp_path.exists()
        assert temp_path.read_bytes() == b"Hello"
        assert sha256_hex == hashlib.sha256(b"Hello").hexdigest()
        # Session should be removed
        assert manager.get_session(session.upload_id) is None

    @pytest.mark.asyncio
    async def test_complete_leaves_only_the_data_file_behind(self, manager, upload_dir):
        session = await _create(manager, total_size=5)
        await manager.write_chunk(session.upload_id, 0, b"Hello")

        await manager.complete_session(session.upload_id)

        assert [p.name for p in upload_dir.iterdir()] == [session.upload_id]

    @pytest.mark.asyncio
    async def test_checksum_covers_every_chunk(self, manager):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"Hello, ")
        await manager.write_chunk_stream(session.upload_id, 1, _stream(b"Wor", b"ld!"))

        _path, sha256_hex = await manager.complete_session(session.upload_id)

        assert sha256_hex == hashlib.sha256(b"Hello, World!").hexdigest()

    @pytest.mark.asyncio
    async def test_complete_unknown_session_raises(self, manager):
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.complete_session("nonexistent-id")

    @pytest.mark.asyncio
    async def test_complete_twice_raises(self, manager):
        session = await _create(manager, total_size=5)
        await manager.write_chunk(session.upload_id, 0, b"Hello")
        await manager.complete_session(session.upload_id)

        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.complete_session(session.upload_id)

    @pytest.mark.asyncio
    async def test_complete_session_missing_temp_file(self, manager):
        session = await _create(manager, total_size=5)
        # Don't write any data — temp file doesn't exist

        with pytest.raises(FileNotFoundError):
            await manager.complete_session(session.upload_id)


# ============================================================================
# Session Abort
# ============================================================================

class TestSessionAbort:
    """Test aborting upload sessions."""

    @pytest.mark.asyncio
    async def test_abort_session(self, manager, upload_dir):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"data")

        await manager.abort_session(session.upload_id)

        assert manager.get_session(session.upload_id) is None
        assert list(upload_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_abort_nonexistent_session(self, manager):
        # Should not raise
        await manager.abort_session("nonexistent-id")
        await manager.abort_session("00000000-0000-4000-8000-000000000000")

    @pytest.mark.asyncio
    async def test_chunk_after_abort_is_rejected_and_leaves_nothing(self, manager, upload_dir):
        session = await _create(manager, total_size=100)
        await manager.abort_session(session.upload_id)

        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.write_chunk(session.upload_id, 0, b"late")

        assert list(upload_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_abort_waits_for_a_running_write_and_leaves_nothing(
        self, manager, other_worker, upload_dir, monkeypatch,
    ):
        """The DELETE used to be able to overtake a write still in progress:
        the write then recreated the temp file after the abort had removed
        it, and nothing ever collected it (#653)."""
        session = await _create(manager, total_size=100)
        in_write = threading.Event()
        release = threading.Event()
        real_append = cu._append_to_data_file

        def _slow_append(path, parts):
            in_write.set()
            assert release.wait(timeout=5)
            return real_append(path, parts)

        monkeypatch.setattr(cu, "_append_to_data_file", _slow_append)

        write = asyncio.create_task(manager.write_chunk(session.upload_id, 0, b"data"))
        assert await asyncio.to_thread(in_write.wait, 5)
        abort = asyncio.create_task(other_worker.abort_session(session.upload_id))
        await asyncio.sleep(0.05)
        assert not abort.done()  # waits for the write instead of overtaking it

        release.set()
        await asyncio.wait_for(write, timeout=5)
        await asyncio.wait_for(abort, timeout=5)

        assert manager.get_session(session.upload_id) is None
        assert list(upload_dir.iterdir()) == []


# ============================================================================
# Sessions are shared by every worker
# ============================================================================

class TestAcrossWorkers:
    """`init` on one worker, chunks and `complete` on others."""

    @pytest.mark.asyncio
    async def test_other_worker_sees_the_session(self, manager, other_worker):
        session = await _create(manager, filename="big.bin", total_size=100, user_id=7)

        seen = other_worker.get_session(session.upload_id)

        assert seen is not None
        assert (seen.filename, seen.total_size, seen.user_id) == ("big.bin", 100, 7)

    @pytest.mark.asyncio
    async def test_chunks_and_complete_on_different_workers(self, manager, other_worker, upload_dir, clock):
        third_worker = ChunkedUploadManager(clock=clock)
        session = await _create(manager, total_size=100)

        await other_worker.write_chunk(session.upload_id, 0, b"Hello, ")
        await manager.write_chunk(session.upload_id, 1, b"World")
        received = await other_worker.write_chunk(session.upload_id, 2, b"!")
        temp_path, sha256_hex = await third_worker.complete_session(session.upload_id)

        assert received == 13
        assert temp_path.read_bytes() == b"Hello, World!"
        assert sha256_hex == hashlib.sha256(b"Hello, World!").hexdigest()
        for worker in (manager, other_worker, third_worker):
            assert worker.get_session(session.upload_id) is None

    @pytest.mark.asyncio
    async def test_checksum_is_right_when_this_worker_missed_a_chunk(self, manager, other_worker):
        """The worker that completes saw chunks 0 and 2 but not 1: its running
        hash is useless and must not be used."""
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"aaa")
        await other_worker.write_chunk(session.upload_id, 1, b"bbb")
        await manager.write_chunk(session.upload_id, 2, b"ccc")

        _path, sha256_hex = await manager.complete_session(session.upload_id)

        assert sha256_hex == hashlib.sha256(b"aaabbbccc").hexdigest()

    @pytest.mark.asyncio
    async def test_checksum_is_right_when_this_worker_saw_only_the_beginning(
        self, manager, other_worker,
    ):
        """No later chunk came by to tell this worker its running hash is
        behind — `complete` has to notice by itself."""
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"aaa")
        await other_worker.write_chunk(session.upload_id, 1, b"bbb")

        _path, sha256_hex = await manager.complete_session(session.upload_id)

        assert sha256_hex == hashlib.sha256(b"aaabbb").hexdigest()

    @pytest.mark.asyncio
    async def test_order_is_enforced_across_workers(self, manager, other_worker):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"aaa")

        with pytest.raises(ValueError, match="Expected chunk 1, got 0"):
            await other_worker.write_chunk(session.upload_id, 0, b"aaa")

    @pytest.mark.asyncio
    async def test_abort_on_another_worker(self, manager, other_worker, upload_dir):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"data")

        await other_worker.abort_session(session.upload_id)

        assert manager.get_session(session.upload_id) is None
        assert list(upload_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_session_survives_a_worker_restart(self, manager, upload_dir, clock):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"before ")
        await manager.shutdown()

        restarted = ChunkedUploadManager(clock=clock)
        await restarted.write_chunk(session.upload_id, 1, b"after")
        temp_path, sha256_hex = await restarted.complete_session(session.upload_id)

        assert temp_path.read_bytes() == b"before after"
        assert sha256_hex == hashlib.sha256(b"before after").hexdigest()

    @pytest.mark.asyncio
    async def test_concurrent_chunk_with_the_same_index_is_written_once(
        self, manager, other_worker,
    ):
        session = await _create(manager, total_size=100)

        results = await asyncio.gather(
            manager.write_chunk(session.upload_id, 0, b"same"),
            other_worker.write_chunk(session.upload_id, 0, b"same"),
            return_exceptions=True,
        )

        assert sorted(type(r).__name__ for r in results) == ["ValueError", "int"]
        assert session.temp_file_path.read_bytes() == b"same"


# ============================================================================
# Stale Session Cleanup
# ============================================================================

class TestStaleCleanup:
    """Test cleanup of stale sessions."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_stale_sessions(self, manager, upload_dir, clock):
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"data")

        clock.now += SESSION_MAX_AGE.total_seconds() + 3600

        await manager._cleanup_stale()

        assert manager.get_session(session.upload_id) is None
        assert list(upload_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_cleanup_keeps_fresh_sessions(self, manager):
        session = await _create(manager, total_size=100)

        await manager._cleanup_stale()

        assert manager.get_session(session.upload_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_goes_by_the_last_chunk_not_by_the_start(self, manager, clock):
        """A long upload that is still making progress is not stale."""
        session = await _create(manager, total_size=100)
        clock.now += SESSION_MAX_AGE.total_seconds() - 60
        await manager.write_chunk(session.upload_id, 0, b"data")
        clock.now += 3600  # older than the limit since creation, not since the chunk

        await manager._cleanup_stale()

        assert manager.get_session(session.upload_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_spares_a_session_that_got_a_chunk_while_it_waited(
        self, manager, other_worker, clock, monkeypatch,
    ):
        """The janitor reads the session, finds it stale, and waits for the
        lock — held by a chunk that is just being written. It must look again
        once it has the lock."""
        session = await _create(manager, total_size=100)
        clock.now += SESSION_MAX_AGE.total_seconds() + 3600
        real_locked = manager._locked
        arrived = []

        def _locked_after_a_chunk(upload_id):
            if not arrived:
                arrived.append(True)
                other_worker._write_locked(upload_id, 0, [b"just in time"])
            return real_locked(upload_id)

        monkeypatch.setattr(manager, "_locked", _locked_after_a_chunk)

        await manager._cleanup_stale()

        assert arrived
        assert manager.get_session(session.upload_id) is not None
        assert session.temp_file_path.read_bytes() == b"just in time"

    @pytest.mark.asyncio
    async def test_cleanup_removes_sessions_of_other_workers(self, manager, other_worker, clock):
        session = await _create(other_worker, total_size=100)
        clock.now += SESSION_MAX_AGE.total_seconds() + 3600

        await manager._cleanup_stale()

        assert other_worker.get_session(session.upload_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_collects_old_leftovers_without_a_session(self, manager, upload_dir, clock):
        """A data file whose session is gone: a completed upload the route
        never moved, or a file from before sessions were stored on disk."""
        upload_dir.mkdir(parents=True, exist_ok=True)
        old_time = clock.now - SESSION_MAX_AGE.total_seconds() - 3600
        orphan = upload_dir / "11111111-1111-4111-8111-111111111111"
        orphan.write_bytes(b"left behind")
        os.utime(orphan, (old_time, old_time))
        fresh = upload_dir / "22222222-2222-4222-8222-222222222222"
        fresh.write_bytes(b"just completed, about to be moved")
        os.utime(fresh, (clock.now, clock.now))
        foreign = upload_dir / "not-ours.txt"
        foreign.write_bytes(b"x")
        os.utime(foreign, (old_time, old_time))

        await manager._cleanup_stale()

        assert not orphan.exists()
        assert fresh.exists()
        assert foreign.exists()

    @pytest.mark.asyncio
    async def test_cleanup_without_a_directory_does_nothing(self, manager):
        await manager._cleanup_stale()


# ============================================================================
# Shutdown
# ============================================================================

class TestShutdown:
    """Test graceful shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_leaves_sessions_for_the_other_workers(self, manager, other_worker):
        """One worker going down must not take the uploads the others are
        still serving with it."""
        session = await _create(manager, total_size=100)
        await manager.write_chunk(session.upload_id, 0, b"data")

        await manager.shutdown()

        assert other_worker.get_session(session.upload_id) is not None
        assert session.temp_file_path.read_bytes() == b"data"

    @pytest.mark.asyncio
    async def test_shutdown_stops_the_cleanup_loop(self, manager):
        manager.start_cleanup_loop()
        task = manager._cleanup_task

        await manager.shutdown()

        assert task.done()


# ============================================================================
# Overflow Guard (DoS hardening — Posten 5 #3)
# ============================================================================

@pytest.mark.asyncio
async def test_write_chunk_rejects_overflow_beyond_total_size(manager, upload_dir):
    """A chunk that pushes received_bytes past the declared total_size is rejected
    and the session is aborted (disk-fill DoS guard)."""
    session = await _create(manager, target_path="x", filename="f.bin", total_size=4)
    # First chunk fits exactly (4 bytes == total_size).
    await manager.write_chunk(session.upload_id, 0, b"AAAA")
    # Second chunk overflows.
    with pytest.raises(ValueError, match="exceeds declared total_size"):
        await manager.write_chunk(session.upload_id, 1, b"B")
    # Session was aborted → temp file gone, session unknown.
    assert manager.get_session(session.upload_id) is None
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_write_chunk_stream_rejects_overflow(manager, upload_dir):
    """Streaming variant also rejects overflow before writing to disk."""
    session = await _create(manager, target_path="x", filename="f.bin", total_size=3)
    with pytest.raises(ValueError, match="exceeds declared total_size"):
        await manager.write_chunk_stream(session.upload_id, 0, _stream(b"AA", b"BB"))
    assert manager.get_session(session.upload_id) is None
    assert list(upload_dir.iterdir()) == []


# ============================================================================
# The session file is not trusted
# ============================================================================

_VALID_ID = "33333333-3333-4333-8333-333333333333"


def _session_dict(**overrides):
    data = {
        "upload_id": _VALID_ID, "target_path": "uploads", "filename": "f.bin",
        "total_size": 100, "chunk_size": 1024, "received_bytes": 0,
        "next_chunk_index": 0, "user_id": 1, "username": "u",
        "created_at": 1_800_000_000.0, "last_activity": 1_800_000_000.0,
    }
    data.update(overrides)
    return data


def _plant_session(upload_dir, **overrides):
    """Write the session file of `_VALID_ID` by hand, as someone with access
    to the directory could. *overrides* change its content, never its name."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    data = _session_dict(**overrides)
    (upload_dir / f"{_VALID_ID}.json").write_text(json.dumps(data))
    (upload_dir / f"{_VALID_ID}.lock").write_text("")
    return data


class TestUploadIdIsNeverAPath:
    """The id comes from the URL and becomes a file name."""

    @pytest.mark.parametrize(
        "upload_id",
        [
            "../../etc/passwd",
            "..",
            "",
            "a/b",
            "33333333-3333-4333-8333-333333333333/../x",
            "33333333-3333-4333-8333-333333333333.json",
            "33333333-3333-4333-8333-33333333333",    # too short
            "33333333-3333-4333-8333-3333333333333",  # too long
            "33333333333343338333333333333333",       # no dashes
            "33333333-3333-4333-8333-33333333333G",   # not hex
            "33333333-3333-4333-8333-33333333333\n",
        ],
    )
    @pytest.mark.asyncio
    async def test_anything_but_a_uuid_is_an_unknown_session(self, manager, upload_dir, upload_id):
        upload_dir.mkdir(parents=True, exist_ok=True)
        outside = upload_dir.parent / "outside.json"
        outside.write_text("{}")

        assert manager.get_session(upload_id) is None
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.write_chunk(upload_id, 0, b"x")
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.complete_session(upload_id)
        await manager.abort_session(upload_id)

        assert outside.read_text() == "{}"
        assert list(upload_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_id_that_continues_after_a_uuid_does_not_reach_a_file_outside(
        self, manager, upload_dir,
    ):
        """An id that only STARTS like a UUID, with a real, well-formed
        session file waiting where the rest of it leads."""
        traversal = f"{_VALID_ID}/../../outside"
        (upload_dir / _VALID_ID).mkdir(parents=True)  # so the path resolves
        planted = _session_dict(upload_id=traversal)
        (upload_dir.parent / "outside.json").write_text(json.dumps(planted))
        (upload_dir.parent / "outside.lock").write_text("")
        (upload_dir.parent / "outside").write_bytes(b"data")

        assert manager.get_session(traversal) is None
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.write_chunk(traversal, 0, b"x")
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.complete_session(traversal)
        await manager.abort_session(traversal)

        assert (upload_dir.parent / "outside").read_bytes() == b"data"
        assert (upload_dir.parent / "outside.json").exists()

    @pytest.mark.asyncio
    async def test_uppercase_id_is_not_another_name_for_a_session(self, manager):
        session = await _create(manager)

        assert manager.get_session(session.upload_id.upper()) is None


class TestSessionFileIsValidated:
    @pytest.mark.parametrize(
        "content",
        [
            "{not json",
            "[]",
            json.dumps({"upload_id": _VALID_ID}),
        ],
    )
    def test_unreadable_session_file_is_an_unknown_session(self, manager, upload_dir, content):
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / f"{_VALID_ID}.json").write_text(content)

        assert manager.get_session(_VALID_ID) is None

    @pytest.mark.parametrize(
        "overrides",
        [
            {"upload_id": "44444444-4444-4444-8444-444444444444"},  # file of another id
            {"total_size": -1},
            {"total_size": "100"},
            {"received_bytes": -5},
            {"next_chunk_index": -1},
            {"next_chunk_index": True},
            {"user_id": "1"},
            {"filename": 7},
            {"target_path": None},
            {"last_activity": "yesterday"},
        ],
    )
    def test_malformed_field_is_an_unknown_session(self, manager, upload_dir, overrides):
        _plant_session(upload_dir, **overrides)

        assert manager.get_session(_VALID_ID) is None

    def test_well_formed_planted_session_is_readable(self, manager, upload_dir):
        """Control for the cases above: the planted file is otherwise valid."""
        _plant_session(upload_dir)

        assert manager.get_session(_VALID_ID) is not None

    def test_session_file_behind_a_symlink_is_not_read(self, manager, upload_dir):
        data = _plant_session(upload_dir)
        elsewhere = upload_dir.parent / "elsewhere.json"
        elsewhere.write_text(json.dumps(data))
        meta = upload_dir / f"{_VALID_ID}.json"
        meta.unlink()
        meta.symlink_to(elsewhere)

        assert manager.get_session(_VALID_ID) is None


class TestDataFileIsNeverFollowed:
    @pytest.mark.asyncio
    async def test_chunk_is_not_written_through_a_symlink(self, manager, upload_dir):
        """Someone who can write to the upload directory plants a link where
        the data file belongs: the chunk must not land in the link's target."""
        session = await _create(manager, total_size=100)
        victim = upload_dir.parent / "victim.txt"
        victim.write_bytes(b"original")
        session.temp_file_path.symlink_to(victim)

        with pytest.raises(ValueError):
            await manager.write_chunk(session.upload_id, 0, b"appended")

        assert victim.read_bytes() == b"original"

    @pytest.mark.asyncio
    async def test_complete_refuses_a_data_file_that_is_a_symlink(self, manager, upload_dir):
        """Completing would move the link into the user's folder — and with
        it read access to whatever it points at."""
        session = await _create(manager, total_size=100)
        secret = upload_dir.parent / "secret.txt"
        secret.write_bytes(b"secret")
        session.temp_file_path.symlink_to(secret)

        with pytest.raises(ValueError):
            await manager.complete_session(session.upload_id)

        assert secret.read_bytes() == b"secret"
        assert manager.get_session(session.upload_id) is None
        assert not session.temp_file_path.is_symlink()


class TestDataFileMustBeARegularFile:
    @pytest.mark.asyncio
    async def test_complete_refuses_a_directory_where_the_data_file_belongs(self, manager):
        session = await _create(manager, total_size=100)
        session.temp_file_path.mkdir()

        with pytest.raises(ValueError, match="not a regular file"):
            await manager.complete_session(session.upload_id)

        assert manager.get_session(session.upload_id) is None


# ============================================================================
# Moving the completed file: that file, or nothing
# ============================================================================

class TestMoveCompletedUpload:
    """`complete` checks the data file; the move happens afterwards, from a
    directory others can write to. What reaches the destination must be the
    file that was checked."""

    @staticmethod
    async def _completed(manager, data=b"Hello, World!"):
        session = await _create(manager, total_size=len(data))
        await manager.write_chunk(session.upload_id, 0, data)
        return await manager.complete_session_checked(session.upload_id)

    @pytest.mark.asyncio
    async def test_checked_variant_describes_the_file(self, manager):
        completed = await self._completed(manager)

        st = os.stat(completed.temp_path)
        assert completed.sha256_hex == hashlib.sha256(b"Hello, World!").hexdigest()
        assert completed.size == 13
        assert (completed.device, completed.inode) == (st.st_dev, st.st_ino)

    @pytest.mark.asyncio
    async def test_moves_the_file_and_sets_the_storage_mode(self, manager, tmp_path):
        completed = await self._completed(manager)
        os.chmod(completed.temp_path, 0o600)
        destination = tmp_path / "target" / "big.bin"
        destination.parent.mkdir()

        cu.move_completed_upload(completed, destination)

        assert destination.read_bytes() == b"Hello, World!"
        assert not completed.temp_path.exists()
        assert destination.stat().st_mode & 0o777 == cu.STORAGE_FILE_MODE

    @pytest.mark.asyncio
    async def test_replaces_an_existing_destination(self, manager, tmp_path):
        completed = await self._completed(manager)
        destination = tmp_path / "big.bin"
        destination.write_bytes(b"old version")

        cu.move_completed_upload(completed, destination)

        assert destination.read_bytes() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_link_swapped_in_after_the_check_is_not_moved(self, manager, tmp_path):
        """The race the check alone leaves open: regular file at `complete`,
        a link to something else by the time of the move."""
        completed = await self._completed(manager)
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"secret")
        os.chmod(secret, 0o600)
        completed.temp_path.unlink()
        completed.temp_path.symlink_to(secret)
        destination = tmp_path / "big.bin"

        with pytest.raises(ValueError, match="changed after it was checked"):
            cu.move_completed_upload(completed, destination)

        assert not destination.exists() and not destination.is_symlink()
        assert secret.read_bytes() == b"secret"
        assert secret.stat().st_mode & 0o777 == 0o600  # nobody chmod-ed the target

    @pytest.mark.asyncio
    async def test_other_file_swapped_in_after_the_check_is_not_moved(self, manager, tmp_path):
        """Not a link, just not the file that was hashed."""
        completed = await self._completed(manager)
        completed.temp_path.unlink()
        completed.temp_path.write_bytes(b"something else entirely")
        destination = tmp_path / "big.bin"

        with pytest.raises(ValueError, match="changed after it was checked"):
            cu.move_completed_upload(completed, destination)

        assert not destination.exists()

    @pytest.mark.asyncio
    async def test_missing_data_file_is_not_moved(self, manager, tmp_path):
        completed = await self._completed(manager)
        completed.temp_path.unlink()

        with pytest.raises(ValueError, match="changed after it was checked"):
            cu.move_completed_upload(completed, tmp_path / "big.bin")

    @pytest.mark.asyncio
    async def test_link_swapped_in_at_the_last_instant_is_taken_back(
        self, manager, tmp_path, monkeypatch,
    ):
        """The swap lands between the mover's own check and its rename: the
        rename then moves the link. It must not stay at the destination, and
        the mode must not be set on what it points at."""
        completed = await self._completed(manager)
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"secret")
        os.chmod(secret, 0o600)
        destination = tmp_path / "big.bin"
        real_replace = os.replace

        def _swap_then_replace(src, dst):
            if os.fspath(src) == os.fspath(completed.temp_path):
                os.unlink(src)
                os.symlink(secret, src)
            return real_replace(src, dst)

        monkeypatch.setattr(cu.os, "replace", _swap_then_replace)

        with pytest.raises(ValueError, match="changed after it was checked"):
            cu.move_completed_upload(completed, destination)

        assert not destination.exists() and not destination.is_symlink()
        assert secret.read_bytes() == b"secret"
        assert secret.stat().st_mode & 0o777 == 0o600

    @pytest.mark.asyncio
    async def test_destination_on_another_filesystem_is_copied(
        self, manager, tmp_path, monkeypatch,
    ):
        import errno

        completed = await self._completed(manager)
        os.chmod(completed.temp_path, 0o600)
        destination = tmp_path / "big.bin"
        destination.write_bytes(b"old version")
        real_replace = os.replace

        def _cross_device(src, dst):
            if os.fspath(src) == os.fspath(completed.temp_path):
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real_replace(src, dst)

        monkeypatch.setattr(cu.os, "replace", _cross_device)

        cu.move_completed_upload(completed, destination)

        assert destination.read_bytes() == b"Hello, World!"
        assert destination.stat().st_mode & 0o777 == cu.STORAGE_FILE_MODE
        assert not completed.temp_path.exists()
        assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".upload-")] == []

    @pytest.mark.asyncio
    async def test_other_move_errors_are_not_mistaken_for_another_filesystem(
        self, manager, tmp_path,
    ):
        completed = await self._completed(manager)

        with pytest.raises(OSError):
            cu.move_completed_upload(completed, tmp_path / "no-such-dir" / "big.bin")

        assert completed.temp_path.read_bytes() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_refused_move_is_not_retried_as_a_copy(self, manager, tmp_path, monkeypatch):
        """Only "other filesystem" falls back to copying. A move that is
        refused stays refused."""
        import errno

        completed = await self._completed(manager)
        destination = tmp_path / "big.bin"

        real_replace = os.replace

        def _refused(src, dst):
            # Only the move itself: a copy that followed would get through.
            if os.fspath(src) == os.fspath(completed.temp_path):
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_replace(src, dst)

        monkeypatch.setattr(cu.os, "replace", _refused)

        with pytest.raises(PermissionError):
            cu.move_completed_upload(completed, destination)

        assert not destination.exists()
        assert completed.temp_path.read_bytes() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_mode_is_set_on_the_moved_file_not_on_the_destination_path(
        self, manager, tmp_path, monkeypatch,
    ):
        """After the move the destination path is checked, then the mode is
        set. A link put at that path in between must not get the mode change
        passed on to its target."""
        completed = await self._completed(manager)
        os.chmod(completed.temp_path, 0o600)
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"secret")
        os.chmod(secret, 0o600)
        destination = tmp_path / "big.bin"
        moved_aside = tmp_path / "moved-aside.bin"
        real_lstat = os.lstat

        def _lstat_then_swap(path, *args, **kwargs):
            result = real_lstat(path, *args, **kwargs)
            if os.fspath(path) == os.fspath(destination):
                os.rename(destination, moved_aside)
                os.symlink(secret, destination)
            return result

        monkeypatch.setattr(cu.os, "lstat", _lstat_then_swap)

        cu.move_completed_upload(completed, destination)

        assert secret.stat().st_mode & 0o777 == 0o600
        assert moved_aside.stat().st_mode & 0o777 == cu.STORAGE_FILE_MODE


# ============================================================================
# A named pipe where a file belongs must not hang the worker
# ============================================================================

def _finishes(fn, timeout=5.0):
    """Run *fn* in a daemon thread; fail if it is still running after *timeout*.

    Opening a FIFO for reading blocks until someone opens it for writing. A
    regression here would hang, so the call must not run in the test's own
    thread (nor in an executor thread, which would keep the interpreter alive).
    """
    outcome = {}

    def _run():
        try:
            outcome["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - handed to the caller
            outcome["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), "blocked on a named pipe"
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
class TestNamedPipeDoesNotBlock:
    """Whoever can write to the upload directory can put a FIFO where one of
    a session's files belongs. Every open of those files used to wait on it
    forever — one stuck thread per request."""

    def test_pipe_as_session_file_is_an_unknown_session(self, manager, upload_dir):
        upload_dir.mkdir(parents=True)
        os.mkfifo(upload_dir / f"{_VALID_ID}.json")

        assert _finishes(lambda: manager.get_session(_VALID_ID)) is None

    def test_pipe_as_lock_file_is_an_unknown_session(self, manager, upload_dir):
        _plant_session(upload_dir)
        lock = upload_dir / f"{_VALID_ID}.lock"
        lock.unlink()
        os.mkfifo(lock)

        with pytest.raises(ValueError, match="Unknown upload session"):
            _finishes(lambda: manager._write_locked(_VALID_ID, 0, [b"x"]))

    def test_pipe_as_data_file_refuses_the_chunk(self, manager, upload_dir):
        _plant_session(upload_dir)
        os.mkfifo(upload_dir / _VALID_ID)

        with pytest.raises(ValueError):
            _finishes(lambda: manager._write_locked(_VALID_ID, 0, [b"x"]))

    def test_pipe_as_data_file_refuses_complete(self, manager, upload_dir):
        _plant_session(upload_dir, received_bytes=1, next_chunk_index=1)
        os.mkfifo(upload_dir / _VALID_ID)

        with pytest.raises(ValueError, match="not a regular file"):
            _finishes(lambda: manager._complete_locked(_VALID_ID))

        assert manager.get_session(_VALID_ID) is None

    @pytest.mark.asyncio
    async def test_pipe_swapped_in_before_the_move_is_not_moved(self, manager, tmp_path):
        session = await _create(manager, total_size=5)
        await manager.write_chunk(session.upload_id, 0, b"Hello")
        completed = await manager.complete_session_checked(session.upload_id)
        completed.temp_path.unlink()
        os.mkfifo(completed.temp_path)
        destination = tmp_path / "big.bin"

        with pytest.raises(ValueError, match="changed after it was checked"):
            _finishes(lambda: cu.move_completed_upload(completed, destination))

        assert not destination.exists()

    def test_cleanup_is_not_stopped_by_a_pipe(self, manager, upload_dir, clock):
        upload_dir.mkdir(parents=True)
        old = clock.now - SESSION_MAX_AGE.total_seconds() - 3600
        pipe = upload_dir / f"{_VALID_ID}.json"
        os.mkfifo(pipe)
        os.utime(pipe, (old, old))

        _finishes(manager._cleanup_stale_sync)

        assert not pipe.exists()
