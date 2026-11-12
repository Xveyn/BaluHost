"""The command-queue poll loops must not query the database on the event loop.

`claim_pending()` opens a `SessionLocal()` and runs a SELECT. Both the CPU and
the GPU poll loop call it every 0.5 s on the primary worker; py-spy there
(2026-11-11) put ~4000 of ~9400 non-idle loop samples into those two calls
(#797). A slow connect or pool ping then stalls every coroutine of the worker.

Since #313 both queues are instances of one `DbCommandQueue`; these tests pin
the guarantee on the two real instances, `test_db_command_queue.py` covers
the class itself.
"""
import threading
from unittest.mock import MagicMock

import pytest

from app.services.power import command_queue as cpu_queue
from app.services.power.gpu import command_queue as gpu_queue

QUEUES = [
    pytest.param(cpu_queue.QUEUE, id="cpu"),
    pytest.param(gpu_queue.QUEUE, id="gpu"),
]


def _recording_claim(seen: list, result=None):
    def fake():
        seen.append(threading.current_thread())
        return result

    return fake


@pytest.mark.asyncio
@pytest.mark.parametrize("queue", QUEUES)
async def test_claim_pending_runs_in_a_worker_thread(queue, monkeypatch):
    seen: list = []
    monkeypatch.setattr(queue, "claim_pending", _recording_claim(seen))

    processed = await queue.process_one_pending(MagicMock())

    assert processed is False
    assert len(seen) == 1
    assert seen[0] is not threading.main_thread()


@pytest.mark.asyncio
@pytest.mark.parametrize("queue", QUEUES)
async def test_claimed_command_is_still_dispatched(queue, monkeypatch):
    """Off-loop claiming must not change what happens with the claimed row."""
    seen: list = []
    finished: list = []
    # An unknown command is reported as failed through `finish` — enough to
    # prove the claimed tuple reaches the dispatch code unchanged.
    monkeypatch.setattr(
        queue, "claim_pending", _recording_claim(seen, (42, "no_such_command", None))
    )
    monkeypatch.setattr(
        queue, "finish", lambda command_id, *, success, error: finished.append(
            (command_id, success)
        )
    )

    processed = await queue.process_one_pending(MagicMock())

    assert processed is True
    assert finished == [(42, False)]
