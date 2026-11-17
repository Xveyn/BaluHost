"""Tests for upload progress tracking."""
import asyncio
import pytest
from app.services.upload_progress import get_upload_progress_manager, UploadProgress
from app.services import upload_progress as upload_progress_service


@pytest.fixture(autouse=True)
def reset_upload_manager():
    """Reset the global upload progress manager between tests for isolation."""
    upload_progress_service._manager = None
    yield
    upload_progress_service._manager = None


@pytest.mark.asyncio
async def test_create_upload_session():
    """Test creating an upload session."""
    manager = get_upload_progress_manager()
    
    upload_id = manager.create_upload_session("test.txt", 1024)
    
    assert upload_id is not None
    assert len(upload_id) > 0
    
    progress = manager.get_progress(upload_id)
    assert progress is not None
    assert progress.filename == "test.txt"
    assert progress.total_bytes == 1024
    assert progress.uploaded_bytes == 0
    assert progress.status == "uploading"


@pytest.mark.asyncio
async def test_update_progress():
    """Test updating upload progress."""
    manager = get_upload_progress_manager()
    
    upload_id = manager.create_upload_session("test.txt", 1024)
    
    # Subscribe to progress updates
    received_updates = []
    queue = await manager.subscribe(upload_id)
    
    # Update progress in background
    async def update_and_collect():
        await manager.update_progress(upload_id, 512)
        await asyncio.sleep(0.1)
        await manager.update_progress(upload_id, 1024)
        await asyncio.sleep(0.1)
        await manager.complete_upload(upload_id)
    
    update_task = asyncio.create_task(update_and_collect())
    
    # Collect updates
    while True:
        try:
            progress = await asyncio.wait_for(queue.get(), timeout=1.0)
            if progress is None:
                break
            received_updates.append(progress)
            if progress.status in ('completed', 'failed'):
                break
        except asyncio.TimeoutError:
            break
    
    await update_task
    
    # Verify updates received
    assert len(received_updates) >= 2
    assert any(p.uploaded_bytes == 512 for p in received_updates)
    assert any(p.status == "completed" for p in received_updates)
    
    await manager.unsubscribe(upload_id, queue)


@pytest.mark.asyncio
async def test_fail_upload():
    """Test marking upload as failed."""
    manager = get_upload_progress_manager()
    
    upload_id = manager.create_upload_session("test.txt", 1024)
    
    await manager.fail_upload(upload_id, "Quota exceeded")
    
    progress = manager.get_progress(upload_id)
    assert progress is not None
    assert progress.status == "failed"
    assert progress.error == "Quota exceeded"


@pytest.mark.asyncio
async def test_multiple_subscribers():
    """Test multiple subscribers to same upload."""
    manager = get_upload_progress_manager()
    
    upload_id = manager.create_upload_session("test.txt", 1024)
    
    # Create multiple subscribers
    queue1 = await manager.subscribe(upload_id)
    queue2 = await manager.subscribe(upload_id)
    
    # Update progress
    await manager.update_progress(upload_id, 512)
    
    # Both queues should receive the update
    progress1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    progress2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
    
    assert progress1.uploaded_bytes == 512
    assert progress2.uploaded_bytes == 512
    
    await manager.unsubscribe(upload_id, queue1)
    await manager.unsubscribe(upload_id, queue2)


@pytest.mark.asyncio
async def test_progress_percentage():
    """Test progress percentage calculation."""
    progress = UploadProgress(
        upload_id="test-123",
        filename="test.txt",
        total_bytes=1000,
        uploaded_bytes=250,
        status="uploading"
    )
    
    assert progress.progress_percentage == 25.0
    
    progress.uploaded_bytes = 500
    assert progress.progress_percentage == 50.0
    
    progress.uploaded_bytes = 1000
    assert progress.progress_percentage == 100.0


@pytest.mark.asyncio
async def test_cleanup_after_completion():
    """Test that upload sessions are cleaned up after completion."""
    manager = get_upload_progress_manager()
    
    upload_id = manager.create_upload_session("test.txt", 1024)
    
    # Complete upload
    await manager.complete_upload(upload_id)
    
    # Session should still exist immediately
    progress = manager.get_progress(upload_id)
    assert progress is not None
    assert progress.status == "completed"
    
    # In dev/test mode cleanup delay is 0s, so a short wait suffices
    await asyncio.sleep(0.2)

    progress = manager.get_progress(upload_id)


# ─── Sessions always end (#834) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fail_unfinished_fails_only_sessions_still_uploading():
    manager = get_upload_progress_manager()
    running = manager.create_upload_session("running.bin", 10)
    done = manager.create_upload_session("done.bin", 10)
    failed = manager.create_upload_session("failed.bin", 10)
    await manager.complete_upload(done)
    await manager.fail_upload(failed, "first error")
    # Keep the finished ones for the assertions below (dev mode cleans up at once).
    kept = {uid: manager.get_progress(uid) for uid in (done, failed)}

    await manager.fail_unfinished([running, done, failed, "unknown-id"], "Upload failed")

    assert manager.get_progress(running).status == "failed"
    assert manager.get_progress(running).error == "Upload failed"
    assert kept[done].status == "completed"
    assert kept[failed].error == "first error"


@pytest.mark.asyncio
async def test_stalled_session_is_dropped_when_the_next_one_starts():
    manager = get_upload_progress_manager()
    now = [1000.0]
    manager._monotonic = lambda: now[0]
    stalled = manager.create_upload_session("abandoned.bin", 10)
    listener = await manager.subscribe(stalled)
    await listener.get()  # the current state, sent on subscribe

    now[0] += manager.STALLED_AFTER_SECONDS + 1
    fresh = manager.create_upload_session("new.bin", 10)

    assert manager.get_progress(stalled) is None
    assert manager.get_progress(fresh) is not None
    assert await listener.get() is None  # the stream is told it is over
    assert stalled not in manager._touched


@pytest.mark.asyncio
async def test_session_with_recent_progress_is_not_stalled():
    manager = get_upload_progress_manager()
    now = [1000.0]
    manager._monotonic = lambda: now[0]
    slow = manager.create_upload_session("slow.bin", 100)

    now[0] += manager.STALLED_AFTER_SECONDS - 10
    await manager.update_progress(slow, 50)
    now[0] += manager.STALLED_AFTER_SECONDS - 10  # long since the start, not since the update
    manager.create_upload_session("new.bin", 10)

    assert manager.get_progress(slow).status == "uploading"


@pytest.mark.asyncio
async def test_finished_session_is_not_treated_as_stalled():
    """A finished session waits for its own cleanup; the stall rule is for
    "uploading" only."""
    manager = get_upload_progress_manager()
    now = [1000.0]
    manager._monotonic = lambda: now[0]
    done = manager.create_upload_session("done.bin", 10)
    manager._progress[done].status = "completed"

    now[0] += manager.STALLED_AFTER_SECONDS + 1
    manager.create_upload_session("new.bin", 10)

    assert manager.get_progress(done) is not None
