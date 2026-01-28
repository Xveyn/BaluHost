#!/bin/bash
set -e

echo "Completing PostgreSQL Production Setup..."

DB_PASSWORD="3bHuIiGi6gyO93SbvEzydtiMwAfAtYYl2D-PogdIMT4"

# Set password for baluhost user
echo "Setting database password..."
sudo -u postgres psql -d baluhost <<EOF
ALTER USER baluhost WITH PASSWORD '$DB_PASSWORD';
EOF

# Configure pg_hba.conf
echo "Configuring PostgreSQL authentication..."
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -n1)
sudo cp "$PG_HBA" "${PG_HBA}.backup"

# Add local connection for baluhost user if not exists
if ! sudo grep -q "local.*baluhost.*baluhost" "$PG_HBA"; then
    echo "local   baluhost   baluhost   md5" | sudo tee -a "$PG_HBA"
fi

# Reload PostgreSQL
sudo systemctl reload postgresql

# Install Nginx and Certbot
echo "Installing Nginx and Certbot..."
sudo apt install -y nginx certbot python3-certbot-nginx

echo ""
echo "✅ Setup completed!"
echo ""
echo "Database Connection String:"
echo "DATABASE_URL=postgresql://baluhost:$DB_PASSWORD@localhost:5432/baluhost"
echo ""
echo "Save this password securely!"
