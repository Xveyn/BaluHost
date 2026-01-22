#!/bin/bash
# Setup script for BaluHost on Debian/Ubuntu
# Run with: bash setup_debian.sh

set -e

echo "==> BaluHost Development Setup for Debian/Ubuntu"
echo ""

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "[error] python3 is not installed. Install with:"
    echo "  sudo apt update && sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

# Check Node.js/npm
if ! command -v npm &> /dev/null; then
    echo "[error] npm is not installed. Install with:"
    echo "  sudo apt update && sudo apt install nodejs npm"
    exit 1
fi

echo "[info] Python version: $(python3 --version)"
echo "[info] Node version: $(node --version)"
echo "[info] npm version: $(npm --version)"
echo ""

# Setup backend
echo "==> Setting up Python backend..."
cd backend

if [ ! -d ".venv" ]; then
    echo "[info] Creating virtual environment..."
    python3 -m venv .venv
else
    echo "[info] Virtual environment already exists"
fi

echo "[info] Activating virtual environment..."
source .venv/bin/activate

echo "[info] Upgrading pip..."
pip install --upgrade pip

echo "[info] Installing backend dependencies..."
pip install -e ".[dev]"

deactivate
cd ..

# Setup frontend
echo ""
echo "==> Setting up React frontend..."
cd client

if [ ! -d "node_modules" ]; then
    echo "[info] Installing npm dependencies..."
    npm install
else
    echo "[info] npm dependencies already installed"
fi

cd ..

echo ""
echo "==> Setup complete!"
echo ""
echo "To start the development servers, run:"
echo "  python3 start_dev.py"
echo ""
echo "The following services will be available:"
echo "  - Backend API: http://localhost:8000"
echo "  - Frontend UI: http://localhost:5173"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
echo "Optional: Enable HTTPS mode with:"
echo "  export DEV_USE_HTTPS=true"
echo "  python3 start_dev.py"
