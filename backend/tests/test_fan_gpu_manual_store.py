"""Der AMD-Manual-Mode-Vorzustand ueberlebt die Worker-Grenze (#411).

Er lag in einem modulweiten Dict in routes/fans.py -- bei vier Uvicorn-Workern
also vierfach getrennt. Landete das Einschalten auf Worker A und das
Ausschalten auf Worker B, fand dieser nichts und schrieb einen GERATENEN
Vorzustand zurueck:

    state = _gpu_manual_state.pop(fan_id, None)
    if state is None:
        state = AmdManualState(previous_level="auto", previous_pwm_enable=2)

Auf BaluNode steht `power_dpm_force_performance_level` auf **low**, nicht auf
auto (gemessen 2026-09-06). Das Raten haette dort eine bewusst gesetzte
Stromspar-Einstellung stillschweigend ueberschrieben -- und zwar in drei von
vier Faellen, weil nur einer der vier Worker den Vorzustand kennt.
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power.fan_gpu_manual import AmdManualState
from app.services.power.fan_gpu_manual_store import (
    remember_manual_state,
    take_manual_state,
)

FAN_ID = "amdgpu-pci-0300:pwm1"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _with_fan_row(session_factory):
    with session_factory() as db:
        db.add(FanConfig(fan_id=FAN_ID, name="amdgpu PWM1"))
        db.commit()


def test_remember_stores_the_measured_previous_state(session_factory):
    _with_fan_row(session_factory)

    with session_factory() as db:
        stored = remember_manual_state(
            db, FAN_ID, AmdManualState(previous_level="low", previous_pwm_enable=2)
        )

    assert stored is True
    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.gpu_manual_prev_level == "low"
    assert row.gpu_manual_prev_pwm_enable == 2


def test_take_returns_the_state_and_clears_it(session_factory):
    """Ein anderer Worker liest denselben Zustand -- und nimmt ihn weg.

    Das Leeren ist die eigentliche Zusage: bleibt der Wert stehen, gaebe ein
    zweites Abschalten ihn ein zweites Mal zurueck, obwohl inzwischen jemand
    anderes den Zustand gesetzt haben kann.
    """
    _with_fan_row(session_factory)
    with session_factory() as db:
        remember_manual_state(
            db, FAN_ID, AmdManualState(previous_level="low", previous_pwm_enable=2)
        )

    with session_factory() as db:
        state = take_manual_state(db, FAN_ID)

    assert state == AmdManualState(previous_level="low", previous_pwm_enable=2)

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.gpu_manual_prev_level is None
    assert row.gpu_manual_prev_pwm_enable is None


def test_take_without_a_recorded_state_returns_none(session_factory):
    """Kein Eintrag heisst None -- nicht ein geratener Vorzustand.

    Die Entscheidung, was dann passiert, gehoert an die Aufrufstelle und
    soll dort sichtbar sein statt hier still getroffen zu werden.
    """
    _with_fan_row(session_factory)

    with session_factory() as db:
        assert take_manual_state(db, FAN_ID) is None


def test_remember_reports_a_missing_fan_row(session_factory):
    """Ohne Konfigurationszeile gibt es keinen Ablageort -- und das muss der
    Aufrufer erfahren, statt den Vorzustand ins Leere zu schreiben."""
    with session_factory() as db:
        stored = remember_manual_state(
            db, FAN_ID, AmdManualState(previous_level="low", previous_pwm_enable=2)
        )

    assert stored is False


def test_a_partial_record_counts_as_no_record(session_factory):
    """Nur eine der beiden Spalten gefuellt -- etwa nach einem Eingriff von
    Hand -- ist kein verwertbarer Vorzustand."""
    _with_fan_row(session_factory)
    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
        row.gpu_manual_prev_level = "low"
        db.commit()

    with session_factory() as db:
        assert take_manual_state(db, FAN_ID) is None
