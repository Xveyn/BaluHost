#!/usr/bin/env python3
"""
BaluHost Monitoring Worker — standalone process for system monitoring services.

Runs telemetry, disk I/O, monitoring orchestrator, and power monitor in a
dedicated process, communicating with web workers via /dev/shm/baluhost/.

Usage:
    python scripts/monitoring_worker.py
"""

import asyncio
import logging
import os
import signal
import sys

# Ensure the backend package is importable (parent of scripts/ = backend/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def async_main() -> int:
    # Configure structured logging (same as web process)
    from app.core.logging_config import setup_logging
    setup_logging()

    logger = logging.getLogger("monitoring_worker")
    logger.info("BaluHost Monitoring Worker starting...")

    # Initialize database (create tables if missing)
    from app.core.database import init_db, SessionLocal
    init_db()

    # Initialize Firebase so threshold-triggered push notifications
    # (temperature, disk space) can be sent from this process.
    from app.services.notifications.firebase import FirebaseService
    FirebaseService.initialize()

    # Initialize the EventEmitter with a DB session factory so emit_sync
    # calls (e.g. temperature/disk space alerts) can create DB records.
    from app.services.notifications.events import init_event_emitter
    init_event_emitter(SessionLocal)

    # Clean up any stale SHM files from a previous run
    from app.services.monitoring.shm import cleanup_shm
    cleanup_shm()

    # Create and start the worker
    from app.services.monitoring.worker_service import MonitoringWorker
    worker = MonitoringWorker()

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating shutdown...", sig_name)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        await worker.start(SessionLocal)

        # Run loop until shutdown signal
        loop_task = asyncio.create_task(worker.run_loop())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [loop_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
    except Exception:
        logger.exception("Monitoring worker crashed")
        return 1
    finally:
        await worker.shutdown()

    logger.info("Monitoring worker exited cleanly")
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
