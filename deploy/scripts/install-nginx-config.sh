#!/bin/bash
set -e

echo "Installing Nginx configuration for BaluHost..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or with sudo"
    exit 1
fi

# Backup existing config if it exists
if [ -f /etc/nginx/sites-available/baluhost ]; then
    echo "Backing up existing config..."
    cp /etc/nginx/sites-available/baluhost /etc/nginx/sites-available/baluhost.backup.$(date +%Y%m%d_%H%M%S)
fi

# Copy new config
echo "Copying Nginx configuration..."
cp /home/sven/projects/BaluHost/deploy/nginx/baluhost.conf /etc/nginx/sites-available/baluhost

# Enable site (create symlink)
echo "Enabling site..."
ln -sf /etc/nginx/sites-available/baluhost /etc/nginx/sites-enabled/baluhost

# Remove default site if it exists
if [ -f /etc/nginx/sites-enabled/default ]; then
    echo "Removing default Nginx site..."
    rm /etc/nginx/sites-enabled/default
fi

# Test Nginx configuration
echo "Testing Nginx configuration..."
nginx -t

# Reload Nginx
echo "Reloading Nginx..."
systemctl reload nginx

echo ""
echo "✅ Nginx configuration installed successfully!"
echo ""
echo "BaluHost is now accessible at:"
echo "  - http://localhost"
echo "  - http://baluhost.local (if mDNS is configured)"
echo "  - http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Backend API: http://localhost/api/"
echo "Swagger Docs: http://localhost/docs"
echo ""
echo "To enable HTTPS, run: sudo certbot --nginx -d yourdomain.com"
