"""Smoke tests for GPU power DB models — verify schema and table creation."""
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.gpu_power import GpuPowerLog, GpuPowerConfigDb


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_gpu_power_log_table_exists(db_session):
    inspector = inspect(db_session.bind)
    assert "gpu_power_log" in inspector.get_table_names()


def test_gpu_power_log_columns(db_session):
    inspector = inspect(db_session.bind)
    cols = {c["name"] for c in inspector.get_columns("gpu_power_log")}
    assert {"id", "timestamp", "state", "previous_state", "reason", "source",
            "power_watts_at_transition"}.issubset(cols)


def test_gpu_power_config_table_exists(db_session):
    inspector = inspect(db_session.bind)
    assert "gpu_power_config" in inspector.get_table_names()


def test_gpu_power_log_insert(db_session):
    from datetime import datetime, timezone
    log = GpuPowerLog(
        timestamp=datetime.now(timezone.utc),
        state="standby",
        previous_state="active",
        reason="idle_window_elapsed",
        source=None,
        power_watts_at_transition=42.5,
    )
    db_session.add(log)
    db_session.commit()
    assert log.id is not None


def test_gpu_power_config_singleton_insert(db_session):
    cfg = GpuPowerConfigDb(id=1, config_json='{"enabled": true}')
    db_session.add(cfg)
    db_session.commit()
    assert cfg.id == 1
