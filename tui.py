#!/usr/bin/env python3
"""
BaluHost TUI Launcher

Quick start script to launch the Terminal User Interface.
Run with: python tui.py
"""
import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

if __name__ == "__main__":
    from baluhost_tui.main import cli
    cli()
