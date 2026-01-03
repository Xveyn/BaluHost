#!/usr/bin/env python3
"""
BaluDesk Development Starter
=============================
Startet Backend (C++) und Frontend (Electron) gleichzeitig für Development.

Usage:
    python start.py              # Start both backend and frontend
    python start.py --backend    # Start only backend
    python start.py --frontend   # Start only frontend
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from typing import List, Optional

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(message: str, color: str = Colors.ENDC):
    """Print colored message to console."""
    print(f"{color}{message}{Colors.ENDC}")

def print_header(message: str):
    """Print header message."""
    print_colored(f"\n{'='*60}", Colors.CYAN)
    print_colored(f"  {message}", Colors.BOLD + Colors.CYAN)
    print_colored(f"{'='*60}\n", Colors.CYAN)

def check_backend_exists() -> bool:
    """Check if C++ backend executable exists."""
    backend_paths = [
        Path("backend/build/Release/baludesk-backend.exe"),
        Path("backend/build/Debug/baludesk-backend.exe"),
    ]
    
    for path in backend_paths:
        if path.exists():
            print_colored(f"✓ Backend gefunden: {path}", Colors.GREEN)
            return True
    
    print_colored("✗ Backend nicht gefunden!", Colors.RED)
    print_colored("  Bitte zuerst bauen:", Colors.YELLOW)
    print_colored("    cd backend/build", Colors.YELLOW)
    print_colored("    cmake --build . --config Release", Colors.YELLOW)
    return False

def check_frontend_deps() -> bool:
    """Check if frontend dependencies are installed."""
    node_modules = Path("frontend/node_modules")
    
    if node_modules.exists():
        print_colored("✓ Frontend Dependencies installiert", Colors.GREEN)
        return True
    
    print_colored("✗ Frontend Dependencies fehlen!", Colors.RED)
    print_colored("  Installiere jetzt...", Colors.YELLOW)
    
    try:
        subprocess.run(
            ["npm", "install"],
            cwd="frontend",
            check=True,
            shell=True
        )
        print_colored("✓ Dependencies installiert", Colors.GREEN)
        return True
    except subprocess.CalledProcessError:
        print_colored("✗ npm install fehlgeschlagen", Colors.RED)
        return False

def start_backend() -> Optional[subprocess.Popen]:
    """Start C++ backend process."""
    backend_path = None
    for path_str in ["backend/build/Release/baludesk-backend.exe", 
                     "backend/build/Debug/baludesk-backend.exe"]:
        path = Path(path_str)
        if path.exists():
            backend_path = path
            break
    
    if not backend_path:
        return None
    
    print_colored(f"\n🚀 Starte Backend: {backend_path}", Colors.BLUE)
    
    try:
        process = subprocess.Popen(
            [str(backend_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        time.sleep(1)
        
        if process.poll() is not None:
            print_colored("✗ Backend konnte nicht gestartet werden", Colors.RED)
            return None
        
        print_colored("✓ Backend läuft", Colors.GREEN)
        return process
    
    except Exception as e:
        print_colored(f"✗ Fehler beim Starten: {e}", Colors.RED)
        return None

def start_frontend() -> Optional[subprocess.Popen]:
    """Start Electron frontend process."""
    print_colored("\n🚀 Starte Frontend (Electron + Vite)...", Colors.BLUE)
    
    try:
        # Use npm run dev which starts both Vite and Electron
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="frontend",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        print_colored("✓ Frontend startet...", Colors.GREEN)
        print_colored("  Vite Dev Server: http://localhost:5173", Colors.CYAN)
        print_colored("  Electron App wird geöffnet...", Colors.CYAN)
        return process
    
    except Exception as e:
        print_colored(f"✗ Fehler beim Starten: {e}", Colors.RED)
        return None

def monitor_process(process: subprocess.Popen, name: str):
    """Monitor process output."""
    if not process or not process.stdout:
        return
    
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"[{name}] {line.rstrip()}")
    except Exception:
        pass

def main():
    """Main entry point."""
    # Change to script directory
    os.chdir(Path(__file__).parent)
    
    # Parse arguments
    start_backend_only = "--backend" in sys.argv
    start_frontend_only = "--frontend" in sys.argv
    
    print_header("BaluDesk Development Starter")
    
    processes: List[subprocess.Popen] = []
    
    try:
        # Start backend if requested
        if not start_frontend_only:
            if not check_backend_exists():
                print_colored("\n⚠️  Backend fehlt - nur Frontend wird gestartet", Colors.YELLOW)
            else:
                backend_proc = start_backend()
                if backend_proc:
                    processes.append(backend_proc)
                    time.sleep(2)  # Wait for backend to initialize
        
        # Start frontend if requested
        if not start_backend_only:
            if not check_frontend_deps():
                print_colored("\n✗ Kann Frontend nicht starten", Colors.RED)
                return 1
            
            frontend_proc = start_frontend()
            if frontend_proc:
                processes.append(frontend_proc)
        
        if not processes:
            print_colored("\n✗ Keine Prozesse gestartet", Colors.RED)
            return 1
        
        # Success message
        print_header("BaluDesk läuft!")
        print_colored("Drücke Ctrl+C zum Beenden\n", Colors.YELLOW)
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
            # Check if any process died
            for proc in processes:
                if proc.poll() is not None:
                    print_colored(f"\n⚠️  Prozess beendet (Exit Code: {proc.returncode})", Colors.YELLOW)
                    raise KeyboardInterrupt
    
    except KeyboardInterrupt:
        print_colored("\n\n⏹️  Beende BaluDesk...", Colors.YELLOW)
    
    finally:
        # Cleanup processes
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass
        
        print_colored("\n✓ Alle Prozesse beendet", Colors.GREEN)
        print_colored("Bis bald! 👋\n", Colors.CYAN)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
