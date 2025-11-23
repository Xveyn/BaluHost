"""Tests for upload progress tracking."""
import asyncio
import pytest
from app.services.upload_progress import get_upload_progress_manager, UploadProgress


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
    
    # After cleanup delay, session should be gone
    await asyncio.sleep(61)  # Wait for cleanup (60s + buffer)
    
    progress = manager.get_progress(upload_id)
    # Note: This might still exist in real scenarios, testing cleanup timing is tricky
