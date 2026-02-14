"""Production launcher for BaluHost backend and frontend.

Usage:
    Linux: python3 start_prod.py

Press Ctrl+C to stop both processes. The script ensures that the backend virtual
environment exists and uses it to run Uvicorn. Run it from the repository root.

Production Mode:
    - Uses NAS_MODE=prod (real RAID, SMART, system commands)
    - No auto-reload (stable process)
    - Multiple workers for better performance
    - Expects PostgreSQL database (configure via DATABASE_URL)
    - Kills existing processes before starting

Requirements:
    - Linux with systemd (recommended)
    - PostgreSQL database configured
    - Backend virtual environment with dependencies installed
    - Frontend built (npm run build) or running separately via nginx
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Optional

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
CLIENT_DIR = ROOT_DIR / "client"

# Load .env file from backend directory
def load_env_file(env_path: Path) -> Dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars = {}
    if not env_path.exists():
        return env_vars

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Parse KEY=value
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                env_vars[key] = value
    return env_vars

# Load environment files into os.environ at startup
# Priority: shell env > .env.production (root) > backend/.env
_backend_env = load_env_file(BACKEND_DIR / ".env")
_prod_env = load_env_file(ROOT_DIR / ".env.production")

# First load backend .env (lowest priority)
for key, value in _backend_env.items():
    if key not in os.environ:
        os.environ[key] = value

# Then load .env.production (higher priority, overwrites backend/.env)
for key, value in _prod_env.items():
    if key not in os.environ:
        os.environ[key] = value

BACKEND_VENV = BACKEND_DIR / ".venv/bin/python"

ProcessInfo = Tuple[str, subprocess.Popen]

# Production configuration
PROD_CONFIG = {
    "backend_port": 8000,
    "backend_host": "127.0.0.1",  # Bind to localhost, nginx handles external
    # Workers: Use 1 for hardware control (PowerManager, FanControl need singleton)
    # Multiple workers would start duplicate hardware controllers
    "workers": 1,
    "frontend_port": 5173,  # Only used if running frontend in dev mode
}


def resolve_backend_python() -> str:
    """Resolve the Python executable for the backend virtual environment.

    Tries in order:
    1. Virtual environment Python (platform-specific path)
    2. python3 in venv (Linux/Debian fallback)
    3. Current Python interpreter (sys.executable)
    """
    if BACKEND_VENV.exists():
        return str(BACKEND_VENV)

    # Linux/Debian: Try python3 in venv
    python3_path = BACKEND_DIR / ".venv" / "bin" / "python3"
    if python3_path.exists():
        return str(python3_path)

    # Fallback to current interpreter; user must ensure packages are available
    print("[warning] Virtual environment not found, using system Python")
    return sys.executable


def resolve_npm_binary() -> Optional[str]:
    """Resolve npm binary, returns None if not found."""
    resolved = shutil.which("npm")
    if resolved:
        return resolved
    return None


def kill_existing_processes(patterns: Iterable[str], grace_seconds: int = 5) -> None:
    """Kill any existing processes matching the given patterns.

    This ensures a clean start by terminating lingering processes from
    previous runs that could cause port conflicts.

    Args:
        patterns: Process patterns to match (passed to pgrep -f)
        grace_seconds: Time to wait before force-killing
    """
    if os.name == "nt":
        print("[warning] Process cleanup not supported on Windows")
        return

    pgrep = shutil.which("pgrep")
    pkill = shutil.which("pkill")

    def _run_pgrep(pattern: str) -> List[int]:
        if not pgrep:
            return []
        try:
            # Exclude our own process
            res = subprocess.run(
                [pgrep, "-f", pattern],
                capture_output=True,
                text=True
            )
            if res.returncode != 0 or not res.stdout:
                return []
            pids = [int(x) for x in res.stdout.split() if x.strip()]
            # Exclude current process
            current_pid = os.getpid()
            return [pid for pid in pids if pid != current_pid]
        except Exception:
            return []

    killed_any = False

    for pat in patterns:
        try:
            pids = _run_pgrep(pat)
            if pids:
                print(f"[cleanup] Found {len(pids)} process(es) matching: {pat}")
                killed_any = True
                if pkill:
                    # Try graceful terminate via pkill
                    subprocess.run([pkill, "-f", "-TERM", pat], check=False)
                else:
                    for pid in pids:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
        except Exception as e:
            print(f"[debug] Error while terminating pattern {pat}: {e}")

    if killed_any:
        print(f"[cleanup] Waiting {grace_seconds}s for graceful shutdown...")
        time.sleep(grace_seconds)

        # Force kill remaining processes
        for pat in patterns:
            try:
                remaining = _run_pgrep(pat)
                if remaining:
                    print(f"[cleanup] Force killing {len(remaining)} remaining process(es) matching: {pat}")
                    if pkill:
                        subprocess.run([pkill, "-f", "-KILL", pat], check=False)
                    else:
                        for pid in remaining:
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
            except Exception as e:
                print(f"[debug] Error while forcing kill for pattern {pat}: {e}")

        # Final wait to ensure ports are released
        time.sleep(1)
    else:
        print("[cleanup] No existing processes found")


def start_process(name: str, cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
    """Start a subprocess with process group handling for clean termination.

    Args:
        name: Display name for logging
        cmd: Command and arguments
        cwd: Working directory
        env: Optional environment variables (merged with current env)
    """
    print(f"[start] {name}: {' '.join(cmd)} (cwd={cwd})")

    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    # Linux/Unix: Use start_new_session for process group
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=process_env,
        start_new_session=True
    )


def terminate_processes(processes: List[ProcessInfo]) -> None:
    """Terminate all running processes gracefully, with fallback to kill.

    On Linux: Terminates entire process group to clean up child processes
    """
    for name, proc in processes:
        if proc.poll() is not None:
            continue
        print(f"[stop] {name}")
        try:
            # Linux: Terminate entire process group to kill child processes
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    # Process already terminated
                    pass
            else:
                proc.terminate()

            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Force kill if graceful termination fails
            print(f"[warning] {name} didn't terminate gracefully, forcing kill")
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
        except Exception as e:
            print(f"[error] Failed to terminate {name}: {e}")
            proc.kill()


def check_prerequisites() -> bool:
    """Check that all prerequisites for production are met."""
    errors = []
    warnings = []

    # Check Linux
    if os.name == "nt":
        errors.append("Production mode requires Linux")

    # Check backend venv
    backend_python = resolve_backend_python()
    if backend_python == sys.executable:
        warnings.append("Backend virtual environment not found")

    # Check for DATABASE_URL (PostgreSQL)
    if not os.environ.get("DATABASE_URL"):
        warnings.append("DATABASE_URL not set - will use SQLite (not recommended for production)")

    # Check for SECRET_KEY
    if not os.environ.get("SECRET_KEY"):
        warnings.append("SECRET_KEY not set - using default (INSECURE for production)")

    # Print results
    if warnings:
        print("\n[warnings]")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\n[errors]")
        for e in errors:
            print(f"  - {e}")
        return False

    return True


def main() -> int:
    processes: List[ProcessInfo] = []
    exit_codes: Dict[str, int] = {}

    print("=" * 60)
    print("BaluHost Production Launcher")
    print("=" * 60)

    # Check prerequisites
    if not check_prerequisites():
        print("\n[error] Prerequisites not met, aborting")
        return 1

    # Kill existing processes first
    print("\n[phase 1] Cleaning up existing processes...")
    kill_patterns = [
        "uvicorn.*app.main:app",
        "gunicorn.*app.main:app",
        "node.*vite",
        "npm run dev",
        "npm run preview",
    ]
    kill_existing_processes(kill_patterns, grace_seconds=3)

    try:
        # Set production environment
        os.environ["NAS_MODE"] = "prod"

        # Ensure /sbin and /usr/sbin are in PATH (needed for mdadm, smartctl, etc.)
        current_path = os.environ.get("PATH", "")
        sbin_paths = ["/sbin", "/usr/sbin"]
        for sbin in sbin_paths:
            if sbin not in current_path:
                current_path = f"{sbin}:{current_path}"
        os.environ["PATH"] = current_path

        # Optional: Set default quota if not configured
        if not os.environ.get("NAS_QUOTA_BYTES"):
            os.environ["NAS_QUOTA_BYTES"] = str(100 * 1024 * 1024 * 1024)  # 100 GB default

        backend_python = resolve_backend_python()

        # Get local IP for display
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "localhost"

        # Backend command - production mode without reload
        backend_cmd = [
            backend_python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host", PROD_CONFIG["backend_host"],
            "--port", str(PROD_CONFIG["backend_port"]),
            "--workers", str(PROD_CONFIG["workers"]),
            "--access-log",
            "--log-level", "info",
        ]

        print(f"\n[phase 2] Starting services...")
        print(f"[info] Backend binding to {PROD_CONFIG['backend_host']}:{PROD_CONFIG['backend_port']}")
        print(f"[info] Workers: {PROD_CONFIG['workers']}")
        print(f"[info] Mode: NAS_MODE=prod")

        # Check if we should also start frontend (not typical for production)
        run_frontend = os.environ.get("PROD_RUN_FRONTEND", "false").lower() == "true"
        frontend_dist = CLIENT_DIR / "dist"
        frontend_built = frontend_dist.exists() and (frontend_dist / "index.html").exists()

        # Scheduler worker runs all APScheduler jobs in a separate process
        scheduler_cmd = [
            backend_python,
            "scripts/scheduler_worker.py",
        ]

        # WebDAV worker runs the cheroot-based WebDAV server in a separate process
        webdav_cmd = [
            backend_python,
            "scripts/webdav_worker.py",
        ]

        commands: Dict[str, Dict[str, object]] = {
            "backend": {
                "cmd": backend_cmd,
                "cwd": BACKEND_DIR,
            },
            "scheduler": {
                "cmd": scheduler_cmd,
                "cwd": BACKEND_DIR,
            },
            "webdav": {
                "cmd": webdav_cmd,
                "cwd": BACKEND_DIR,
            },
        }

        if run_frontend:
            npm_binary = resolve_npm_binary()
            if npm_binary:
                print("[info] PROD_RUN_FRONTEND=true, starting frontend preview server")
                if not frontend_built:
                    print("[warning] client/dist not found - run 'cd client && npm run build' first")
                commands["frontend"] = {
                    "cmd": [npm_binary, "run", "preview"],
                    "cwd": CLIENT_DIR,
                }
            else:
                print("[warning] npm not found, skipping frontend")
        else:
            print("[info] Frontend: nginx mode (PROD_RUN_FRONTEND=false)")
            if frontend_built:
                print(f"[info] Serving via nginx from {frontend_dist}")
            else:
                print(f"[warning] client/dist not found - run 'cd client && npm run build'")
                print("[info] Or set PROD_RUN_FRONTEND=true for dev preview server")

        # Start all processes
        for name, config in commands.items():
            proc = start_process(name, config["cmd"], config["cwd"])  # type: ignore[arg-type]
            processes.append((name, proc))

        print(f"\n[ready] BaluHost production server running")
        print(f"[ready] API: http://{PROD_CONFIG['backend_host']}:{PROD_CONFIG['backend_port']}")
        print(f"[ready] Docs: http://{PROD_CONFIG['backend_host']}:{PROD_CONFIG['backend_port']}/docs")
        print(f"[ready] Press Ctrl+C to stop\n")

        # Monitor processes
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
