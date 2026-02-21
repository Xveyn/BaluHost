#!/bin/bash
# BaluHost Install - Module 06: PostgreSQL Setup
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Main ───────────────────────────────────────────────────────────

log_step "PostgreSQL Setup"

require_root

# --- Ensure PostgreSQL is started ---
if systemctl is-active postgresql &>/dev/null; then
    log_info "PostgreSQL is already running."
else
    log_info "Starting PostgreSQL..."
    systemctl start postgresql
    systemctl enable postgresql
    log_info "PostgreSQL started and enabled."
fi

# --- Wait for PostgreSQL to be ready ---
for i in $(seq 1 10); do
    if sudo -u postgres pg_isready &>/dev/null; then
        break
    fi
    if [[ "$i" -eq 10 ]]; then
        log_error "PostgreSQL did not become ready within 10 seconds."
        exit 1
    fi
    sleep 1
done
log_info "PostgreSQL is ready."

# --- Generate password if not set ---
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD=$(generate_db_password)
    log_info "Generated random PostgreSQL password."
    export POSTGRES_PASSWORD
fi

# --- Create PostgreSQL user ---
if pg_user_exists "$POSTGRES_USER"; then
    log_info "PostgreSQL user '$POSTGRES_USER' already exists."
    # Update password to ensure it matches config
    sudo -u postgres psql -c "ALTER USER \"$POSTGRES_USER\" WITH PASSWORD '$POSTGRES_PASSWORD';" &>/dev/null
    log_info "Updated password for PostgreSQL user '$POSTGRES_USER'."
else
    sudo -u postgres psql -c "CREATE USER \"$POSTGRES_USER\" WITH PASSWORD '$POSTGRES_PASSWORD';" &>/dev/null
    log_info "Created PostgreSQL user '$POSTGRES_USER'."
fi

# --- Create database ---
if pg_db_exists "$POSTGRES_DB"; then
    log_info "Database '$POSTGRES_DB' already exists."
    # Ensure ownership is correct
    sudo -u postgres psql -c "ALTER DATABASE \"$POSTGRES_DB\" OWNER TO \"$POSTGRES_USER\";" &>/dev/null
    log_info "Ensured database '$POSTGRES_DB' is owned by '$POSTGRES_USER'."
else
    sudo -u postgres psql -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";" &>/dev/null
    log_info "Created database '$POSTGRES_DB' owned by '$POSTGRES_USER'."
fi

# --- Configure pg_hba.conf for local md5 auth ---
log_step "Configuring pg_hba.conf"

PG_HBA=$(sudo -u postgres psql -tAc "SHOW hba_file;" 2>/dev/null | tr -d ' ')
if [[ -z "$PG_HBA" || ! -f "$PG_HBA" ]]; then
    # Fallback: find pg_hba.conf
    PG_HBA=$(find /etc/postgresql -name pg_hba.conf -type f 2>/dev/null | head -1)
fi

if [[ -z "$PG_HBA" || ! -f "$PG_HBA" ]]; then
    log_error "Could not locate pg_hba.conf"
    exit 1
fi

log_info "pg_hba.conf location: $PG_HBA"

# Check if a local md5/scram-sha-256 entry exists for our database or all databases
HBA_ENTRY="local   $POSTGRES_DB   $POSTGRES_USER   md5"
if grep -qE "^local\s+($POSTGRES_DB|all)\s+($POSTGRES_USER|all)\s+(md5|scram-sha-256)" "$PG_HBA"; then
    log_info "pg_hba.conf already has a suitable local auth entry."
else
    log_info "Adding md5 auth entry to pg_hba.conf..."
    # Insert before the first "local all all" line to ensure our specific rule takes priority
    TEMP_HBA=$(mktemp)
    INSERTED=false
    while IFS= read -r line; do
        if [[ "$INSERTED" == "false" ]] && echo "$line" | grep -qE "^local\s+all\s+all"; then
            echo "$HBA_ENTRY" >> "$TEMP_HBA"
            INSERTED=true
        fi
        echo "$line" >> "$TEMP_HBA"
    done < "$PG_HBA"

    # If no "local all all" line found, append at end
    if [[ "$INSERTED" == "false" ]]; then
        echo "$HBA_ENTRY" >> "$TEMP_HBA"
    fi

    cp "$TEMP_HBA" "$PG_HBA"
    rm -f "$TEMP_HBA"
    log_info "Added entry: $HBA_ENTRY"
fi

# --- Reload PostgreSQL to apply hba changes ---
log_info "Reloading PostgreSQL configuration..."
systemctl reload postgresql
sleep 1
log_info "PostgreSQL reloaded."

# --- Test connection ---
log_step "Testing Connection"

export PGPASSWORD="$POSTGRES_PASSWORD"
if psql -h localhost -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;" &>/dev/null; then
    log_info "Connection test PASSED: $POSTGRES_USER@localhost/$POSTGRES_DB"
else
    # Try via Unix socket
    if psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;" &>/dev/null; then
        log_info "Connection test PASSED (via Unix socket): $POSTGRES_USER/$POSTGRES_DB"
    else
        log_error "Connection test FAILED. Check pg_hba.conf and PostgreSQL logs."
        log_error "  pg_hba.conf: $PG_HBA"
        log_error "  Logs: journalctl -u postgresql"
        unset PGPASSWORD
        exit 1
    fi
fi
unset PGPASSWORD

# --- Export DATABASE_URL for later modules ---
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}"

# --- Summary ---
log_step "PostgreSQL Summary"
PG_VERSION=$(sudo -u postgres psql -tAc "SELECT version();" 2>/dev/null | head -1)
log_info "PostgreSQL: $PG_VERSION"
log_info "User:       $POSTGRES_USER"
log_info "Database:   $POSTGRES_DB"
log_info "pg_hba:     $PG_HBA"
log_info "URL:        postgresql://${POSTGRES_USER}:****@localhost:5432/${POSTGRES_DB}"
log_info "PostgreSQL setup complete."

exit 0
