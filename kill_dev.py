"""Kill all running BaluHost development processes (backend and frontend).

Usage:
    Windows: python kill_dev.py
    Linux:   python3 kill_dev.py

This script terminates all uvicorn (backend) and vite/npm (frontend) processes
gracefully with SIGTERM, then forces SIGKILL after a grace period if needed.

Platform Support:
    - Windows: Uses taskkill command
    - Linux/Debian: Uses pkill/pgrep or direct process signals
    - macOS: Uses pkill/pgrep or direct process signals
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


def kill_windows_processes(patterns: List[str], force: bool = False) -> None:
    """Kill processes on Windows using taskkill."""
    for pattern in patterns:
        print(f"[info] Terminating Windows processes matching: {pattern}")
        try:
            # First try graceful termination
            if not force:
                subprocess.run(
                    ["taskkill", "/F", "/IM", f"{pattern}.exe"],
                    check=False,
                    capture_output=True
                )
            else:
                # Force kill
                subprocess.run(
                    ["taskkill", "/F", "/IM", f"{pattern}.exe"],
                    check=False,
                    capture_output=True
                )
        except Exception as e:
            print(f"[debug] Error terminating {pattern}: {e}")


def kill_unix_processes(patterns: List[str], grace_seconds: int = 5) -> None:
    """Kill processes on Unix/Linux using pkill/pgrep or direct signals.

    Args:
        patterns: List of command patterns to match (used with pgrep -f)
        grace_seconds: Seconds to wait before forcing SIGKILL
    """
    pgrep = shutil.which("pgrep")
    pkill = shutil.which("pkill")

    def _run_pgrep(pattern: str) -> List[int]:
        """Get PIDs matching pattern."""
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
            return [int(x) for x in res.stdout.split() if x.strip()]
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

            print(f"[info] Terminating {len(pids)} process(es) matching: {pat}")
            if pkill:
                subprocess.run([pkill, "-f", "-TERM", pat], check=False)
            else:
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        print(f"[warning] Permission denied for PID {pid}")
                    except Exception as e:
                        print(f"[debug] Error killing PID {pid}: {e}")
        except Exception as e:
            print(f"[debug] Error while terminating pattern {pat}: {e}")

    # Wait grace period
    if grace_seconds > 0:
        print(f"[info] Waiting {grace_seconds} seconds for processes to terminate...")
        time.sleep(grace_seconds)

    # Phase 2: Force kill remaining processes with SIGKILL
    print("[info] Force killing any remaining processes (SIGKILL)...")
    remaining_count = 0
    for pat in patterns:
        try:
            pids = _run_pgrep(pat)
            if not pids:
                continue

            remaining_count += len(pids)
            print(f"[warning] Force killing {len(pids)} process(es) matching: {pat}")
            if pkill:
                subprocess.run([pkill, "-f", "-KILL", pat], check=False)
            else:
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        print(f"[warning] Permission denied for PID {pid}")
                    except Exception as e:
                        print(f"[debug] Error killing PID {pid}: {e}")
        except Exception as e:
            print(f"[debug] Error while forcing kill for pattern {pat}: {e}")

    if remaining_count == 0:
        print("[success] All processes terminated gracefully")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("BaluHost Development Process Killer")
    print("=" * 60)

    if os.name == "nt":
        # Windows
        print("[info] Platform: Windows")
        patterns = ["python", "node", "uvicorn"]
        print("[warning] Terminating all Python and Node processes!")
        print("[warning] This may affect other running Python/Node applications.")

        # Give user a chance to cancel
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n[info] Cancelled by user")
            return 0

        kill_windows_processes(patterns, force=False)
        time.sleep(2)
        kill_windows_processes(patterns, force=True)
        print("[success] Windows processes terminated")

    else:
        # Unix/Linux/macOS
        print(f"[info] Platform: {sys.platform}")

        # More specific patterns to avoid killing unrelated processes
        kill_patterns = [
            "uvicorn app.main:app",           # Backend server
            "vite",                            # Frontend dev server
            "npm run dev",                     # Frontend npm command
            "node.*vite",                      # Node running vite
            "node.*@vite",                     # Alternative vite pattern
        ]

        try:
            kill_unix_processes(kill_patterns, grace_seconds=3)
            print("[success] All BaluHost processes terminated")
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
