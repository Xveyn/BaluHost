"""Kill all running BaluHost development processes (backend and frontend).

Usage:
    Windows: python kill_dev.py
    Linux:   python3 kill_dev.py

This script terminates the uvicorn (backend) and vite/npm (frontend)
processes of THIS checkout gracefully with SIGTERM, then forces SIGKILL after a
grace period if needed. Processes of another checkout or of the production
install (/opt/baluhost) are left alone (#763).

Platform Support:
    - Windows: Uses taskkill command. It matches by image name and therefore
      ends EVERY python.exe/node.exe - the script warns before doing so.
    - Linux/Debian: Scans /proc (see dev_process_cleanup.py)
    - macOS: No /proc, so the cleanup is skipped with a message
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List

from dev_process_cleanup import terminate_owned_processes

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
            terminate_owned_processes(kill_patterns, ROOT_DIR, grace_seconds=3)
            print("[success] Done")
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
