# PostgreSQL Migration Guide

## 📋 Overview

This guide walks you through migrating BaluHost from SQLite to PostgreSQL for production deployment.

**Why PostgreSQL?**
- Better concurrent write performance
- ACID compliance for production workloads
- Advanced indexing and query optimization
- Better scalability for multiple users
- Native JSON support
- Robust backup and replication

**Migration Time**: ~15-30 minutes (depending on data volume)

---

## 🚀 Quick Start (Docker Compose)

### 1. Start PostgreSQL Container

```bash
# Copy environment template
cp .env.postgres.example .env.postgres

# Edit .env.postgres and set secure passwords
nano .env.postgres

# Start PostgreSQL + pgAdmin
docker-compose -f docker-compose.postgres.yml --env-file .env.postgres up -d

# Check that PostgreSQL is running
docker-compose -f docker-compose.postgres.yml ps
```

Expected output:
```
NAME                    STATUS              PORTS
baluhost-postgres       Up 10 seconds       0.0.0.0:5432->5432/tcp
baluhost-pgadmin        Up 10 seconds       0.0.0.0:5050->80/tcp
```

### 2. Verify PostgreSQL Connection

```bash
# Test connection using psql (if installed)
psql -h localhost -U baluhost -d baluhost -c "SELECT version();"

# Or test with Python
python backend/scripts/test_postgres_connection.py
```

### 3. Run Migration

```bash
cd backend

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Run migration (creates backup automatically)
python scripts/migrate_to_postgres.py \
    --sqlite-path ./baluhost.db \
    --postgres-url "postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost"
```

**Migration Script Features:**
- ✅ Automatic SQLite backup
- ✅ Schema migration via Alembic
- ✅ Data migration with batch processing
- ✅ Row count verification
- ✅ Rollback support

### 4. Update Configuration

```bash
# Update backend/.env
nano backend/.env
```

Add or update:
```env
DATABASE_URL=postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost
NAS_MODE=prod
```

### 5. Test the Application

```bash
# Start backend with PostgreSQL
cd backend
uvicorn app.main:app --reload --port 3001

# Check logs for "Using PostgreSQL database with connection pooling"
# Visit http://localhost:3001/docs to test API
```

---

## 📊 Connection Pool Configuration

The PostgreSQL connection pool can be tuned via environment variables:

```env
# Connection Pool Settings (defaults shown)
DB_POOL_SIZE=10              # Number of persistent connections
DB_MAX_OVERFLOW=20           # Additional connections when pool is full
DB_POOL_TIMEOUT=30           # Seconds to wait for connection
DB_POOL_RECYCLE=3600         # Seconds before recycling connections (1 hour)

# Debugging (dev only)
DB_ECHO=false                # Log all SQL queries
DB_ECHO_POOL=false           # Log connection pool activity
```

**Recommended Settings:**

| Deployment Size | POOL_SIZE | MAX_OVERFLOW |
|----------------|-----------|--------------|
| Small (1-5 users) | 5 | 10 |
| Medium (5-20 users) | 10 | 20 |
| Large (20+ users) | 20 | 40 |

---

## 🔧 Manual Setup (No Docker)

### Install PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**macOS (Homebrew):**
```bash
brew install postgresql@16
brew services start postgresql@16
```

**Windows:**
Download installer from https://www.postgresql.org/download/windows/

### Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# Inside psql:
CREATE DATABASE baluhost;
CREATE USER baluhost WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE baluhost TO baluhost;

# Enable extensions
\c baluhost
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

\q
```

### Run Migration

```bash
cd backend
python scripts/migrate_to_postgres.py \
    --sqlite-path ./baluhost.db \
    --postgres-url "postgresql://baluhost:your_secure_password@localhost:5432/baluhost"
```

---

## 🔍 Verification

### Check Data Integrity

```bash
# Verify row counts match
python scripts/migrate_to_postgres.py \
    --postgres-url "postgresql://baluhost:PASSWORD@localhost:5432/baluhost" \
    --verify-only
```

### Access pgAdmin

If using Docker:
1. Open http://localhost:5050
2. Login with credentials from `.env.postgres`
3. Add server:
   - Host: `postgres` (Docker network) or `localhost`
   - Port: `5432`
   - Username: `baluhost`
   - Password: (from `.env.postgres`)

### Query Data Manually

```bash
# Connect to PostgreSQL
psql -h localhost -U baluhost -d baluhost

# List tables
\dt

# Check user count
SELECT COUNT(*) FROM users;

# Check file metadata
SELECT COUNT(*) FROM file_metadata;

# Exit
\q
```

---

## 🔄 Rollback (If Needed)

If something goes wrong, you can rollback to SQLite:

```bash
# 1. Stop the backend
# 2. Restore from backup
cp backups/baluhost_backup_TIMESTAMP.db backend/baluhost.db

# 3. Update backend/.env
DATABASE_URL=sqlite:///./baluhost.db
NAS_MODE=dev

# 4. Restart backend
uvicorn app.main:app --reload --port 3001
```

The migration script **does not delete** your SQLite database, so rollback is safe.

---

## 🐛 Troubleshooting

### Connection Refused

```
Error: connection refused (localhost:5432)
```

**Solutions:**
- Check PostgreSQL is running: `docker ps` or `systemctl status postgresql`
- Verify port: PostgreSQL default is 5432
- Check firewall: `sudo ufw allow 5432` (Linux)

### Authentication Failed

```
Error: password authentication failed for user "baluhost"
```

**Solutions:**
- Verify password in `.env.postgres` matches database
- Check `pg_hba.conf` for authentication method
- Recreate user with correct password

### Migration Failed: Row Count Mismatch

```
Error: Row count mismatch in users: source=10, target=9
```

**Solutions:**
- Check PostgreSQL logs: `docker logs baluhost-postgres`
- Run migration again (it will skip existing data)
- Check for constraint violations

### Performance Issues

```
Slow queries after migration
```

**Solutions:**
- Run `ANALYZE` on all tables: `psql -c "ANALYZE;"`
- Increase `DB_POOL_SIZE` if seeing connection timeouts
- Check `shared_buffers` in PostgreSQL config (25% of RAM recommended)
- Create indexes: Already handled by Alembic migrations

---

## 📈 Performance Tuning

### PostgreSQL Configuration

Edit `postgresql.conf` (or use Docker environment variables):

```conf
# Memory settings (adjust based on available RAM)
shared_buffers = 256MB              # 25% of RAM
effective_cache_size = 1GB          # 50-75% of RAM
maintenance_work_mem = 64MB
work_mem = 8MB

# Connection settings
max_connections = 100               # Should be > pool_size * app instances

# Write-ahead log
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# Query planner
random_page_cost = 1.1              # For SSD
effective_io_concurrency = 200      # For SSD
```

### Monitoring Queries

```sql
-- Show active queries
SELECT pid, usename, state, query, query_start
FROM pg_stat_activity
WHERE state = 'active';

-- Show slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Show table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

## 🔒 Security Best Practices

### 1. Use Strong Passwords

```bash
# Generate secure password
openssl rand -base64 32
```

### 2. Restrict Network Access

```yaml
# docker-compose.postgres.yml
services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"  # Only localhost
```

### 3. Enable SSL (Production)

```yaml
# docker-compose.postgres.yml
services:
  postgres:
    environment:
      POSTGRES_SSL_MODE: require
    volumes:
      - ./certs/server.crt:/var/lib/postgresql/server.crt
      - ./certs/server.key:/var/lib/postgresql/server.key
```

### 4. Regular Backups

```bash
# Automated backup script
docker exec baluhost-postgres pg_dump -U baluhost baluhost > backup_$(date +%Y%m%d).sql

# Compress
gzip backup_$(date +%Y%m%d).sql

# Restore
gunzip -c backup_20260112.sql.gz | docker exec -i baluhost-postgres psql -U baluhost baluhost
```

---

## 🎯 Next Steps

After successful migration:

1. ✅ Update `PRODUCTION_READINESS.md` - PostgreSQL ✓
2. ✅ Set up automated backups (cron job or systemd timer)
3. ✅ Configure monitoring (pg_stat_statements)
4. ⏩ Continue with **Security Hardening** (Phase 1, Task 2)
5. ⏩ Implement **Structured Logging** (Phase 1, Task 3)
6. ⏩ Create **Deployment Documentation** (Phase 1, Task 4)

---

## 📚 Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [SQLAlchemy PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [Alembic Migration Guide](https://alembic.sqlalchemy.org/en/latest/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)

---

**Last Updated:** January 2026
**Version:** 1.0
**Maintainer:** BaluHost Team
