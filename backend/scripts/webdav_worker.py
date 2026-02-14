#!/usr/bin/env python3
"""
BaluHost WebDAV Worker — standalone process for the WebDAV server.

Runs the cheroot WSGI server hosting the WsgiDAV application with
BaluHost authentication and per-user storage isolation.

IPC is done via the shared database:
  - Worker writes webdav_state row (heartbeat, port, SSL, PID)
  - Web API reads it for status display

Usage:
    python scripts/webdav_worker.py
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

    logger = logging.getLogger("webdav_worker")
    logger.info("BaluHost WebDAV Worker starting...")

    # Initialize database (create tables if missing)
    from app.core.database import init_db
    init_db()

    # Create and start the worker
    from app.services.webdav_service import WebdavWorker
    worker = WebdavWorker()

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
        logger.exception("WebDAV worker crashed")
        return 1
    finally:
        if worker.running:
            worker.shutdown()

    logger.info("WebDAV worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
