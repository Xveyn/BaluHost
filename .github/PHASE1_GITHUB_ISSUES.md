# Phase 1 GitHub Issues - Copy & Paste Template

## Issue 1: PostgreSQL Migration

```markdown
# [CRITICAL] Task 1: PostgreSQL Migration (4-5 days)

## Description
Migriere BaluHost Backend von SQLite zu PostgreSQL für Production-Readiness.

## Acceptance Criteria
- [ ] PostgreSQL lokal aufgesetzt (Docker oder native)
- [ ] Alle Migrations-Tests grün (TDD approach)
- [ ] SQLite → PostgreSQL Migration Skript funktioniert
- [ ] Daten-Integrität verifiziert
- [ ] Database Connection Pooling implementiert
- [ ] .env dokumentiert mit PostgreSQL URL
- [ ] Migration in CI/CD Pipeline integriert
- [ ] Rollback-Strategie dokumentiert

## Tasks
1. **Subtask 1.1: PostgreSQL Setup (1 day)**
   - [ ] Docker Compose mit PostgreSQL 15
   - [ ] Lokale PostgreSQL Installation (alternatives Dokumentation)
   - [ ] Connection String in .env
   - [ ] `scripts/setup_postgresql.py` ausführen

2. **Subtask 1.2: Migration Tests schreiben (1.5 days)**
   - [ ] `tests/database/test_postgresql_migration.py`
   - [ ] Connection Tests
   - [ ] Table Structure Tests
   - [ ] Data Integrity Tests
   - [ ] UUID Primary Keys Tests
   - [ ] JSON Column Tests
   - [ ] Index Tests
   - [ ] Constraint Tests
   - [ ] **Ziel**: Alle Tests GRÜN vor Migration

3. **Subtask 1.3: Migration Skript implementieren (1.5 days)**
   - [ ] `scripts/migrate_to_postgresql.py`
   - [ ] SQLite → PostgreSQL Daten-Transfer
   - [ ] Automatische Backups
   - [ ] Verifizierungs-Logik
   - [ ] Detailliertes Logging
   - [ ] Rollback-Unterstützung
   - [ ] **Ziel**: Dry-run erfolgreich

4. **Subtask 1.4: Integration & Dokumentation (0.5 days)**
   - [ ] Database Config in `backend/app/config.py`
   - [ ] Connection Pooling (SQLAlchemy Pool)
   - [ ] Environment Variables dokumentiert
   - [ ] Migration in GitHub Actions
   - [ ] README mit PostgreSQL Setup aktualisiert

## Implementation Details

### Files zu erstellen/ändern:
```
backend/
├── scripts/
│   ├── setup_postgresql.py      # ✅ Erstellt
│   └── migrate_to_postgresql.py # ✅ Erstellt
├── tests/database/
│   └── test_postgresql_migration.py # ✅ Erstellt
├── app/
│   ├── config.py               # Ändern: PostgreSQL Config
│   └── database.py             # Ändern: Connection Pooling
├── alembic/versions/           # Neue Migrations-Scripts
├── .env.example                # Ändern: PostgreSQL URL
└── requirements.txt            # Ändern: psycopg2-binary
```

### PostgreSQL Connection String:
```
postgresql://baluhost_user:baluhost_password@localhost:5432/baluhost
# oder für Production
postgresql+asyncpg://user:pass@host:5432/baluhost
```

## Best Practices
- ✅ TDD: Tests ZUERST schreiben
- ✅ Feature Branch: `feat/postgresql-migration`
- ✅ Dry-run: Erst im Test-Environment
- ✅ Backup: Automatisches SQLite Backup vor Migration
- ✅ Rollback: Alte Datenbank bleibt erhalten
- ✅ Verifizierung: Row Count & Checksum Vergleich
- ✅ Dokumentation: Alembic Migrations dokumentieren

## Testing Strategy
```bash
# 1. Setup PostgreSQL
docker-compose -f deployment/docker-compose.yml up -d

# 2. Run tests
cd backend
python -m pytest tests/database/test_postgresql_migration.py -v

# 3. Dry run
python scripts/migrate_to_postgresql.py --verify --backup

# 4. Integration test
python -m pytest tests/ -v

# 5. Verify
select count(*) from users;  # PostgreSQL CLI
```

## Success Criteria
- Alle 4 Subtasks abgeschlossen
- 100% Test Coverage für PostgreSQL Code
- Migration kann reversible durchgeführt werden
- Keine Datenverluste
- Production-Ready Configuration

## Links
- [PHASE1_ACTION_PLAN.md](../../PHASE1_ACTION_PLAN.md)
- [PostgreSQL Docs](https://www.postgresql.org/docs/)
- [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/)
```

---

## Issue 2: Security Hardening

```markdown
# [CRITICAL] Task 2: Security Hardening (3-4 days)

## Description
Implementiere Security Best Practices für Production.

## Acceptance Criteria
- [ ] Input Validation auf allen API-Endpoints
- [ ] File Validation (Type, Size, Extensions)
- [ ] SQL Injection Prevention (Parametrized Queries)
- [ ] XSS Prevention (Content Security Policy)
- [ ] CSRF Protection (Token-basiert)
- [ ] Rate Limiting implementiert
- [ ] Security Headers gesetzt
- [ ] Authentication Review durchgeführt
- [ ] Authorization Checks komplett
- [ ] Error Messages sicher (keine Stack Traces)
- [ ] OWASP Top 10 Review durchgeführt
- [ ] Security Tests geschrieben

## Tasks
1. **Subtask 2.1: Input Validation (1 day)**
   - [ ] `backend/app/security/validators.py`
   - [ ] Email Validation
   - [ ] Password Strength Check
   - [ ] File Name Validation
   - [ ] Path Traversal Prevention
   - [ ] Unit Tests für alle Validators

2. **Subtask 2.2: File Security (1 day)**
   - [ ] `backend/app/security/file_validator.py`
   - [ ] File Type Check (Magic Numbers, nicht Extension!)
   - [ ] File Size Limits
   - [ ] Malware Detection (optional: ClamAV Integration)
   - [ ] Quarantine für verdächtige Dateien
   - [ ] Tests für File Upload Security

3. **Subtask 2.3: Security Middleware & Headers (0.5 days)**
   - [ ] `backend/app/middleware/security_headers.py`
   - [ ] CORS Configuration
   - [ ] Security Headers (X-Content-Type-Options, X-Frame-Options, etc.)
   - [ ] HSTS Header
   - [ ] Content-Security-Policy Header
   - [ ] Tests für Security Headers

4. **Subtask 2.4: Error Handling & Logging (0.5 days)**
   - [ ] Error Responses ohne Stack Traces
   - [ ] Structured Error Logging
   - [ ] Sensitive Data Filtering in Logs
   - [ ] Audit Logging für Security Events
   - [ ] Tests für Error Handling

5. **Subtask 2.5: Authentication & Authorization (0.5 days)**
   - [ ] JWT Token Validation Review
   - [ ] Token Expiration & Refresh
   - [ ] Permission Checks auf allen Endpoints
   - [ ] Rate Limiting für Auth Endpoints
   - [ ] Brute Force Protection

6. **Subtask 2.6: Production Configuration (0.5 days)**
   - [ ] Environment-spezifische Configs
   - [ ] Secrets Management
   - [ ] Debug Mode ausgeschaltet in Prod
   - [ ] HTTPS/TLS erzwungen
   - [ ] Security Checklist abgarbeitet

## Best Practices
- ✅ OWASP Top 10: https://owasp.org/www-project-top-ten/
- ✅ Defense in Depth: Mehrschichtige Validierung
- ✅ Fail Secure: Errors schließen zu Ablehnung, nicht Zulass
- ✅ Least Privilege: Minimale Permissions
- ✅ Logging: Alle Security-Events geloggt
- ✅ Testing: Penetration Tests für kritische Paths

## Testing Strategy
```bash
# Security Unit Tests
python -m pytest tests/security/ -v

# Input Validation Tests
python -m pytest tests/security/test_validators.py -v

# File Security Tests
python -m pytest tests/security/test_file_validator.py -v

# Security Integration Tests
python -m pytest tests/security/test_security_integration.py -v

# OWASP Checklist
# siehe SECURITY_CHECKLIST.md
```

## Success Criteria
- Alle OWASP Top 10 Items adressiert
- 95%+ Test Coverage für Security Code
- Zero Critical Vulnerabilities in Scan
- Security Review durchgeführt
- Dokumentation komplett
```

---

## Issue 3: Structured Logging & Monitoring

```markdown
# [CRITICAL] Task 3: Structured Logging & Monitoring (3-4 days)

## Description
Implementiere produktions-ready Logging mit JSON strukturiert und Monitoring.

## Acceptance Criteria
- [ ] JSON Structured Logging implementiert
- [ ] Log Levels konfigurierbar
- [ ] Context Tracking (Request ID, User ID)
- [ ] Performance Metrics erfasst
- [ ] Error Tracking mit Stack Traces
- [ ] Health Check Endpoint implementiert
- [ ] Metrics für Monitoring vorbereitet
- [ ] Logging in Dokumentation

## Tasks
1. **Subtask 3.1: JSON Logger Setup (1 day)**
   - [ ] `backend/app/logging/logger.py`
   - [ ] JSON Formatter für alle Logs
   - [ ] Structured Fields (timestamp, level, service, etc.)
   - [ ] File & Console Output
   - [ ] Log Rotation
   - [ ] Tests für Logger

2. **Subtask 3.2: Error Handling (1 day)**
   - [ ] `backend/app/errors/exceptions.py`
   - [ ] Custom Exception Classes
   - [ ] Proper Error Codes (HTTP Status)
   - [ ] Error Messages (User-safe)
   - [ ] Stack Trace Logging (intern nur)
   - [ ] Error Serialization
   - [ ] Tests für Error Handling

3. **Subtask 3.3: Health Checks & Metrics (1 day)**
   - [ ] `backend/app/monitoring/health_check.py`
   - [ ] GET /health Endpoint
   - [ ] Database Health Check
   - [ ] Disk Space Check
   - [ ] API Response Times
   - [ ] Error Rate Tracking
   - [ ] Tests für Health Checks

4. **Subtask 3.4: Request Context & Tracing (0.5 days)**
   - [ ] Request ID Generation
   - [ ] User Context Propagation
   - [ ] Execution Time Tracking
   - [ ] Request/Response Logging
   - [ ] Correlation across Services

5. **Subtask 3.5: Documentation (0.5 days)**
   - [ ] Logging Best Practices
   - [ ] How to interpret Logs
   - [ ] Monitoring Setup Guide
   - [ ] Health Check Endpoints dokumentiert
   - [ ] Metrics Schema dokumentiert

## File Structure
```
backend/
├── app/
│   ├── logging/
│   │   ├── __init__.py
│   │   ├── logger.py          # ✅ JSON Logger
│   │   ├── formatters.py       # JSON Formatter
│   │   └── filters.py          # Context Filters
│   ├── errors/
│   │   ├── __init__.py
│   │   ├── exceptions.py       # Custom Exceptions
│   │   └── handlers.py         # Error Handlers
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── health_check.py     # Health Endpoints
│   │   ├── metrics.py          # Metrics Collector
│   │   └── middleware.py       # Metrics Middleware
│   └── middleware/
│       ├── __init__.py
│       ├── request_logging.py  # Request Context
│       └── error_handling.py   # Error Handling
├── tests/
│   └── monitoring/
│       ├── test_logger.py
│       ├── test_health_check.py
│       └── test_error_handling.py
└── docs/
    └── LOGGING_GUIDE.md        # Logging Documentation
```

## Example JSON Log Output
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "service": "baluhost-backend",
  "request_id": "req-abc123def456",
  "user_id": "user-123",
  "action": "file_upload",
  "status": "success",
  "duration_ms": 245,
  "file_size": 1024000,
  "message": "File uploaded successfully"
}
```

## Success Criteria
- JSON Logs für alle wichtigen Events
- Monitoring Ready (Prometheus, CloudWatch, etc.)
- Health Checks für automatisches Monitoring
- Performance Metrics erfasst
- Error Tracking implementiert
```

---

## Issue 4: Deployment Documentation

```markdown
# [CRITICAL] Task 4: Deployment Documentation (3-4 days)

## Description
Erstelle umfassende Deployment-Dokumentation für Linux/NAS und Cloud.

## Acceptance Criteria
- [ ] Linux Deployment Guide komplett
- [ ] Docker Containerization Ready
- [ ] Kubernetes/AKS Beispiele vorhanden
- [ ] Systemd Service Files erstellt
- [ ] Nginx Reverse Proxy Config erstellt
- [ ] Database Backup Strategy dokumentiert
- [ ] SSL/TLS Setup dokumentiert
- [ ] Production Checklist erstellt
- [ ] Disaster Recovery Plan dokumentiert
- [ ] Monitoring Setup Guide erstellt

## Tasks
1. **Subtask 4.1: Linux Deployment Guide (1 day)**
   - [ ] `docs/DEPLOYMENT_LINUX.md`
   - [ ] Requirements & Prerequisites
   - [ ] Step-by-Step Installation
   - [ ] System Service Setup (systemd)
   - [ ] Nginx Configuration
   - [ ] SSL/TLS Setup mit Let's Encrypt
   - [ ] Firewall Configuration
   - [ ] Backup Strategy

2. **Subtask 4.2: Docker Setup (1 day)**
   - [ ] `deployment/docker/Dockerfile`
   - [ ] Multi-stage Build
   - [ ] Alpine Linux Base (minimal)
   - [ ] Security: Non-root User
   - [ ] Health Checks
   - [ ] `deployment/docker/docker-compose.yml`
   - [ ] Production & Development Configurations

3. **Subtask 4.3: Kubernetes/AKS Setup (0.5 days)**
   - [ ] `deployment/k8s/`
   - [ ] Deployment Manifests
   - [ ] Service & Ingress
   - [ ] ConfigMaps & Secrets
   - [ ] PersistentVolumes für Daten
   - [ ] Example for Azure AKS

4. **Subtask 4.4: Reverse Proxy & TLS (0.5 days)**
   - [ ] `deployment/nginx/baluhost.conf`
   - [ ] Nginx Configuration
   - [ ] SSL/TLS Settings (A+ Rating)
   - [ ] Gzip Compression
   - [ ] Security Headers
   - [ ] Rate Limiting

5. **Subtask 4.5: Production Checklist (0.5 days)**
   - [ ] `docs/PRODUCTION_CHECKLIST.md`
   - [ ] Pre-Deployment Checks
   - [ ] Deployment Steps
   - [ ] Post-Deployment Verification
   - [ ] Rollback Procedure
   - [ ] Monitoring Setup

6. **Subtask 4.6: Disaster Recovery (0.5 days)**
   - [ ] `docs/DISASTER_RECOVERY.md`
   - [ ] Backup Strategy
   - [ ] Database Backup & Restore
   - [ ] File Backup Strategy
   - [ ] Recovery Procedures
   - [ ] RTO/RPO Targets

## Deployment Architecture
```
Internet
    ↓
Nginx (Reverse Proxy, TLS)
    ↓
FastAPI Backend (Gunicorn/Uvicorn)
    ↓
PostgreSQL Database
    ↓
File Storage
```

## Files zu erstellen
```
deployment/
├── docker/
│   ├── Dockerfile              # Backend Container
│   ├── docker-compose.yml      # Local/Dev Setup
│   ├── docker-compose.prod.yml # Production Setup
│   └── .dockerignore
├── k8s/
│   ├── deployment.yaml         # Kubernetes Deployment
│   ├── service.yaml            # Kubernetes Service
│   ├── ingress.yaml            # Kubernetes Ingress
│   ├── configmap.yaml          # Configuration
│   ├── secret.yaml             # Secrets (template)
│   └── pvc.yaml                # Persistent Volumes
├── nginx/
│   ├── baluhost.conf           # Main Config
│   ├── ssl-params.conf         # SSL Settings
│   └── rate-limiting.conf      # Rate Limiting
├── systemd/
│   ├── baluhost.service        # Backend Service
│   └── baluhost-backup.timer   # Backup Timer
└── scripts/
    ├── deploy.sh               # Deployment Script
    ├── backup.sh               # Backup Script
    └── restore.sh              # Restore Script

docs/
├── DEPLOYMENT_LINUX.md         # Linux Setup
├── DEPLOYMENT_DOCKER.md        # Docker Setup
├── DEPLOYMENT_K8S.md           # Kubernetes Setup
├── PRODUCTION_CHECKLIST.md     # Pre-Deploy Checks
└── DISASTER_RECOVERY.md        # Recovery Procedures
```

## Success Criteria
- Automated Deployment möglich
- Zero-Downtime Deployment vorbereitet
- Full Backup Strategy implementiert
- Production Monitoring Setup dokumentiert
- Team kann auf Prod deployen
```

---

## How to Use These Templates

1. **Kopiere den Markdown-Code**
2. **Erstelle neue GitHub Issues**
3. **Paste den Content**
4. **Assign an Team Member**
5. **Set as Part of Phase 1 Milestone**
6. **Link related issues**

---

## Phase 1 Timeline

```
Week 1:
  Mon-Tue: Task 1 (PostgreSQL Migration)
  Wed-Thu: Task 2 Early (Security Hardening)

Week 2:
  Mon-Tue: Task 2 Final + Task 3 Early
  Wed-Thu: Task 3 Final + Task 4 Early

Week 3:
  Mon-Tue: Task 4 Final
  Wed-Thu: Integration Testing & Fixes
  Fri: Code Review & Merge to main
```

## Success = Production Ready ✅

Nach Phase 1 ist BaluHost Production-Ready für:
- ✅ PostgreSQL Backend
- ✅ Security Best Practices
- ✅ Structured Monitoring
- ✅ Automated Deployment
