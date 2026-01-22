# Linux/Debian Setup Guide

This guide covers setting up BaluHost on Debian/Ubuntu-based Linux distributions.

## Prerequisites

```bash
# Update package list
sudo apt update

# Install Python 3, pip, and venv
sudo apt install python3 python3-pip python3-venv

# Install Node.js and npm (if not already installed)
sudo apt install nodejs npm

# Optional: Install build essentials (required for some Python packages)
sudo apt install build-essential python3-dev
```

## Quick Start

### Automated Setup

Run the provided setup script:

```bash
# Make the script executable
chmod +x setup_debian.sh

# Run the setup
./setup_debian.sh
```

### Manual Setup

If you prefer manual installation:

1. **Backend Setup**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
deactivate
cd ..
```

2. **Frontend Setup**
```bash
cd client
npm install
cd ..
```

## Running the Development Server

From the project root:

```bash
python3 start_dev.py
```

This will start:
- **Backend API**: http://localhost:8000
- **Frontend UI**: http://localhost:5173
- **API Documentation**: http://localhost:8000/docs

**Default Credentials** (dev mode):
- Username: `admin`
- Password: `Admin123`

Press `Ctrl+C` to stop both servers.

## HTTPS Mode (Optional)

For HTTPS in development (useful for testing PWA features):

```bash
export DEV_USE_HTTPS=true
python3 start_dev.py
```

Note: You'll need to accept the self-signed certificate in your browser.

## Production Mode on Linux

To run in production mode (uses real system commands like mdadm):

```bash
export NAS_MODE=prod
python3 start_dev.py
```

**Warning**: Production mode requires:
- Root/sudo access for some operations (RAID management)
- Real disk access
- PostgreSQL database (recommended)

## Troubleshooting

### Port Already in Use

If port 8000 or 5173 is already in use:

```bash
# Find process using port
sudo lsof -i :8000
sudo lsof -i :5173

# Kill process if needed
kill -9 <PID>
```

### Permission Denied

If you encounter permission errors:

```bash
# Make scripts executable
chmod +x start_dev.py
chmod +x setup_debian.sh

# Ensure proper ownership
sudo chown -R $USER:$USER .
```

### Virtual Environment Not Found

The script automatically detects `python3` in the virtual environment:

```bash
# Verify venv exists
ls -la backend/.venv/bin/python3

# Recreate if needed
cd backend
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### npm Errors

```bash
# Clear npm cache
npm cache clean --force

# Delete and reinstall
cd client
rm -rf node_modules package-lock.json
npm install
```

## System Requirements

- **OS**: Debian 11+, Ubuntu 20.04+, or compatible
- **Python**: 3.9+
- **Node.js**: 16+
- **RAM**: 2GB minimum (4GB recommended)
- **Disk**: 10GB free space

## Development Tools (Recommended)

```bash
# Install useful development tools
sudo apt install -y \
  git \
  curl \
  wget \
  vim \
  htop \
  tmux \
  tree
```

## Running as a Service (Production)

For production deployment, consider using systemd:

```bash
# Create service file
sudo nano /etc/systemd/system/baluhost.service
```

Example service configuration:

```ini
[Unit]
Description=BaluHost NAS Backend
After=network.target

[Service]
Type=simple
User=baluhost
WorkingDirectory=/opt/baluhost
Environment="NAS_MODE=prod"
Environment="NAS_QUOTA_BYTES=107374182400"
ExecStart=/opt/baluhost/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable baluhost
sudo systemctl start baluhost
sudo systemctl status baluhost
```

## Security Considerations

When deploying on Linux:

1. **Firewall**: Configure UFW or iptables
   ```bash
   sudo ufw allow 8000/tcp
   sudo ufw allow 5173/tcp  # Only for dev
   sudo ufw enable
   ```

2. **Dedicated User**: Run as non-root user
   ```bash
   sudo useradd -r -s /bin/false baluhost
   ```

3. **Reverse Proxy**: Use nginx or Apache for SSL termination
4. **Database**: Use PostgreSQL instead of SQLite
5. **Secrets**: Set environment variables securely (not in code)

## Additional Resources

- **Main Documentation**: See `TECHNICAL_DOCUMENTATION.md`
- **Architecture**: See `ARCHITECTURE.md`
- **API Documentation**: http://localhost:8000/docs (when running)
- **Production Readiness**: See `PRODUCTION_READINESS.md`

## Support

For issues specific to Linux/Debian, check:
1. System logs: `journalctl -xe`
2. Application logs: Check terminal output
3. File permissions: `ls -la` in project directories
