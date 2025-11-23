# Database Migration Documentation

## Übersicht

Die BaluHost-Anwendung wurde von JSON-basierten Speicher auf SQLite-Datenbank migriert. Diese Dokumentation beschreibt die Migration und neue Best Practices.

## ✅ Abgeschlossene Migrationen

### 1. **Database Models erstellt**
- `app/models/user.py` - User Model mit SQLAlchemy
- `app/models/file_metadata.py` - FileMetadata Model für persistente Datei-Informationen
- `app/models/base.py` - Base Model mit gemeinsamen Funktionen

### 2. **Database Configuration**
- `app/core/database.py` - Session Management, SQLite Optimierungen
- Support für SQLite (dev) und PostgreSQL (production)
- Connection Pooling und WAL-Mode für Performance

### 3. **API Routes mit DB Sessions**

#### Auth Routes (`app/api/routes/auth.py`)
- `POST /auth/login` - DB Session injiziert
- `POST /auth/register` - DB Session injiziert

#### User Routes (`app/api/routes/users.py`)
- `GET /users` - DB Session injiziert
- `POST /users` - DB Session injiziert
- `PUT /users/{user_id}` - DB Session injiziert
- `DELETE /users/{user_id}` - DB Session injiziert

#### Dependencies (`app/api/deps.py`)
- `get_current_user()` - Nutzt DB Session für User Lookup
- `get_current_admin()` - Admin-Validierung (ohne zusätzliche DB-Abfrage)

### 4. **File Metadata Service**
Neuer Database-backed Service: `app/services/file_metadata_db.py`

**Funktionen:**
- `create_metadata()` - Neue File/Dir Metadata erstellen
- `get_metadata()` - Metadata abrufen
- `update_metadata()` - Size/MIME Type aktualisieren
- `delete_metadata()` - Metadata löschen
- `rename_metadata()` - Rename/Move Operation
- `list_children()` - Directory-Listing
- `get_owner_id()` / `set_owner_id()` - Ownership Management

**Legacy-Kompatibilität:**
- `get_owner()` / `set_owner()` - String-basierte Owner IDs (deprecated)

### 5. **Alembic Migrations Setup**
```bash
# Initialisiert
alembic init alembic

# Erste Migration
alembic revision --autogenerate -m "Initial database schema"

# Migration anwenden
alembic upgrade head
```

**Konfiguration:**
- `alembic.ini` - Alembic Konfiguration
- `alembic/env.py` - Dynamische DB URL, Model Imports
- `alembic/versions/` - Migration Scripts

### 6. **Seed Data Script**
`backend/scripts/seed.py`

**Funktionen:**
- Admin User Creation
- Demo Users (dev mode)
- Demo File Metadata (dev mode)

**Ausführen:**
```bash
python scripts/seed.py
```

### 7. **Test Fixtures mit Rollback**
`backend/tests/conftest.py`

**Fixtures:**
- `db_session` - In-memory SQLite Session mit Auto-Rollback
- `client` - TestClient mit DB Override
- `admin_user`, `regular_user`, `another_user` - Test Users
- `admin_headers`, `user_headers` - Auth Headers
- `sample_file_metadata`, `sample_directory_metadata` - Test Data

**Test Isolation:**
Jeder Test bekommt eine frische In-Memory-Database, alle Änderungen werden automatisch zurückgerollt.

## 🔄 Noch ausstehende Migrationen

### 1. **Files Service Integration**
Der bestehende `app/services/files.py` Service muss auf den neuen `file_metadata_db.py` Service umgestellt werden:

**Zu ändern:**
- `save_uploads()` - File Metadata in DB speichern
- `delete_path()` - Metadata aus DB entfernen
- `create_folder()` - Directory Metadata erstellen
- Ownership Checks mit `file_metadata_db.get_owner_id()`

### 2. **System Routes mit DB Sessions**
`app/api/routes/system.py` - noch keine DB-Abhängigkeiten

**Zu prüfen:**
- RAID Status
- SMART Monitoring
- Telemetry
→ Möglicherweise keine DB nötig (System-Level Daten)

### 3. **Logging Routes mit DB Sessions**
`app/api/routes/logging.py` - Audit Logs in Database speichern?

**Optionale Erweiterung:**
- Audit Log Model erstellen
- Disk I/O History in DB speichern
- Query-basierte Log-Filterung

## 📝 Best Practices

### Database Sessions in API Routes

**DO:**
```python
from sqlalchemy.orm import Session
from app.core.database import get_db

@router.get("/items")
async def get_items(db: Session = Depends(get_db)):
    items = db.query(Item).all()
    return items
```

**DON'T:**
```python
# Nicht mehr verwenden!
from app.core.database import SessionLocal

@router.get("/items")
async def get_items():
    db = SessionLocal()  # ❌ Session manually erstellt
    items = db.query(Item).all()
    db.close()  # ❌ Manual close
    return items
```

### Service Layer mit optionaler DB Session

**Pattern:**
```python
def get_user(user_id: int, db: Optional[Session] = None) -> Optional[User]:
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        if should_close:
            db.close()
```

**Vorteile:**
- API Routes können DB Session durchreichen (efficient)
- Service kann auch standalone genutzt werden
- Test-friendly

### Tests schreiben

**Verwende Fixtures:**
```python
def test_create_user(db_session: Session):
    user = User(username="test", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    
    # Test assertions
    assert user.id is not None
    # Kein Rollback nötig - Fixture macht das automatisch
```

**API Tests mit Client:**
```python
def test_login(client: TestClient, admin_user: User):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "changeme"}
    )
    assert response.status_code == 200
    # DB changes werden automatisch zurückgerollt
```

## 🗄️ Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100),
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### File Metadata Table
```sql
CREATE TABLE file_metadata (
    id INTEGER PRIMARY KEY,
    path VARCHAR(1000) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    owner_id INTEGER NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    is_directory BOOLEAN DEFAULT 0,
    mime_type VARCHAR(100),
    parent_path VARCHAR(1000),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**Indizes:**
- `path` (unique)
- `owner_id`
- `parent_path`
- `is_directory`
- `name`

## 🚀 Deployment

### Dev Mode
```bash
# Database wird automatisch in dev-storage/ erstellt
NAS_MODE=dev python -m app.main

# Seed ausführen
python scripts/seed.py
```

### Production Mode
```bash
# SQLite in /var/lib/baluhost/
# Oder PostgreSQL via DATABASE_URL
DATABASE_URL=postgresql://user:pass@localhost/baluhost python -m app.main

# Migrations anwenden
alembic upgrade head

# Seed für Admin User
python scripts/seed.py
```

## 🔍 Troubleshooting

### "No module named 'app'"
```bash
# Sicherstellen, dass PYTHONPATH gesetzt ist oder aus backend/ Verzeichnis gestartet wird
cd backend
python -m pytest
```

### Database locked
```bash
# WAL-Mode aktiviert? Check in database.py
# Parallele Writes sollten kein Problem sein

# Falls nötig: Database neu erstellen
rm baluhost.db*
python scripts/seed.py
```

### Alembic Fehler
```bash
# Env.py muss Models importieren
# Check alembic/env.py für korrekte Imports

# Neue Migration
alembic revision --autogenerate -m "Description"

# Apply
alembic upgrade head
```

## 📚 Weitere Ressourcen

- [SQLAlchemy ORM Tutorial](https://docs.sqlalchemy.org/en/20/orm/tutorial.html)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [FastAPI with SQL Databases](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [pytest Fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)

## ✅ Checkliste für neue Features

Wenn du ein neues Feature mit Database entwickelst:

- [ ] Model in `app/models/` erstellen
- [ ] Base von `app.models.base.Base` ableiten
- [ ] Alembic Migration generieren
- [ ] Service Layer mit `db: Optional[Session]` Parameter
- [ ] API Route mit `db: Session = Depends(get_db)`
- [ ] Test Fixtures in `conftest.py`
- [ ] Unit Tests mit `db_session` Fixture
- [ ] Integration Tests mit `client` Fixture
- [ ] Seed Data in `scripts/seed.py` (optional)

## 🎯 Nächste Schritte

1. **Files Service Migration** - `app/services/files.py` auf DB umstellen
2. **Files Routes Update** - DB Session in alle File Operations
3. **Audit Logs in DB** - Persistente Log-Speicherung (optional)
4. **PostgreSQL Testing** - Production Database Testing
5. **Performance Optimization** - Query Optimization, Indizes
6. **Backup Strategy** - Database Backup & Restore
