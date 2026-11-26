"""Shared fixtures for tests/services."""
import pytest


@pytest.fixture
def power_tables_in_global_db():
    """
    Ensure the multi-worker power tables exist in the global SessionLocal-backed DB.

    Tests that use this fixture construct ``PowerManagerService`` directly and bypass
    ``conftest.db_session``; the manager calls ``SessionLocal()`` for DB-backed
    helpers (runtime state, demands), so we need the schema available there.
    Cleans up after each test so state does not leak between cases.
    """
    from sqlalchemy import inspect

    from app.core.database import engine
    from app.models.power import PowerCommand, PowerDemand, PowerDemandLog, PowerRuntimeState

    tables = [
        PowerRuntimeState.__table__,
        PowerDemand.__table__,
        PowerCommand.__table__,
        PowerDemandLog.__table__,
    ]

    inspector = inspect(engine)
    created = [t for t in tables if not inspector.has_table(t.name)]
    for table in created:
        table.create(bind=engine, checkfirst=True)

    # Seed singleton runtime-state row
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        existing = db.query(PowerRuntimeState).filter(PowerRuntimeState.id == 1).first()
        if existing is None:
            db.add(PowerRuntimeState(id=1, current_profile="idle"))
            db.commit()
    finally:
        db.close()

    yield

    db = Session()
    try:
        db.query(PowerDemand).delete()
        db.query(PowerDemandLog).delete()
        db.query(PowerCommand).delete()
        db.query(PowerRuntimeState).delete()
        db.add(PowerRuntimeState(id=1, current_profile="idle"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
