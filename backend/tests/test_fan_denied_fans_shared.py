"""Der Kanalzustand gilt fuer alle Worker gleich (#568 Punkt 2).

`pwm_control` lebt im `_fan_cache` des jeweiligen Uvicorn-Workers, gesetzt wird
es aber nur von dem, der schreibt -- im Regelbetrieb also allein vom Primary.
Ohne eine gemeinsame Zeile melden die drei Follower fuer denselben Kanal weiter
`supported`, und das Badge in der Luefterkarte erscheint und verschwindet im
5-Sekunden-Poll, je nachdem welcher Worker antwortet.

Dieselbe Loesung wie fuer `has_write_permission` eine Ebene darueber (#552):
der Primary veroeffentlicht, alle lesen von dort.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.power.fan_runtime_store import (
    publish_write_permission,
    read_denied_fans,
    read_write_permission,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_ohne_zeile_ist_die_antwort_none(session_factory):
    """None heisst 'nichts veroeffentlicht' und ist ausdruecklich NICHT
    dasselbe wie 'kein Kanal betroffen' -- der Leser soll dann seine eigene
    Sicht behalten statt eine leere Menge als Tatsache zu nehmen."""
    with session_factory() as db:
        assert read_denied_fans(db) is None


def test_veroeffentlichte_kanaele_kommen_zurueck(session_factory):
    with session_factory() as db:
        assert publish_write_permission(db, False, {"nct6798:pwm2", "nct6798:pwm1"})
    with session_factory() as db:
        assert read_denied_fans(db) == {"nct6798:pwm1", "nct6798:pwm2"}


def test_eine_leere_menge_ist_eine_aussage(session_factory):
    """'Kein Kanal ist gesperrt' muss sich von 'nichts veroeffentlicht'
    unterscheiden lassen.

    Die Unterscheidung traegt auf der SCHREIBSEITE: None laesst die
    gespeicherte Liste unberuehrt (ein Aufrufer, der nur das Flag kennt, darf
    sie nicht loeschen), die leere Menge ersetzt sie. Auf der Leseseite ist sie
    seit der Umstellung auf Vereinigung ohne Wirkung -- get_status nimmt einen
    eigenen Befund ohnehin nicht mehr zurueck. Die urspruengliche Begruendung
    hier ("sonst koennte ein Follower einen veralteten Befund nie
    zuruecknehmen") galt nur fuer die verworfene Ersetzungs-Variante."""
    with session_factory() as db:
        publish_write_permission(db, False, {"nct6798:pwm1"})
    with session_factory() as db:
        publish_write_permission(db, True, set())
    with session_factory() as db:
        assert read_denied_fans(db) == set()


def test_none_laesst_die_liste_unberuehrt(session_factory):
    """Rueckwaertskompatibel: ein Aufrufer, der nur das Flag kennt, darf die
    veroeffentlichten Kanaele nicht versehentlich loeschen."""
    with session_factory() as db:
        publish_write_permission(db, False, {"nct6798:pwm1"})
    with session_factory() as db:
        publish_write_permission(db, True)
    with session_factory() as db:
        assert read_denied_fans(db) == {"nct6798:pwm1"}
        assert read_write_permission(db) is True


def test_unlesbarer_inhalt_wird_nicht_zur_aussage(session_factory):
    """Eine kaputte Zeile darf nicht als 'kein Kanal gesperrt' gelesen werden
    -- das waere ein gruenes Signal aus einem Fehlerfall."""
    from app.models.fans import FanRuntimeState

    with session_factory() as db:
        db.add(FanRuntimeState(id=1, has_write_permission=True,
                               denied_fan_ids="{kein gueltiges json"))
        db.commit()
    with session_factory() as db:
        assert read_denied_fans(db) is None


def test_ein_objekt_statt_einer_liste_wird_abgelehnt(session_factory):
    from app.models.fans import FanRuntimeState

    with session_factory() as db:
        db.add(FanRuntimeState(id=1, has_write_permission=True,
                               denied_fan_ids='{"a": 1}'))
        db.commit()
    with session_factory() as db:
        assert read_denied_fans(db) is None
