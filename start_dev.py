"""Convenience launcher that starts the mocked Python backend and the Vite frontend.

Usage:
    python start_dev.py

Press Ctrl+C to stop both processes. The script ensures that the backend virtual
environment exists and uses it to run Uvicorn. Run it from the repository root.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
CLIENT_DIR = ROOT_DIR / "client"

BACKEND_VENV = BACKEND_DIR / (".venv\\Scripts\\python.exe" if os.name == "nt" else ".venv/bin/python")

ProcessInfo = Tuple[str, subprocess.Popen]


def resolve_backend_python() -> str:
    if BACKEND_VENV.exists():
        return str(BACKEND_VENV)
    if BACKEND_VENV.with_name("python").exists():  # Windows fallback
        return str(BACKEND_VENV.with_name("python"))
    if BACKEND_VENV.with_name("python.exe").exists():
        return str(BACKEND_VENV.with_name("python.exe"))
    # Fallback to current interpreter; user must ensure packages are available
    return sys.executable


def resolve_npm_binary() -> str:
    candidates = ["npm.cmd", "npm.exe", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError(
        "npm executable not found. Please install Node.js and ensure npm is on PATH."
    )


def start_process(name: str, cmd: List[str], cwd: Path) -> subprocess.Popen:
    print(f"[start] {name}: {' '.join(cmd)} (cwd={cwd})")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(cmd, cwd=cwd, creationflags=creationflags)


def terminate_processes(processes: List[ProcessInfo]) -> None:
    for name, proc in processes:
        if proc.poll() is not None:
            continue
        print(f"[stop] {name}")
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def main() -> int:
    processes: List[ProcessInfo] = []
    backend_python = resolve_backend_python()

    exit_codes: Dict[str, int] = {}

    try:
        # Ensure development-specific environment toggles are present during local runs
        os.environ.setdefault("NAS_MODE", "dev")
        os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

        npm_binary = resolve_npm_binary()

        commands: Dict[str, Dict[str, object]] = {
            "backend": {
                "cmd": [
                    backend_python,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--reload",
                    "--port",
                    "3001",
                ],
                "cwd": BACKEND_DIR,
            },
            "frontend": {
                "cmd": [npm_binary, "run", "dev"],
                "cwd": CLIENT_DIR,
            },
        }

        for name, config in commands.items():
            proc = start_process(name, config["cmd"], config["cwd"])  # type: ignore[arg-type]
            processes.append((name, proc))

        while True:
            loop_break = False
            for name, proc in processes:
                retcode = proc.poll()
                if retcode is not None and name not in exit_codes:
                    exit_codes[name] = retcode
                    print(f"[info] {name} exited with code {retcode}")
                    loop_break = True
                    break
            if loop_break:
                break
            time.sleep(0.5)
        return max(exit_codes.values()) if exit_codes else 0
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[info] Ctrl+C received, shutting down...")
        return max(exit_codes.values()) if exit_codes else 0
    finally:
        terminate_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
