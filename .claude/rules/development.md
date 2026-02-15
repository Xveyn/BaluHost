# Development

## Common Commands

### Combined Development Start
```bash
# Starts both backend (port 3001) and frontend (port 5173)
python start_dev.py
```

### Backend
```bash
cd backend

# Install dependencies
pip install -e ".[dev]"

# Run server (dev mode with auto-reload)
uvicorn app.main:app --reload --port 3001

# Run tests
python -m pytest
python -m pytest tests/test_permissions.py -v  # Specific test

# Run TUI
python -m baluhost_tui
# or
baluhost-tui  # if installed
```

### Frontend
```bash
cd client

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Run tests
npm run test        # Unit tests (placeholder)
npm run test:e2e    # E2E tests (placeholder)
```

### Database Migrations
```bash
cd backend

# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Development Modes

### Dev Mode (`NAS_MODE=dev`)
- Enabled by default in `start_dev.py`
- Creates sandbox storage in `backend/dev-storage/` (2x5GB RAID1 simulated)
- Mock SMART data, RAID arrays, and system metrics
- Automatic seed data (admin/DevMode2024, user/User123)
- Windows-compatible (no Linux dependencies required)
- Mock VPN key generation (no `wg` command needed)

### Production Mode (`NAS_MODE=prod`)
- Real mdadm RAID commands
- Actual smartctl disk health data
- System-wide file access
- PostgreSQL database (recommended)

## Development Tips

1. **Always use dev mode** for local development (`python start_dev.py`)
2. **Check logs** in terminal where `start_dev.py` is running
3. **API testing**: Use Swagger UI at `http://localhost:3001/docs`
4. **Database inspection**: Use SQLite browser on `backend/baluhost.db`
5. **Reset dev environment**: `python backend/scripts/debug/reset_dev_storage.py`
6. **Test a specific feature**: Write pytest test, then implement feature (TDD)

## Common Issues & Solutions

**Backend won't start**: Check if port 3001 is already in use
**Frontend can't reach API**: Verify proxy config in `client/vite.config.ts`
**Permission denied on file operation**: Check file ownership in `.metadata.json`
**RAID commands fail**: Ensure dev mode is active or run on Linux with mdadm
**Tests fail**: Run `python -m pytest -v` to see detailed error messages
**Import errors**: Ensure virtual environment is activated and dependencies installed

## Documentation Structure

- `README.md` - Project overview, quick start
- `TECHNICAL_DOCUMENTATION.md` - Complete feature documentation (1600+ lines)
- `ARCHITECTURE.md` - System architecture and design decisions
- `TODO.md` - Roadmap and planned features
- `PRODUCTION_READINESS.md` - Production deployment checklist
- `docs/` - Feature-specific documentation (RAID, VPN, Mobile, etc.)
- `CONTRIBUTING.md` - Contribution guidelines
- `SECURITY.md` - Security policy
