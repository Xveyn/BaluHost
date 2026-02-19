"""Unit tests for SSD cache (bcache) service — DevSsdCacheBackend."""

import pytest

from app.schemas.ssd_cache import (
    CacheAttachRequest,
    CacheConfigureRequest,
    CacheDetachRequest,
    CacheMode,
    CacheStatus,
    ExternalBitmapRequest,
)
from app.services.hardware.ssd_cache import (
    DevSsdCacheBackend,
    _select_backend,
    request_cache_confirmation,
    execute_cache_confirmation,
    _confirmations,
)
from app.core import config


# ---------------------------------------------------------------------------
# DevSsdCacheBackend basics
# ---------------------------------------------------------------------------

@pytest.fixture
def backend() -> DevSsdCacheBackend:
    return DevSsdCacheBackend()


def test_initial_state_empty(backend: DevSsdCacheBackend):
    assert backend.get_all_cache_statuses() == []
    assert backend.get_cache_status("md0") is None
    assert backend.get_cache_devices() == set()
    assert backend.get_cached_arrays() == set()


def test_attach_cache_success(backend: DevSsdCacheBackend):
    payload = CacheAttachRequest(array="md0", cache_device="nvme1n1p1", mode=CacheMode.WRITETHROUGH)
    resp = backend.attach_cache(payload)

    assert "attached" in resp.message.lower()
    assert "md0" in resp.message
    assert "nvme1n1p1" in resp.message

    statuses = backend.get_all_cache_statuses()
    assert len(statuses) == 1
    st = statuses[0]
    assert st.array_name == "md0"
    assert st.cache_device == "nvme1n1p1"
    assert st.mode == CacheMode.WRITETHROUGH
    assert st.state == "running"
    assert st.bcache_device == "bcache0"


def test_attach_cache_writeback(backend: DevSsdCacheBackend):
    payload = CacheAttachRequest(array="md0", cache_device="nvme1n1p1", mode=CacheMode.WRITEBACK)
    backend.attach_cache(payload)

    st = backend.get_cache_status("md0")
    assert st is not None
    assert st.mode == CacheMode.WRITEBACK


def test_attach_duplicate_array_raises(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    with pytest.raises(ValueError, match="already has an SSD cache"):
        backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme2n1p1"))


def test_attach_duplicate_device_raises(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    with pytest.raises(ValueError, match="already in use"):
        backend.attach_cache(CacheAttachRequest(array="md1", cache_device="nvme1n1p1"))


def test_attach_increments_bcache_counter(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))
    backend.attach_cache(CacheAttachRequest(array="md1", cache_device="nvme2n1p1"))

    st0 = backend.get_cache_status("md0")
    st1 = backend.get_cache_status("md1")
    assert st0 is not None and st0.bcache_device == "bcache0"
    assert st1 is not None and st1.bcache_device == "bcache1"


# ---------------------------------------------------------------------------
# Detach
# ---------------------------------------------------------------------------

def test_detach_cache_success(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))
    resp = backend.detach_cache(CacheDetachRequest(array="md0"))

    assert "detached" in resp.message.lower()
    assert backend.get_cache_status("md0") is None
    assert backend.get_all_cache_statuses() == []


def test_detach_nonexistent_raises(backend: DevSsdCacheBackend):
    with pytest.raises(ValueError, match="No SSD cache attached"):
        backend.detach_cache(CacheDetachRequest(array="md0"))


def test_detach_dirty_data_without_force_raises(backend: DevSsdCacheBackend):
    backend.attach_cache(
        CacheAttachRequest(array="md0", cache_device="nvme1n1p1", mode=CacheMode.WRITEBACK)
    )
    # Simulate dirty data
    backend._caches["md0"].dirty_data_bytes = 1024 * 1024

    with pytest.raises(ValueError, match="dirty data"):
        backend.detach_cache(CacheDetachRequest(array="md0", force=False))


def test_detach_dirty_data_with_force_succeeds(backend: DevSsdCacheBackend):
    backend.attach_cache(
        CacheAttachRequest(array="md0", cache_device="nvme1n1p1", mode=CacheMode.WRITEBACK)
    )
    backend._caches["md0"].dirty_data_bytes = 1024 * 1024

    resp = backend.detach_cache(CacheDetachRequest(array="md0", force=True))
    assert "detached" in resp.message.lower()
    assert backend.get_cache_status("md0") is None


# ---------------------------------------------------------------------------
# Configure
# ---------------------------------------------------------------------------

def test_configure_mode(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    resp = backend.configure_cache(CacheConfigureRequest(array="md0", mode=CacheMode.WRITEBACK))
    assert "mode=writeback" in resp.message

    st = backend.get_cache_status("md0")
    assert st is not None and st.mode == CacheMode.WRITEBACK


def test_configure_sequential_cutoff(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    resp = backend.configure_cache(
        CacheConfigureRequest(array="md0", sequential_cutoff_bytes=8 * 1024 * 1024)
    )
    assert "sequential_cutoff" in resp.message

    st = backend.get_cache_status("md0")
    assert st is not None and st.sequential_cutoff_bytes == 8 * 1024 * 1024


def test_configure_multiple_changes(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    resp = backend.configure_cache(
        CacheConfigureRequest(
            array="md0",
            mode=CacheMode.WRITEAROUND,
            sequential_cutoff_bytes=2 * 1024 * 1024,
        )
    )
    assert "mode=writearound" in resp.message
    assert "sequential_cutoff" in resp.message


def test_configure_no_changes_raises(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    with pytest.raises(ValueError, match="No configuration changes"):
        backend.configure_cache(CacheConfigureRequest(array="md0"))


def test_configure_nonexistent_raises(backend: DevSsdCacheBackend):
    with pytest.raises(ValueError, match="No SSD cache attached"):
        backend.configure_cache(CacheConfigureRequest(array="md0", mode=CacheMode.WRITEBACK))


# ---------------------------------------------------------------------------
# External bitmap
# ---------------------------------------------------------------------------

def test_set_external_bitmap(backend: DevSsdCacheBackend):
    resp = backend.set_external_bitmap(ExternalBitmapRequest(array="md0", ssd_partition="nvme1n1p2"))
    assert "bitmap" in resp.message.lower()
    assert "md0" in resp.message


# ---------------------------------------------------------------------------
# Simulate IO & hit rate
# ---------------------------------------------------------------------------

def test_simulate_io_hit_rate(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))

    # Before IO — no hit rate
    st = backend.get_cache_status("md0")
    assert st is not None and st.hit_rate_percent is None

    # Simulate IO
    backend._simulate_io("md0", hits=80, misses=20)

    st = backend.get_cache_status("md0")
    assert st is not None
    assert st.hit_rate_percent == pytest.approx(80.0, rel=0.01)
    assert st.cache_used_bytes > 0


def test_simulate_io_nonexistent_array_noop(backend: DevSsdCacheBackend):
    # Should not raise
    backend._simulate_io("nonexistent", hits=100, misses=50)


# ---------------------------------------------------------------------------
# Cache devices / cached arrays helpers
# ---------------------------------------------------------------------------

def test_get_cache_devices_and_cached_arrays(backend: DevSsdCacheBackend):
    backend.attach_cache(CacheAttachRequest(array="md0", cache_device="nvme1n1p1"))
    backend.attach_cache(CacheAttachRequest(array="md1", cache_device="nvme2n1p1"))

    assert backend.get_cache_devices() == {"nvme1n1p1", "nvme2n1p1"}
    assert backend.get_cached_arrays() == {"md0", "md1"}


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def test_select_backend_dev_mode(monkeypatch):
    monkeypatch.setattr(config.settings, "ssd_cache_force_dev_backend", True)
    backend = _select_backend()
    assert isinstance(backend, DevSsdCacheBackend)


def test_select_backend_disabled(monkeypatch):
    monkeypatch.setattr(config.settings, "ssd_cache_enabled", False)
    backend = _select_backend()
    assert isinstance(backend, DevSsdCacheBackend)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_cache_mode_enum():
    assert CacheMode.WRITETHROUGH.value == "writethrough"
    assert CacheMode.WRITEBACK.value == "writeback"
    assert CacheMode.WRITEAROUND.value == "writearound"
    assert CacheMode.NONE.value == "none"


def test_cache_status_defaults():
    st = CacheStatus(
        array_name="md0",
        cache_device="nvme1n1p1",
        mode=CacheMode.WRITETHROUGH,
        state="running",
    )
    assert st.bcache_device is None
    assert st.hit_rate_percent is None
    assert st.dirty_data_bytes == 0
    assert st.cache_size_bytes == 0
    assert st.cache_used_bytes == 0
    assert st.sequential_cutoff_bytes == 4 * 1024 * 1024


def test_cache_attach_request_defaults():
    req = CacheAttachRequest(array="md0", cache_device="nvme1n1p1")
    assert req.mode == CacheMode.WRITETHROUGH


def test_cache_detach_request_defaults():
    req = CacheDetachRequest(array="md0")
    assert req.force is False


def test_cache_configure_request_nullable():
    req = CacheConfigureRequest(array="md0")
    assert req.mode is None
    assert req.sequential_cutoff_bytes is None


# ---------------------------------------------------------------------------
# Two-step confirmation
# ---------------------------------------------------------------------------

def test_confirmation_token_roundtrip():
    import app.services.hardware.ssd_cache as ssd_mod
    _confirmations.clear()
    # Reset module-level backend so previous tests don't leave stale caches
    ssd_mod._backend = DevSsdCacheBackend()

    payload = CacheAttachRequest(array="md0", cache_device="nvme1n1p1")
    result = request_cache_confirmation("attach_cache", payload, ttl_seconds=3600)

    assert "token" in result
    assert "expires_at" in result
    assert len(_confirmations) == 1

    # Execute — should delegate to attach_cache on the module-level backend
    resp = execute_cache_confirmation(result["token"])
    assert "attached" in resp.message.lower() or "DEV MODE" in resp.message

    # Token consumed
    assert len(_confirmations) == 0


def test_confirmation_invalid_token():
    _confirmations.clear()

    with pytest.raises(KeyError, match="Invalid confirmation token"):
        execute_cache_confirmation("nonexistent-token")


def test_confirmation_expired_token(monkeypatch):
    import time as time_mod
    import app.services.hardware.ssd_cache as ssd_mod

    _confirmations.clear()
    ssd_mod._backend = DevSsdCacheBackend()

    # Freeze time during request_cache_confirmation
    real_time = time_mod.time

    payload = CacheAttachRequest(array="md0", cache_device="nvme1n1p1")
    result = request_cache_confirmation("attach_cache", payload, ttl_seconds=10)

    # Now advance time past the expiration
    monkeypatch.setattr(time_mod, "time", lambda: real_time() + 20)

    with pytest.raises(KeyError, match="expired"):
        execute_cache_confirmation(result["token"])
