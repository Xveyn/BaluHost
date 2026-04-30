"""Tests for GpuPowerConfig persistence."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.gpu_power import GpuPowerConfigDb
from app.schemas.gpu_power import GpuPowerConfig
from app.services.power.gpu import config_store


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(config_store, "SessionLocal", Session)
    yield Session


def test_load_returns_defaults_when_empty(in_memory_db):
    cfg = config_store.load_gpu_power_config()
    assert cfg.enabled is False
    assert cfg.idle_window_seconds == 30


def test_save_then_load_roundtrip(in_memory_db):
    cfg = GpuPowerConfig(enabled=True, idle_window_seconds=60, usage_threshold_percent=10.0)
    config_store.save_gpu_power_config(cfg)
    loaded = config_store.load_gpu_power_config()
    assert loaded.enabled is True
    assert loaded.idle_window_seconds == 60
    assert loaded.usage_threshold_percent == 10.0


def test_save_overwrites_existing(in_memory_db):
    config_store.save_gpu_power_config(GpuPowerConfig(idle_window_seconds=60))
    config_store.save_gpu_power_config(GpuPowerConfig(idle_window_seconds=120))
    loaded = config_store.load_gpu_power_config()
    assert loaded.idle_window_seconds == 120
