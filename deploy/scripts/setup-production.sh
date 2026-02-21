#!/bin/bash
# DEPRECATED: Use deploy/install/install.sh instead.
# This script is replaced by modules 02-system-packages, 06-postgresql, and 07-env-generate.
echo "WARNING: This script is deprecated. Use deploy/install/install.sh instead." >&2
set -e  # Exit on error

echo "================================================"
echo "BaluHost Production Setup Script"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

# Variables
PROJECT_DIR="/home/sven/projects/BaluHost"
BALUHOST_USER="sven"
DB_NAME="baluhost"
DB_USER="baluhost"
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo -e "${GREEN}Step 1/7: Installing PostgreSQL...${NC}"
apt update
apt install -y postgresql postgresql-contrib

echo -e "${GREEN}Step 2/7: Starting PostgreSQL service...${NC}"
systemctl start postgresql
systemctl enable postgresql

echo -e "${GREEN}Step 3/7: Creating database and user...${NC}"
sudo -u postgres psql <<EOF
-- Drop existing database and user if they exist
DROP DATABASE IF EXISTS $DB_NAME;
DROP USER IF EXISTS $DB_USER;

-- Create user and database
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Connect to database and grant schema privileges
\c $DB_NAME
GRANT ALL ON SCHEMA public TO $DB_USER;
EOF

echo -e "${GREEN}Step 4/7: Configuring PostgreSQL authentication...${NC}"
# Backup pg_hba.conf
cp /etc/postgresql/*/main/pg_hba.conf /etc/postgresql/*/main/pg_hba.conf.backup

# Add local connection for baluhost user (md5 auth)
PG_HBA_FILE=$(find /etc/postgresql -name pg_hba.conf | head -n1)
if ! grep -q "local.*$DB_NAME.*$DB_USER" "$PG_HBA_FILE"; then
    echo "local   $DB_NAME   $DB_USER   md5" >> "$PG_HBA_FILE"
fi

# Reload PostgreSQL
systemctl reload postgresql

echo -e "${GREEN}Step 5/7: Installing required system packages...${NC}"
apt install -y nginx python3-pip python3-venv certbot python3-certbot-nginx

echo -e "${GREEN}Step 6/7: Saving database credentials...${NC}"
CREDS_FILE="/home/$BALUHOST_USER/baluhost_db_credentials.txt"
cat > "$CREDS_FILE" <<EOF
BaluHost Production Database Credentials
========================================
Generated: $(date)

Database Name: $DB_NAME
Database User: $DB_USER
Database Password: $DB_PASSWORD

Connection String:
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME

IMPORTANT: Copy this password to your .env.production file!
After copying, delete this file or store it securely.
EOF

chown $BALUHOST_USER:$BALUHOST_USER "$CREDS_FILE"
chmod 600 "$CREDS_FILE"

echo -e "${GREEN}Step 7/7: Verifying PostgreSQL connection...${NC}"
sudo -u postgres psql -d $DB_NAME -c "SELECT version();" > /dev/null 2>&1

echo ""
echo -e "${GREEN}================================================"
echo "✅ Production setup completed successfully!"
echo "================================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. View database credentials: cat $CREDS_FILE"
echo "2. Copy DATABASE_URL to .env.production"
echo "3. Run database migrations: cd backend && alembic upgrade head"
echo "4. Continue with systemd service setup"
echo ""
echo -e "${YELLOW}PostgreSQL Status:${NC}"
systemctl status postgresql --no-pager | head -n3
