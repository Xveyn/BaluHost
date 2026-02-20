
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Detailed rules are in `.claude/rules/` (automatically loaded by Claude Code).

## Project Overview

BaluHost is a full-stack NAS management platform with multiple components:
- **Backend**: Python FastAPI (primary), located in `backend/`
- **Frontend**: React + TypeScript + Vite (Web UI), located in `client/`
- **TUI**: Terminal UI (Textual), located in `backend/baluhost_tui/`
- **BaluDesk**: Desktop sync client → [Xveyn/BaluDesk](https://github.com/Xveyn/BaluDesk)
- **BaluApp**: Android app → [Xveyn/BaluApp](https://github.com/Xveyn/BaluApp)

**Current Production Status**: ~99% production-ready, deployed in production (Jan 2026). PostgreSQL, security hardening, and deployment complete.

## Architecture

```
backend/
├── app/
│   ├── api/routes/        # API endpoints
│   ├── services/          # Business logic
│   ├── schemas/           # Pydantic models
│   ├── models/            # SQLAlchemy ORM models
│   └── core/config.py     # Configuration
├── baluhost_tui/          # Terminal UI application
├── tests/                 # Pytest tests (68 files, 1121 test functions)
└── pyproject.toml         # Dependencies

client/
├── src/
│   ├── pages/             # Page components
│   ├── components/        # Reusable components
│   ├── api/               # API client modules
│   ├── lib/api.ts         # Base API client (axios)
│   └── hooks/             # Custom React hooks
└── vite.config.ts
```

## Quick Reference: Finding Things

**Authentication logic**: `backend/app/services/auth.py` + `backend/app/api/deps.py`
**File upload handling**: `backend/app/services/files.py:upload_file()`
**RAID status**: `backend/app/services/raid.py`
**Frontend API client**: `client/src/lib/api.ts`
**Dashboard page**: `client/src/pages/Dashboard.tsx`
**Database models**: `backend/app/models/`
**API schemas**: `backend/app/schemas/`
**Tests**: `backend/tests/`
**Fan control**: `backend/app/services/fan_control.py`
**Power management**: `backend/app/services/power_manager.py`
**Monitoring orchestrator**: `backend/app/services/monitoring/orchestrator.py`
**Service status**: `backend/app/services/service_status.py`
**Network discovery**: `backend/app/services/network_discovery.py`
**Scheduler service**: `backend/app/services/scheduler_service.py`
**Scheduler Dashboard**: `client/src/pages/SchedulerDashboard.tsx`

## Contact & Support

- **Issues**: GitHub Issues (repository URL needed)
- **Documentation**: See `docs/` directory
- **Maintainer**: Xveyn
- **Version**: 1.8.2 (as of Feb 2026)
