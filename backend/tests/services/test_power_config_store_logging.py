"""Auto-scaling config reload logs on change, not on every tick (#551).

The power monitor reloads the config every 5 s so a PUT on another worker
becomes visible - that reload stays. It used to log "Loaded auto-scaling config
from DB" at INFO each time: ~17k identical lines a day on BaluNode. Now INFO
only when the loaded config differs from the last one this process logged.
"""
import logging

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.power import PowerAutoScalingConfig
from app.services.power import config_store

LOGGER = "app.services.power.config_store"


@pytest.fixture
def store(monkeypatch, db_session):
    monkeypatch.setattr(
        config_store, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    )
    monkeypatch.setattr(config_store, "_last_logged_auto_scaling", None)
    return db_session


def _info_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]


def test_repeated_identical_loads_log_once(store, caplog):
    store.add(PowerAutoScalingConfig(id=1, enabled=False))
    store.commit()
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    for _ in range(5):
        config_store.load_auto_scaling_config()

    assert len(_info_lines(caplog)) == 1


def test_a_change_is_logged_again(store, caplog):
    store.add(PowerAutoScalingConfig(id=1, enabled=False))
    store.commit()
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    config_store.load_auto_scaling_config()
    row = store.get(PowerAutoScalingConfig, 1)
    row.enabled = True
    store.commit()
    config_store.load_auto_scaling_config()
    config_store.load_auto_scaling_config()

    lines = _info_lines(caplog)
    assert len(lines) == 2
    assert "enabled=True" in lines[1]


def test_missing_row_logs_defaults_once(store, caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    for _ in range(3):
        config_store.load_auto_scaling_config()

    assert len(_info_lines(caplog)) == 1
