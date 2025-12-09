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
CERTS_DIR = ROOT_DIR / "dev-certs"

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


def generate_self_signed_cert() -> tuple[Path | None, Path | None]:
    """Generate self-signed certificate for dev HTTPS using backend Python."""
    CERTS_DIR.mkdir(exist_ok=True)
    cert_file = CERTS_DIR / "cert.pem"
    key_file = CERTS_DIR / "key.pem"
    
    # Skip if certificates already exist and are recent (less than 30 days old)
    if cert_file.exists() and key_file.exists():
        cert_age = time.time() - cert_file.stat().st_mtime
        if cert_age < 30 * 24 * 3600:  # 30 days
            print("[info] Using existing dev certificates")
            return cert_file, key_file
    
    print("[info] Generating self-signed certificate for dev HTTPS...")
    backend_python = resolve_backend_python()
    
    # Use backend Python to generate certificate (has cryptography installed)
    gen_script = BACKEND_DIR / "scripts" / "generate_cert.py"
    try:
        result = subprocess.run(
            [backend_python, str(gen_script), str(cert_file), str(key_file)],
            check=True,
            capture_output=True,
            text=True
        )
        if "OK" in result.stdout:
            print("[info] Self-signed certificate generated successfully")
            return cert_file, key_file
        else:
            print(f"[warning] Certificate generation failed: {result.stdout}")
            return None, None
    except subprocess.CalledProcessError as e:
        print(f"[warning] Certificate generation failed: {e.stderr}")
        print("[warning] Falling back to HTTP mode")
        return None, None
    except Exception as e:
        print(f"[warning] Unexpected error: {e}")
        print("[warning] Falling back to HTTP mode")
        return None, None


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
        os.environ.setdefault("NAS_QUOTA_BYTES", str(5 * 1024 * 1024 * 1024))  # 5 GB effektiv (RAID1: 2x5GB)

        npm_binary = resolve_npm_binary()
        
        # Generate self-signed certificates for HTTPS
        # Check if HTTP-only mode is requested (for mobile development)
        # Default to false for easier mobile development
        use_https = os.environ.get("DEV_USE_HTTPS", "false").lower() != "false"
        
        if use_https:
            cert_file, key_file = generate_self_signed_cert()
            use_https = cert_file is not None and key_file is not None
        else:
            cert_file, key_file = None, None
        
        # Get local IP for network access
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "localhost"
        
        backend_cmd = [
            backend_python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "0.0.0.0",  # Bind to all interfaces for network access
            "--port",
            "8000",
        ]
        
        if use_https:
            backend_cmd.extend([
                "--ssl-keyfile", str(key_file),
                "--ssl-certfile", str(cert_file),
            ])
            print("[info] Backend running with HTTPS")
            print(f"[info] - Local: https://localhost:8000")
            print(f"[info] - Network: https://{local_ip}:8000")
            print("[info] You may need to accept the self-signed certificate")
        else:
            print("[info] Backend running with HTTP")
            print(f"[info] - Local: http://localhost:8000")
            print(f"[info] - Network: http://{local_ip}:8000")

        commands: Dict[str, Dict[str, object]] = {
            "backend": {
                "cmd": backend_cmd,
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
