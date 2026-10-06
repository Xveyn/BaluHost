"""Kill all running BaluHost production processes.

Usage:
    Linux: python3 kill_prod.py
    With sudo (for systemd services): sudo python3 kill_prod.py

This script stops the BaluHost systemd services, then terminates the
uvicorn/gunicorn (backend) and worker processes of THIS install gracefully with
SIGTERM, forcing SIGKILL after a grace period if needed. Processes of another
checkout (e.g. a dev instance) are left alone (#763). The systemd services are
stopped by name, whichever install they belong to.

Platform Support:
    - Linux/Debian: Scans /proc (see dev_process_cleanup.py)
    - macOS: No /proc, so the process cleanup is skipped with a message
    - Windows: Not supported for production
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dev_process_cleanup import find_owned_processes, terminate_owned_processes

ROOT_DIR = Path(__file__).resolve().parent


def stop_systemd_services() -> bool:
    """Attempt to stop BaluHost systemd services if they exist.

    Returns:
        True if any services were stopped
    """
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False

    services = ["baluhost-backend", "baluhost-scheduler", "baluhost-webdav", "baluhost-frontend", "baluhost"]
    stopped_any = False

    for service in services:
        try:
            # Check if service exists
            result = subprocess.run(
                [systemctl, "is-active", service],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:  # Service is active
                print(f"[info] Stopping systemd service: {service}")
                stop_result = subprocess.run(
                    [systemctl, "stop", service],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if stop_result.returncode == 0:
                    print(f"[success] Stopped {service}")
                    stopped_any = True
                else:
                    print(f"[warning] Failed to stop {service}: {stop_result.stderr.strip()}")
                    if "Access denied" in stop_result.stderr or "Permission" in stop_result.stderr:
                        print(f"         Try: sudo systemctl stop {service}")
        except Exception as e:
            print(f"[debug] Error checking service {service}: {e}")

    return stopped_any


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("BaluHost Production Process Killer")
    print("=" * 60)

    if os.name == "nt":
        print("[error] Production mode is not supported on Windows")
        return 1

    print(f"[info] Platform: {sys.platform}")
    print(f"[info] Running as: {os.getenv('USER', 'unknown')}")

    # Phase 1: Try to stop systemd services first
    print("\n[phase 1] Checking for systemd services...")
    systemd_stopped = stop_systemd_services()

    if systemd_stopped:
        print("[info] Systemd services stopped, waiting for cleanup...")
        time.sleep(2)

    # Phase 2: Kill any remaining processes
    print("\n[phase 2] Killing remaining processes...")

    # Production-specific patterns
    kill_patterns = [
        # Backend patterns
        "uvicorn app.main:app",            # Direct uvicorn
        "uvicorn.*app.main:app",           # Uvicorn with args
        "gunicorn.*app.main:app",          # Gunicorn WSGI server
        "python.*uvicorn.*app.main",       # Python running uvicorn
        # Scheduler worker
        "python.*scheduler_worker",        # Scheduler worker process
        # WebDAV worker
        "python.*webdav_worker",           # WebDAV server process
        # Frontend patterns (in case preview server is running)
        "npm run preview",                 # Production preview
        "vite preview",                    # Vite preview mode
        "node.*vite.*preview",             # Node running vite preview
    ]

    try:
        killed_count = terminate_owned_processes(kill_patterns, ROOT_DIR, grace_seconds=5)

        if killed_count == 0 and not systemd_stopped:
            print("\n[info] No BaluHost production processes were running")
        else:
            print(f"\n[success] BaluHost production processes terminated")

        # Final status check
        print("\n[phase 3] Verifying cleanup...")
        time.sleep(1)

        remaining = find_owned_processes(
            ["uvicorn.*app.main", "gunicorn.*app.main"], ROOT_DIR
        )
        if remaining:
            print("[warning] Some processes may still be running")
            print("         Try: sudo python3 kill_prod.py")
        else:
            print("[success] All BaluHost processes of this install confirmed stopped")

    except Exception as e:
        print(f"[error] Failed to kill processes: {e}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[info] Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"[error] Unexpected error: {e}")
        sys.exit(1)
