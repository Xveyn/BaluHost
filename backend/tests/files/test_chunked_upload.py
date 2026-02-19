"""
Tests for chunked upload session manager (services/files/chunked_upload.py).

Covers:
- Session creation and retrieval
- Sequential chunk writing
- Wrong chunk order rejection
- Session completion
- Session abort and cleanup
- Stale session cleanup
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.files.chunked_upload import (
    ChunkedUploadManager,
    ChunkedUploadSession,
)


@pytest.fixture
def manager():
    """Create a fresh ChunkedUploadManager for each test."""
    mgr = ChunkedUploadManager()
    yield mgr
    # Clean up any temp files
    asyncio.get_event_loop().run_until_complete(mgr.shutdown())


# ============================================================================
# Session Creation
# ============================================================================

class TestSessionCreation:
    """Test upload session creation."""

    @pytest.mark.asyncio
    async def test_create_session(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=1024,
            user_id=1,
            username="testuser",
        )

        assert session.upload_id is not None
        assert session.filename == "test.txt"
        assert session.total_size == 1024
        assert session.received_bytes == 0
        assert session.next_chunk_index == 0
        assert session.user_id == 1

    @pytest.mark.asyncio
    async def test_create_session_default_chunk_size(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=1024,
            user_id=1,
            username="testuser",
        )

        assert session.chunk_size == ChunkedUploadManager.DEFAULT_CHUNK_SIZE

    @pytest.mark.asyncio
    async def test_create_session_custom_chunk_size(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=1024,
            user_id=1,
            username="testuser",
            chunk_size=5 * 1024 * 1024,
        )

        assert session.chunk_size == 5 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_create_multiple_sessions(self, manager):
        s1 = await manager.create_session(
            target_path="uploads",
            filename="file1.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )
        s2 = await manager.create_session(
            target_path="uploads",
            filename="file2.txt",
            total_size=200,
            user_id=1,
            username="testuser",
        )

        assert s1.upload_id != s2.upload_id


class TestSessionRetrieval:
    """Test session get operations."""

    @pytest.mark.asyncio
    async def test_get_existing_session(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=1024,
            user_id=1,
            username="testuser",
        )

        fetched = manager.get_session(session.upload_id)
        assert fetched is not None
        assert fetched.upload_id == session.upload_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, manager):
        fetched = manager.get_session("nonexistent-id")
        assert fetched is None


# ============================================================================
# Chunk Writing
# ============================================================================

class TestChunkWriting:
    """Test writing chunks to sessions."""

    @pytest.mark.asyncio
    async def test_write_first_chunk(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )

        data = b"Hello, World!"
        received = await manager.write_chunk(session.upload_id, 0, data)

        assert received == len(data)
        assert session.next_chunk_index == 1

    @pytest.mark.asyncio
    async def test_write_sequential_chunks(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )

        await manager.write_chunk(session.upload_id, 0, b"chunk0")
        await manager.write_chunk(session.upload_id, 1, b"chunk1")
        received = await manager.write_chunk(session.upload_id, 2, b"chunk2")

        assert received == 18  # 6 + 6 + 6
        assert session.next_chunk_index == 3

    @pytest.mark.asyncio
    async def test_write_wrong_chunk_order_rejected(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )

        # Skip chunk 0, try to write chunk 1
        with pytest.raises(ValueError, match="Expected chunk 0, got 1"):
            await manager.write_chunk(session.upload_id, 1, b"data")

    @pytest.mark.asyncio
    async def test_write_unknown_session_rejected(self, manager):
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.write_chunk("nonexistent-id", 0, b"data")

    @pytest.mark.asyncio
    async def test_temp_file_has_correct_content(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )

        await manager.write_chunk(session.upload_id, 0, b"Hello, ")
        await manager.write_chunk(session.upload_id, 1, b"World!")

        content = session.temp_file_path.read_bytes()
        assert content == b"Hello, World!"


# ============================================================================
# Session Completion
# ============================================================================

class TestSessionCompletion:
    """Test completing upload sessions."""

    @pytest.mark.asyncio
    async def test_complete_session(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=5,
            user_id=1,
            username="testuser",
        )
        await manager.write_chunk(session.upload_id, 0, b"Hello")

        temp_path = await manager.complete_session(session.upload_id)

        assert temp_path.exists()
        assert temp_path.read_bytes() == b"Hello"
        # Session should be removed
        assert manager.get_session(session.upload_id) is None

    @pytest.mark.asyncio
    async def test_complete_unknown_session_raises(self, manager):
        with pytest.raises(ValueError, match="Unknown upload session"):
            await manager.complete_session("nonexistent-id")

    @pytest.mark.asyncio
    async def test_complete_session_missing_temp_file(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=5,
            user_id=1,
            username="testuser",
        )
        # Don't write any data — temp file doesn't exist

        with pytest.raises(FileNotFoundError):
            await manager.complete_session(session.upload_id)


# ============================================================================
# Session Abort
# ============================================================================

class TestSessionAbort:
    """Test aborting upload sessions."""

    @pytest.mark.asyncio
    async def test_abort_session(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )
        await manager.write_chunk(session.upload_id, 0, b"data")
        temp_path = session.temp_file_path

        await manager.abort_session(session.upload_id)

        assert manager.get_session(session.upload_id) is None
        assert not temp_path.exists()

    @pytest.mark.asyncio
    async def test_abort_nonexistent_session(self, manager):
        # Should not raise
        await manager.abort_session("nonexistent-id")


# ============================================================================
# Stale Session Cleanup
# ============================================================================

class TestStaleCleanup:
    """Test cleanup of stale sessions."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_stale_sessions(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="old.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )
        await manager.write_chunk(session.upload_id, 0, b"data")

        # Manually age the session
        session.created_at = datetime.now(timezone.utc) - timedelta(hours=25)

        await manager._cleanup_stale()

        assert manager.get_session(session.upload_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_fresh_sessions(self, manager):
        session = await manager.create_session(
            target_path="uploads",
            filename="fresh.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )

        await manager._cleanup_stale()

        assert manager.get_session(session.upload_id) is not None


# ============================================================================
# Shutdown
# ============================================================================

class TestShutdown:
    """Test graceful shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_clears_sessions(self, manager):
        await manager.create_session(
            target_path="uploads",
            filename="test.txt",
            total_size=100,
            user_id=1,
            username="testuser",
        )

        await manager.shutdown()

        assert len(manager._sessions) == 0
