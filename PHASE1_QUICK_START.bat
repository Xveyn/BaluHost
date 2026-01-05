@echo off
REM =========================================
REM BaluHost Phase 1 - Quick Start Script
REM Best Practices Execution Checklist
REM =========================================

echo.
echo ================================
echo   BaluHost Phase 1 Quick Start
echo ================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python nicht gefunden!
    pause
    exit /b 1
)

REM Check Docker (optional, aber empfohlen)
docker --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Docker nicht gefunden. PostgreSQL-Setup wird schwieriger.
    echo Installiere Docker Desktop fur einfaches Setup.
    pause
)

echo.
echo [PHASE 1] PostgreSQL Migration
echo ================================
echo.
echo Step 1: Setup PostgreSQL
echo.
echo Option A (mit Docker - empfohlen):
echo   docker-compose -f deployment/docker-compose.yml up -d
echo.
echo Option B (lokal installiert):
echo   createdb baluhost (macOS/Linux)
echo   CREATE DATABASE baluhost; (Windows)
echo.

set /p continue="PostgreSQL ist ready? (y/n): "
if /i not "%continue%"=="y" (
    echo Bitte PostgreSQL zuerst aufsetzen.
    pause
    exit /b 1
)

echo.
echo Step 2: Tests ausfuhren (TDD Approach)
echo.
cd backend
echo Running PostgreSQL migration tests...
python -m pytest tests/database/test_postgresql_migration.py -v

if errorlevel 1 (
    echo ERROR: Tests fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo Step 3: Setup PostgreSQL Skript ausfuhren
echo.
python scripts/setup_postgresql.py

echo.
echo [SUCCESS] Phase 1 Step 1 Complete!
echo.
echo Next steps:
echo 1. Erstelle GitHub Issues fur Tasks 2-4
echo 2. Starte mit Task 2: Security Hardening
echo 3. Folge dem PHASE1_ACTION_PLAN.md
echo.

pause
