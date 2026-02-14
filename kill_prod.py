"""Kill all running BaluHost production processes.

Usage:
    Linux: python3 kill_prod.py
    With sudo (for systemd services): sudo python3 kill_prod.py

This script terminates all uvicorn/gunicorn (backend) production processes
gracefully with SIGTERM, then forces SIGKILL after a grace period if needed.

Platform Support:
    - Linux/Debian: Uses pkill/pgrep or direct process signals
    - macOS: Uses pkill/pgrep or direct process signals
    - Windows: Not supported for production
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parent


def kill_unix_processes(patterns: List[str], grace_seconds: int = 5) -> int:
    """Kill processes on Unix/Linux using pkill/pgrep or direct signals.

    Args:
        patterns: List of command patterns to match (used with pgrep -f)
        grace_seconds: Seconds to wait before forcing SIGKILL

    Returns:
        Number of processes that were killed
    """
    pgrep = shutil.which("pgrep")
    pkill = shutil.which("pkill")

    total_killed = 0

    def _run_pgrep(pattern: str) -> List[int]:
        """Get PIDs matching pattern, excluding current process."""
        if not pgrep:
            return []
        try:
            res = subprocess.run(
                [pgrep, "-f", pattern],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode != 0 or not res.stdout:
                return []
            pids = [int(x) for x in res.stdout.split() if x.strip()]
            # Exclude current process
            current_pid = os.getpid()
            return [pid for pid in pids if pid != current_pid]
        except Exception:
            return []

    # Phase 1: Graceful termination with SIGTERM
    print("[info] Attempting graceful termination (SIGTERM)...")
    for pat in patterns:
        try:
            pids = _run_pgrep(pat)
            if not pids:
                print(f"[info] No processes found matching: {pat}")
                continue

            total_killed += len(pids)
            print(f"[info] Terminating {len(pids)} process(es) matching: {pat}")
            print(f"       PIDs: {', '.join(str(p) for p in pids)}")

            if pkill:
                subprocess.run([pkill, "-f", "-TERM", pat], check=False)
            else:
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        print(f"[warning] Permission denied for PID {pid} - try with sudo")
                    except Exception as e:
                        print(f"[debug] Error killing PID {pid}: {e}")
        except Exception as e:
            print(f"[debug] Error while terminating pattern {pat}: {e}")

    if total_killed == 0:
        return 0

    # Wait grace period
    if grace_seconds > 0:
        print(f"[info] Waiting {grace_seconds} seconds for processes to terminate...")
        time.sleep(grace_seconds)

    # Phase 2: Force kill remaining processes with SIGKILL
    print("[info] Checking for remaining processes...")
    remaining_count = 0
    for pat in patterns:
        try:
            pids = _run_pgrep(pat)
            if not pids:
                continue

            remaining_count += len(pids)
            print(f"[warning] Force killing {len(pids)} process(es) matching: {pat}")
            print(f"          PIDs: {', '.join(str(p) for p in pids)}")

            if pkill:
                subprocess.run([pkill, "-f", "-KILL", pat], check=False)
            else:
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        print(f"[warning] Permission denied for PID {pid} - try with sudo")
                    except Exception as e:
                        print(f"[debug] Error killing PID {pid}: {e}")
        except Exception as e:
            print(f"[debug] Error while forcing kill for pattern {pat}: {e}")

    if remaining_count == 0:
        print("[success] All processes terminated gracefully")

    return total_killed


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
        killed_count = kill_unix_processes(kill_patterns, grace_seconds=5)

        if killed_count == 0 and not systemd_stopped:
            print("\n[info] No BaluHost production processes were running")
        else:
            print(f"\n[success] BaluHost production processes terminated")

        # Final status check
        print("\n[phase 3] Verifying cleanup...")
        time.sleep(1)

        pgrep = shutil.which("pgrep")
        if pgrep:
            remaining = False
            for pat in ["uvicorn.*app.main", "gunicorn.*app.main"]:
                result = subprocess.run(
                    [pgrep, "-f", pat],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    remaining = True
                    break

            if remaining:
                print("[warning] Some processes may still be running")
                print("         Try: sudo python3 kill_prod.py")
            else:
                print("[success] All BaluHost processes confirmed stopped")

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
