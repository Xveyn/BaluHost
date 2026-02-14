#!/usr/bin/env python3
"""
BaluHost Scheduler Worker — standalone process for running all scheduled jobs.

This process owns all APScheduler jobs (backup, RAID scrub, SMART scan,
sync check, notification check, upload cleanup) so that heavy I/O does
not block the main Uvicorn web worker.

IPC is done via the shared database:
  - Web API creates SchedulerExecution rows with status='requested'
  - This worker polls for them and executes the corresponding job
  - Heartbeat + state written to scheduler_state table

Usage:
    python scripts/scheduler_worker.py
"""

import logging
import os
import signal
import sys

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    # Configure structured logging (same as web process)
    from app.core.logging_config import setup_logging
    setup_logging()

    logger = logging.getLogger("scheduler_worker")
    logger.info("BaluHost Scheduler Worker starting...")

    # Initialize database (create tables if missing)
    from app.core.database import init_db
    init_db()

    # Create and start the worker
    from app.services.scheduler_worker_service import SchedulerWorker
    worker = SchedulerWorker()

    # Handle shutdown signals
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating shutdown...", sig_name)
        worker.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        worker.start()
        worker.run_loop()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
    except Exception:
        logger.exception("Scheduler worker crashed")
        return 1
    finally:
        if worker.running:
            worker.shutdown()

    logger.info("Scheduler worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
