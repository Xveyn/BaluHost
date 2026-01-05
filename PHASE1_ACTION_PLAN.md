# BaluHost Phase 1: Production Readiness - Action Plan

## 🎯 Goal: Make BaluHost Production-Ready (Critical Phase)

**Timeline:** 2-3 weeks | **Team:** 1 senior backend dev | **Priority:** 🔴 CRITICAL

---

## 📋 Phase 1 Tasks (In Order)

### Task 1: PostgreSQL Migration Setup
**Effort:** 4-5 days | **Owner:** Backend Dev | **Status:** ⏳ Not Started

#### 1.1 Environment Setup
- [ ] Create PostgreSQL docker-compose.yml
- [ ] Setup local PostgreSQL instance
- [ ] Create production PostgreSQL backup strategy

#### 1.2 Database Migration Code
- [ ] Update Alembic configuration for PostgreSQL
- [ ] Create migration script: SQLite → PostgreSQL
- [ ] Add database connection pooling (SQLAlchemy)
- [ ] Implement transaction management
- [ ] Add database backup/restore scripts

#### 1.3 Testing
- [ ] Test migration on local data
- [ ] Test migration on test dataset
- [ ] Performance testing (queries, indexing)
- [ ] Data integrity validation

#### 1.4 Documentation
- [ ] Migration guide for users
- [ ] PostgreSQL setup guide (development)
- [ ] PostgreSQL setup guide (production)
- [ ] Backup/restore procedures

**Files to Create/Modify:**
```
backend/
├── migrations/
│   ├── versions/
│   │   └── XXXX_migrate_sqlite_to_postgresql.py (NEW)
│   └── env.py (MODIFY)
├── scripts/
│   ├── migrate_to_postgresql.py (NEW)
│   ├── backup_database.py (NEW)
│   └── restore_database.py (NEW)
├── database.py (MODIFY - add connection pooling)
└── requirements.txt (ADD psycopg2-binary)

docs/
└── POSTGRESQL_SETUP.md (NEW)
```

---

### Task 2: Security Hardening
**Effort:** 3-4 days | **Owner:** Backend Dev | **Status:** ⏳ Not Started

#### 2.1 Input Validation & Sanitization
- [ ] Audit all API endpoints for input validation
- [ ] Validate file paths (prevent path traversal)
- [ ] Validate file uploads (size, type, virus scan)
- [ ] Sanitize user input (XSS prevention)
- [ ] Validate email addresses

#### 2.2 Authentication & Authorization
- [ ] Review JWT token handling
- [ ] Implement token rotation
- [ ] Add session timeout handling
- [ ] Test password reset security
- [ ] Implement brute-force protection

#### 2.3 Database Security
- [ ] Review SQL queries for injection vulnerabilities
- [ ] Add prepared statements (already using Pydantic)
- [ ] Implement database encryption at rest
- [ ] Secure credential storage

#### 2.4 API Security
- [ ] Review CORS configuration
- [ ] Implement CSRF protection if needed
- [ ] Add request signing for sensitive operations
- [ ] Implement rate limiting on auth endpoints
- [ ] Add request validation on all endpoints

#### 2.5 Production Configuration
- [ ] Create security headers (Helmet for Node, or similar for FastAPI)
- [ ] Implement HSTS
- [ ] Add Content-Security-Policy headers
- [ ] Setup HTTPS/TLS requirements

**Files to Create/Modify:**
```
backend/
├── app/
│   ├── security/
│   │   ├── validators.py (NEW)
│   │   ├── input_sanitizer.py (NEW)
│   │   └── file_validator.py (NEW)
│   ├── middleware/
│   │   ├── security_headers.py (NEW)
│   │   └── csrf_protection.py (NEW)
│   └── main.py (MODIFY - add security middleware)
└── tests/
    └── security/ (NEW folder with security tests)

docs/
└── SECURITY_AUDIT_CHECKLIST.md (NEW)
```

---

### Task 3: Structured Logging & Error Handling
**Effort:** 3-4 days | **Owner:** Backend Dev | **Status:** ⏳ Not Started

#### 3.1 Logging Infrastructure
- [ ] Setup structured logging (JSON format)
- [ ] Implement log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- [ ] Add request/response logging
- [ ] Add performance monitoring
- [ ] Implement log rotation

#### 3.2 Error Handling
- [ ] Create custom exception classes
- [ ] Implement global error handler
- [ ] Add error tracking (Sentry or similar)
- [ ] Implement proper error responses (HTTP status codes)
- [ ] Add error logging with context

#### 3.3 Monitoring
- [ ] Health check endpoint (/health)
- [ ] Readiness check endpoint (/ready)
- [ ] Application metrics (requests, errors, latency)
- [ ] Database health checks

**Files to Create/Modify:**
```
backend/
├── app/
│   ├── logging/
│   │   ├── logger.py (NEW)
│   │   └── formatters.py (NEW)
│   ├── errors/
│   │   ├── exceptions.py (NEW)
│   │   └── handlers.py (NEW)
│   ├── monitoring/
│   │   ├── health_check.py (NEW)
│   │   └── metrics.py (NEW)
│   └── main.py (MODIFY - add middleware)
├── requirements.txt (ADD python-json-logger, sentry-sdk)
└── tests/
    └── monitoring/ (NEW)

docs/
└── LOGGING_MONITORING.md (NEW)
```

---

### Task 4: Deployment Documentation
**Effort:** 3-4 days | **Owner:** Backend Dev | **Status:** ⏳ Not Started

#### 4.1 Linux/NAS Deployment Guide
- [ ] Systemd service file
- [ ] Reverse proxy setup (Nginx)
- [ ] TLS/SSL certificate setup
- [ ] Environment configuration
- [ ] Firewall configuration
- [ ] Log file location & rotation

#### 4.2 Docker Setup
- [ ] Dockerfile for BaluHost backend
- [ ] docker-compose.yml with PostgreSQL
- [ ] Multi-stage build for optimization
- [ ] Health check configuration

#### 4.3 Production Checklist
- [ ] Pre-deployment verification steps
- [ ] Database backup before deployment
- [ ] Rollback procedures
- [ ] Monitoring setup
- [ ] Alerting setup

**Files to Create/Modify:**
```
deployment/
├── docker/
│   ├── Dockerfile (NEW)
│   ├── docker-compose.yml (NEW)
│   └── .dockerignore (NEW)
├── systemd/
│   └── baluhost.service (NEW)
├── nginx/
│   └── baluhost.conf (NEW)
├── ssl/
│   └── setup_letsencrypt.sh (NEW)
└── scripts/
    ├── deploy.sh (NEW)
    ├── rollback.sh (NEW)
    └── backup_before_deploy.sh (NEW)

docs/
├── DEPLOYMENT_GUIDE.md (NEW)
├── DOCKER_DEPLOYMENT.md (NEW)
├── NGINX_SETUP.md (NEW)
└── PRODUCTION_CHECKLIST.md (NEW)
```

---

## 🏗️ Implementation Strategy (Best Practices)

### 1️⃣ **Start with Tests**
Before modifying production code, write tests:

```bash
# Create test structure
cd backend
pytest tests/database/test_postgresql_migration.py
pytest tests/security/test_input_validation.py
pytest tests/monitoring/test_health_check.py
```

### 2️⃣ **Use Feature Flags**
Implement feature flags to toggle between SQLite and PostgreSQL during migration:

```python
# config.py
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")  # or "postgresql"

# database.py
if DATABASE_TYPE == "postgresql":
    SQLALCHEMY_DATABASE_URL = "postgresql://..."
else:
    SQLALCHEMY_DATABASE_URL = "sqlite:///./baluhost.db"
```

### 3️⃣ **Create Migration Scripts**
Create automated scripts for migration:

```bash
# Backup SQLite before migration
python scripts/backup_database.py

# Migrate data
python scripts/migrate_to_postgresql.py --source sqlite --target postgresql

# Verify data integrity
python scripts/verify_migration.py
```

### 4️⃣ **Document Everything**
For each change:
- Add docstrings
- Create migration guides
- Document configuration options
- Create troubleshooting guides

### 5️⃣ **Version Control Best Practices**
```bash
# Create feature branch for each task
git checkout -b feat/postgresql-migration
git checkout -b feat/security-hardening
git checkout -b feat/structured-logging
git checkout -b feat/deployment-docs

# Commit frequently with clear messages
git commit -m "feat: Add PostgreSQL support with connection pooling

- Implement SQLAlchemy connection pooling
- Add Alembic migrations for PostgreSQL
- Support both SQLite and PostgreSQL for transition
- Add database health checks"

# Create pull request for review before merging
```

### 6️⃣ **Testing Strategy**
```
Tests needed:
✅ Unit tests (individual functions)
✅ Integration tests (API endpoints)
✅ Security tests (input validation, authentication)
✅ Performance tests (database queries)
✅ Migration tests (SQLite → PostgreSQL)
```

---

## 📊 Progress Tracking

Create this checklist in GitHub Issues or Project:

```markdown
## Phase 1: Production Readiness

### Task 1: PostgreSQL Migration
- [ ] Setup PostgreSQL locally
- [ ] Update Alembic configuration
- [ ] Create migration scripts
- [ ] Write migration tests
- [ ] Document migration guide

### Task 2: Security Hardening
- [ ] Audit all endpoints
- [ ] Implement input validation
- [ ] Add security headers
- [ ] Create security tests
- [ ] Document security guide

### Task 3: Structured Logging
- [ ] Setup JSON logging
- [ ] Implement error handling
- [ ] Add health checks
- [ ] Create monitoring dashboard
- [ ] Document logging setup

### Task 4: Deployment Documentation
- [ ] Create deployment guide
- [ ] Setup Docker files
- [ ] Create Nginx configuration
- [ ] Write production checklist
- [ ] Document troubleshooting
```

---

## 🚀 Recommended Execution Order

### Week 1: Foundation
1. Setup PostgreSQL locally & in Docker
2. Create migration scripts
3. Write migration tests
4. Verify data integrity

### Week 2: Security & Monitoring
1. Audit API endpoints
2. Implement input validation
3. Setup structured logging
4. Add health checks

### Week 3: Documentation & Deployment
1. Create deployment guide
2. Setup Docker & Nginx
3. Create runbooks
4. Document production checklist

---

## 📚 Resources & References

### PostgreSQL Migration
- [SQLAlchemy PostgreSQL docs](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [Alembic migration guide](https://alembic.sqlalchemy.org/)

### Security Best Practices
- [OWASP Top 10](https://owasp.org/Top10/)
- [FastAPI Security docs](https://fastapi.tiangolo.com/tutorial/security/)

### Structured Logging
- [Python logging best practices](https://docs.python.org/3/howto/logging.html)
- [ELK Stack setup](https://www.elastic.co/what-is/elk-stack)

### Deployment
- [Docker best practices](https://docs.docker.com/develop/dev-best-practices/)
- [Nginx configuration](https://nginx.org/en/docs/)
- [systemd service files](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

## ✅ Success Criteria

**Phase 1 is complete when:**
- ✅ PostgreSQL migration tested and documented
- ✅ All critical security vulnerabilities fixed
- ✅ Structured logging in production
- ✅ Deployment guide complete and tested
- ✅ Health checks passing
- ✅ 90%+ test coverage for critical paths

---

**Created:** January 5, 2026  
**Status:** Ready to start  
**Next Step:** Create GitHub Issues for each task
