"""Prove the cross-process bus works against the real database.

CI runs SQLite only, so no test touches the LISTEN path. This script is that
gap's counterweight, in two phases:

1. A listener in a child process receives an envelope published by the parent.
2. The parent kills the listener's Postgres session and publishes again. This
   is the phase worth having: the reconnect path is where this class fails, and
   a unit test cannot see it, because a fake connection's fileno() does not
   raise the way psycopg2's does once the connection is gone.

Run on the box:

    cd <worktree>/backend
    /opt/baluhost/backend/.venv/bin/python scripts/debug/verify_ws_bus.py

It only ever kills the session it created itself, by pid. Exit code 0 means
both phases delivered.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MARKER = "verify-ws-bus"
TIMEOUT_SECONDS = 10.0
PROD_ENV_FILE = Path("/opt/baluhost/.env.production")


def _ensure_dsn() -> None:
    """Put DATABASE_URL into the environment before anything imports settings.

    Settings read `.env`, not `.env.production` (config.py:282), so running this
    by hand against the production database needs the value supplied. Read from
    the file rather than passed on the command line — a DSN carries a password,
    and a command line is readable in ps.
    """
    if os.environ.get("DATABASE_URL"):
        return
    if not PROD_ENV_FILE.exists():
        return
    for line in PROD_ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("DATABASE_URL="):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip("\"'")
            return


def _listener(
    ready: multiprocessing.Event,
    got: multiprocessing.Queue,
    pids: multiprocessing.Queue,
) -> None:
    """Child process: listen, report its backend pid and every matching envelope."""

    async def main() -> None:
        from app.services.ws_bus import build_bus

        async def deliver(env) -> None:
            if env.msg_type == MARKER:
                got.put(env.payload)

        bus = build_bus()
        await bus.start(deliver)
        # The listener connection's server-side pid, so the parent can kill
        # exactly this session and nothing else.
        with bus._conn.cursor() as cur:
            cur.execute("SELECT pg_backend_pid()")
            pids.put(cur.fetchone()[0])
        ready.set()
        await asyncio.sleep(TIMEOUT_SECONDS * 3)
        await bus.stop()

    asyncio.run(main())


def _terminate(pid: int) -> None:
    """Kill one Postgres session — the listener's, by pid."""
    from app.core.database import engine

    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT pg_terminate_backend(%s)", (pid,))
        conn.commit()


async def _publish(phase: str) -> None:
    from app.services.ws_bus import WsEnvelope, build_bus

    bus = build_bus()
    await bus.publish(
        WsEnvelope(
            kind="all",
            msg_type=MARKER,
            payload={"phase": phase, "sent_at": time.time()},
        )
    )


def main() -> int:
    _ensure_dsn()

    import app.services.ws_bus as ws_bus_module
    from app.core.database import DATABASE_URL

    # Say which copy of the code is under test — running this from the
    # production working directory against a worktree checkout is exactly the
    # situation where a PASS could mean nothing.
    print(f"using {ws_bus_module.__file__}")
    # Also name the database: /opt/baluhost/backend/.env holds a DIFFERENT DSN
    # than .env.production, so a PASS against the wrong database would be
    # indistinguishable otherwise.
    print(f"database {DATABASE_URL.rsplit('@', 1)[-1]}")

    if not DATABASE_URL.startswith("postgresql"):
        print(f"FAIL: needs PostgreSQL, got {DATABASE_URL.split(':')[0]}")
        return 1

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    got: multiprocessing.Queue = ctx.Queue()
    pids: multiprocessing.Queue = ctx.Queue()
    child = ctx.Process(target=_listener, args=(ready, got, pids), daemon=True)
    child.start()

    try:
        if not ready.wait(timeout=TIMEOUT_SECONDS):
            print("FAIL: listener process never became ready")
            return 1

        # ---- phase 1: does it work at all? ----
        started = time.perf_counter()
        asyncio.run(_publish("phase1"))
        try:
            payload = got.get(timeout=TIMEOUT_SECONDS)
        except Exception:
            print("FAIL phase 1: envelope never arrived in the other process")
            return 1
        print(
            f"PASS phase 1: delivered cross-process in "
            f"{(time.perf_counter() - started) * 1000:.1f} ms (payload={payload})"
        )

        # ---- phase 2: does it survive losing the connection? ----
        # This is the phase that matters. A listener whose reader was not
        # unregistered on loss reconnects, logs success, and never delivers
        # again — and no unit test can see it, because a fake connection's
        # fileno() does not raise the way psycopg2's does.
        listener_pid = pids.get(timeout=TIMEOUT_SECONDS)
        print(f"terminating the listener's backend pid {listener_pid} ...")
        _terminate(listener_pid)

        deadline = time.monotonic() + TIMEOUT_SECONDS * 2
        while time.monotonic() < deadline:
            asyncio.run(_publish("phase2"))
            try:
                payload = got.get(timeout=2.0)
            except Exception:
                continue
            print(f"PASS phase 2: delivered again after reconnect (payload={payload})")
            return 0

        print("FAIL phase 2: nothing arrived after the connection was killed")
        print("  -> the listener reconnected but its fd is not being watched")
        return 1
    finally:
        child.terminate()
        child.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
