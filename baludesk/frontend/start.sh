#!/bin/bash
# BaluDesk Start Script (Bash - For Linux/macOS)
# Automatically starts backend and frontend (Electron)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "========================================"
echo "  BaluDesk - Starting Application"
echo "========================================"
echo ""
echo "Current directory: $SCRIPT_DIR"
echo ""

# Kill any running BaluDesk processes
echo "[*] Cleaning up old processes..."
pkill -f "baludesk-backend" 2>/dev/null
pkill -f "electron" 2>/dev/null
sleep 1
echo "[OK] Old processes cleaned"
echo ""

# Start backend in background
if [ -f "$SCRIPT_DIR/backend/baludesk-backend" ]; then
    echo "[*] Starting Backend..."
    "$SCRIPT_DIR/backend/baludesk-backend" &
    sleep 2
    echo "[OK] Backend started"
elif [ -f "$SCRIPT_DIR/backend/baludesk-backend.exe" ]; then
    # Windows backend (if wine is available)
    echo "[*] Starting Backend (Windows)..."
    "$SCRIPT_DIR/backend/baludesk-backend.exe" &
    sleep 2
    echo "[OK] Backend started"
else
    echo "[!] Warning: Backend not found at $SCRIPT_DIR/backend/"
fi

echo ""
echo "[*] Starting Frontend..."

# Start Electron frontend
if [ -f "$SCRIPT_DIR/electron" ]; then
    # Linux Electron
    "$SCRIPT_DIR/electron" "$SCRIPT_DIR" &
    echo "[OK] Frontend started"
elif [ -f "$SCRIPT_DIR/electron.exe" ]; then
    # Windows Electron (if wine is available)
    "$SCRIPT_DIR/electron.exe" "$SCRIPT_DIR" &
    echo "[OK] Frontend started"
else
    echo "[ERROR] electron not found at $SCRIPT_DIR/"
    read -p "Press Enter to close"
    exit 1
fi

echo ""
echo "BaluDesk is running. You can close this window."
echo ""

sleep 3
exit 0
