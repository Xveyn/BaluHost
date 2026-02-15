import pytest

from app.services import raid as raid_service


@pytest.mark.skipif(not isinstance(raid_service._backend, raid_service.DevRaidBackend), reason="Dev backend not active")
def test_scrub_now_for_array():
    status = raid_service.get_status()
    assert status.arrays, "No dev arrays available"
    array_name = status.arrays[0].name

    resp = raid_service.scrub_now(array_name)
    assert isinstance(resp.message, str)

    status_after = raid_service.get_status()
    arr = next((a for a in status_after.arrays if a.name == array_name), None)
    assert arr is not None
    # Dev backend sets sync_action to 'check' and resync_progress to 0.0 when triggered
    assert arr.sync_action == "check" or arr.resync_progress == 0.0


@pytest.mark.skipif(not isinstance(raid_service._backend, raid_service.DevRaidBackend), reason="Dev backend not active")
def test_scrub_now_all_arrays():
    status = raid_service.get_status()
    assert status.arrays

    resp = raid_service.scrub_now(None)
    assert isinstance(resp.message, str)
    # ensure each array has had its sync_action set (dev backend)
    status_after = raid_service.get_status()
    for arr in status_after.arrays:
        assert arr.sync_action == "check" or arr.resync_progress == 0.0
