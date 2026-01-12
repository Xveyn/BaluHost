# PostgreSQL Migration - Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Start PostgreSQL

```bash
# Copy environment template
cp .env.postgres.example .env.postgres

# Edit and set secure password
nano .env.postgres  # Change POSTGRES_PASSWORD!

# Start PostgreSQL
docker-compose -f docker-compose.postgres.yml --env-file .env.postgres up -d

# Verify it's running
docker-compose -f docker-compose.postgres.yml ps
```

### Step 2: Install psycopg2

```bash
cd backend
pip install -e ".[dev]"  # This will install psycopg2-binary
```

### Step 3: Test Connection

```bash
python scripts/test_postgres_connection.py \
    --url "postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost"
```

### Step 4: Run Migration

```bash
python scripts/migrate_to_postgres.py \
    --sqlite-path ./baluhost.db \
    --postgres-url "postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost"
```

### Step 5: Update Configuration

Edit `backend/.env`:
```env
DATABASE_URL=postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost
NAS_MODE=prod
```

### Step 6: Start Backend

```bash
uvicorn app.main:app --reload --port 3001
```

✅ Done! Check logs for "Using PostgreSQL database with connection pooling"

---

## 📚 Full Documentation

See [docs/POSTGRESQL_MIGRATION.md](docs/POSTGRESQL_MIGRATION.md) for:
- Detailed setup instructions
- Manual installation (without Docker)
- Performance tuning
- Troubleshooting
- Backup & recovery

---

## 🔍 Verify Migration

```bash
# Check row counts match
python scripts/migrate_to_postgres.py --verify-only \
    --postgres-url "postgresql://baluhost:PASSWORD@localhost:5432/baluhost"
```

---

## 🎯 What We Created

### Files Added:
1. **docker-compose.postgres.yml** - PostgreSQL + pgAdmin setup
2. **.env.postgres.example** - Configuration template
3. **backend/scripts/postgres/01-init-extensions.sql** - DB initialization
4. **backend/scripts/migrate_to_postgres.py** - Migration tool
5. **backend/scripts/test_postgres_connection.py** - Connection test
6. **docs/POSTGRESQL_MIGRATION.md** - Full documentation

### Files Modified:
1. **backend/app/core/database.py** - PostgreSQL support + connection pooling
2. **backend/pyproject.toml** - Added psycopg2-binary dependency

---

## 🐛 Quick Troubleshooting

**Connection Refused:**
```bash
docker-compose -f docker-compose.postgres.yml logs postgres
```

**Authentication Failed:**
```bash
# Verify password in .env.postgres matches
cat .env.postgres | grep POSTGRES_PASSWORD
```

**Migration Failed:**
```bash
# Check Alembic migrations
cd backend
alembic current
alembic upgrade head
```

---

**Need help?** See full docs: `docs/POSTGRESQL_MIGRATION.md`
