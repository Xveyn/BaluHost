#!/bin/bash
set -e

echo "Installing BaluHost systemd services..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or with sudo"
    exit 1
fi

# Copy service files to systemd directory
echo "Copying service files to /etc/systemd/system/..."
cp /home/sven/projects/BaluHost/deploy/systemd/baluhost-backend.service /etc/systemd/system/
cp /home/sven/projects/BaluHost/deploy/systemd/baluhost-frontend.service /etc/systemd/system/

# Set proper permissions
chmod 644 /etc/systemd/system/baluhost-backend.service
chmod 644 /etc/systemd/system/baluhost-frontend.service

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable services (but don't start yet)
echo "Enabling services..."
systemctl enable baluhost-backend.service
systemctl enable baluhost-frontend.service

echo ""
echo "✅ Systemd services installed and enabled!"
echo ""
echo "Services will start automatically on boot."
echo "To start manually:"
echo "  sudo systemctl start baluhost-backend"
echo "  sudo systemctl start baluhost-frontend"
echo ""
echo "To check status:"
echo "  sudo systemctl status baluhost-backend"
echo "  sudo systemctl status baluhost-frontend"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u baluhost-backend -f"
echo "  sudo journalctl -u baluhost-frontend -f"
