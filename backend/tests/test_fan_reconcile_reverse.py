"""Der Rueckweg: stabile Kennung -> hwmon-indiziert (#585).

Ausgangslage ist die auf BaluNode am 2026-09-07 gemessene Datenlage: vier
aktive Zeilen in stabiler Form, dazu zwei Generationen deaktivierter
hwmon-Zeilen aus frueheren Laeufen des Hinwegs (#532).

Der geprueft Fall ist der, den es dort bisher nicht gab: der Scan bildet fuer
den nct6798 keine stabile Kennung mehr und liefert wieder hwmon2_pwmN. Ohne
den Rueckweg fiele die Anlage-Schleife auf die deaktivierte Altzeile zurueck
und der Luefter bliebe ungeregelt -- ohne Logzeile und ohne Zeichen in der
Oberflaeche.
"""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import (
    CompositeTempSensor,
    FanConfig,
    FanScheduleEntry,
    TempSensorLabel,
)
from app.services.power.fan_reconcile import (
    ChipFacts,
    UnstableChip,
    reconcile_fan_identities,
    reconcile_unstable_identities,
    split_legacy_fan_id,
)

NCT_INSTABIL = UnstableChip(
    hwmon_name="hwmon2",
    prefix="nct6798",
    pwm_channels=frozenset({1, 2, 3, 7}),
    temp_channels=frozenset({1, 2, 6}),
    ambiguous=False,
)
CHIPS = {"nct6798": NCT_INSTABIL}


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# (fan_id, name, temp_sensor_id, is_active, updated_at)
ROWS = [
    ("hwmon2_pwm1", "nct6798 PWM1", "hwmon:hwmon3_temp6", False, "2026-09-05T23:29:01"),
    ("hwmon2_pwm2", "nct6798 PWM2", "hwmon:hwmon3_temp6", False, "2026-09-05T23:29:01"),
    ("hwmon5_pwm1", "nct6798 PWM1", "hwmon:hwmon3_temp6", False, "2026-09-05T23:29:01"),
    ("nct6798-isa-0290:pwm1", "nct6798 PWM1",
     "hwmon:nct6798-isa-0290:temp6", True, "2026-09-06T19:02:07"),
    ("nct6798-isa-0290:pwm2", "nct6798 PWM2",
     "hwmon:k10temp-pci-00c3:temp1", True, "2026-09-06T19:02:07"),
    ("nct6798-isa-0290:pwm3", "nct6798 PWM3",
     "hwmon:nct6798-isa-0290:temp1", True, "2026-09-05T23:29:01"),
    ("nct6798-isa-0290:pwm7", "nct6798 PWM7",
     "hwmon:nct6798-isa-0290:temp1", True, "2026-09-05T23:29:01"),
    ("amdgpu-pci-0300:pwm1", "amdgpu PWM1", None, True, "2026-09-06T16:44:27"),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for fan_id, name, sensor, aktiv, updated in ROWS:
        session.add(FanConfig(fan_id=fan_id, name=name, mode="auto",
                              temp_sensor_id=sensor, is_active=aktiv,
                              updated_at=_dt(updated)))
    session.commit()
    yield session
    session.close()


def _zeile(db, fan_id):
    return db.execute(
        select(FanConfig).where(FanConfig.fan_id == fan_id)).scalar_one_or_none()


def _aktiv(db):
    return {r.fan_id for r in db.execute(
        select(FanConfig).where(FanConfig.is_active.is_(True))).scalars()}


# --- Der Kern ---------------------------------------------------------------


def test_die_stabile_zeile_kommt_unter_der_heutigen_kennung_zurueck(db):
    bericht = reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    zeile = _zeile(db, "hwmon2_pwm1")
    assert zeile is not None
    assert zeile.is_active is True
    assert zeile.legacy_fan_id == "nct6798-isa-0290:pwm1"
    assert ("nct6798-isa-0290:pwm1", "hwmon2_pwm1") in bericht.readopted


def test_der_kanal_ist_hinterher_geregelt_statt_stillgelegt(db):
    """Die Aussage von #585 in einem Satz: vorher traegt die Zeile unter der
    heutigen Kennung is_active=False -- der Regelkreis steigt bei
    `not config.is_active` aus (fan_control.py:1160) --, hinterher ist der
    Kanal aktiv.

    Welcher Weg dorthin fuehrt, laesst dieser Test offen, und das ist
    Absicht: im Normalfall gewinnt die stabile Zeile, ist ohnehin aktiv und
    bringt ihre Aktivitaet mit der Umbenennung mit. Die ausdrueckliche
    Reaktivierung greift nur, wenn die Altzeile den Rangvergleich gewinnt --
    dafuer gibt es weiter unten einen eigenen Test."""
    vorher = _zeile(db, "hwmon2_pwm1")
    assert vorher.is_active is False

    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert _zeile(db, "hwmon2_pwm1").is_active is True


def test_die_verdraengte_altzeile_bleibt_erhalten_und_inaktiv(db):
    """Loeschen ist Nicht-Ziel -- schon in #532, hier unveraendert. Die
    Zielkennung muss aber frei werden, sonst halten zwei Zeilen denselben
    fan_id und der Unique-Index schlaegt beim Commit zu."""
    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert db.query(FanConfig).count() == len(ROWS)
    verdraengt = [r for r in db.execute(select(FanConfig)).scalars()
                  if r.fan_id.startswith("hwmon2_pwm1#legacy")]
    assert len(verdraengt) == 1
    assert verdraengt[0].is_active is False


def test_alle_gescannten_kanaele_kommen_zurueck(db):
    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert _aktiv(db) == {"hwmon2_pwm1", "hwmon2_pwm2", "hwmon2_pwm3",
                          "hwmon2_pwm7", "amdgpu-pci-0300:pwm1"}


# --- Sensoren: ohne sie verschoebe der Rueckweg den Fehler nur --------------


def test_der_sensor_desselben_chips_wird_mitgenommen(db):
    """Bliebe er auf der stabilen Kennung stehen, lieferte get_temp() None --
    und seit #534 Punkt 2 gaebe der Regelkreis den Kanal nach 300 s an die
    Board-Automatik ab. Der Rueckweg haette den Fehler dann nur verschoben."""
    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert _zeile(db, "hwmon2_pwm1").temp_sensor_id == "hwmon:hwmon2_temp6"


def test_der_sensor_eines_fremden_chips_bleibt_unberuehrt(db):
    """k10temp ist von der Instabilitaet des nct6798 nicht betroffen."""
    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert _zeile(db, "hwmon2_pwm2").temp_sensor_id == "hwmon:k10temp-pci-00c3:temp1"


def test_ein_nicht_gescannter_temperaturkanal_wird_nicht_erfunden(db):
    """temp9 gibt es im Scan nicht -- eine Zuordnung waere geraten."""
    chips = {"nct6798": UnstableChip(
        hwmon_name="hwmon2", prefix="nct6798",
        pwm_channels=frozenset({1}), temp_channels=frozenset({1}),
        ambiguous=False)}
    zeile = _zeile(db, "nct6798-isa-0290:pwm1")
    zeile.temp_sensor_id = "hwmon:nct6798-isa-0290:temp9"
    db.commit()

    reconcile_unstable_identities(db, chips=chips)
    db.commit()

    assert _zeile(db, "hwmon2_pwm1").temp_sensor_id == "hwmon:nct6798-isa-0290:temp9"


def test_labels_und_composites_ziehen_mit(db):
    db.add(TempSensorLabel(sensor_id="hwmon:nct6798-isa-0290:temp6",
                           custom_label="Gehaeuse hinten"))
    db.add(CompositeTempSensor(
        id="comp1", name="Mittelwert", function="avg",
        source_ids_json=json.dumps(["hwmon:nct6798-isa-0290:temp1",
                                    "hwmon:k10temp-pci-00c3:temp1"])))
    db.commit()

    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    label = db.execute(select(TempSensorLabel)).scalar_one()
    assert label.sensor_id == "hwmon:hwmon2_temp6"
    assert label.legacy_sensor_id == "hwmon:nct6798-isa-0290:temp6"

    composite = db.execute(select(CompositeTempSensor)).scalar_one()
    assert json.loads(composite.source_ids_json) == [
        "hwmon:hwmon2_temp1", "hwmon:k10temp-pci-00c3:temp1"]


# --- Die Wachen: im Zweifel geschieht nichts -------------------------------


def test_zwei_chips_desselben_praefix_werden_nicht_zugeordnet(db):
    """Ihre hwmon-Indizes koennen ueber Boots tauschen -- dieselbe Regel, mit
    der derive_all() Duplikate fuer instabil erklaert."""
    chips = {"nct6798": UnstableChip(
        hwmon_name="hwmon2", prefix="nct6798",
        pwm_channels=frozenset({1}), temp_channels=frozenset({6}),
        ambiguous=True)}

    bericht = reconcile_unstable_identities(db, chips=chips)
    db.commit()

    assert bericht.readopted == []
    assert _zeile(db, "nct6798-isa-0290:pwm1").fan_id == "nct6798-isa-0290:pwm1"
    assert _zeile(db, "hwmon2_pwm1").is_active is False


def test_ohne_lesbaren_chipnamen_wird_nichts_zugeordnet(db):
    """hwmon/name war unlesbar -- "Unknown" waere ueber Chips hinweg
    mehrdeutig und traefe irgendeine Zeile."""
    chips = {"Unknown": UnstableChip(
        hwmon_name="hwmon2", prefix="Unknown",
        pwm_channels=frozenset({1}), temp_channels=frozenset(),
        ambiguous=False)}

    assert reconcile_unstable_identities(db, chips=chips).readopted == []
    assert _zeile(db, "hwmon2_pwm1").is_active is False


def test_zwei_passende_aktive_zeilen_werden_nicht_zugeordnet(db):
    """Zwei Chips desselben Praefix haben zwei stabile Zeilen hinterlassen.
    Welche zu hwmon2 gehoert, ist nicht entscheidbar."""
    db.add(FanConfig(fan_id="nct6798-isa-0a20:pwm1", name="nct6798 PWM1",
                     mode="auto", is_active=True,
                     updated_at=_dt("2026-09-06T19:02:07")))
    db.commit()

    bericht = reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert ("nct6798-isa-0290:pwm1", "hwmon2_pwm1") not in bericht.readopted
    assert _zeile(db, "hwmon2_pwm1").is_active is False


def test_eine_kanalnummer_wird_nicht_mit_ihrem_praefix_verwechselt(db):
    """":pwm1$" darf ":pwm11" nicht treffen -- sonst uebernaehme Kanal 1 die
    Zeile von Kanal 11."""
    db.add(FanConfig(fan_id="nct6798-isa-0290:pwm11", name="nct6798 PWM11",
                     mode="auto", is_active=True,
                     updated_at=_dt("2026-09-07T00:00:00")))
    db.commit()

    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert _zeile(db, "nct6798-isa-0290:pwm11") is not None
    assert _zeile(db, "hwmon2_pwm1").legacy_fan_id == "nct6798-isa-0290:pwm1"


def test_eine_inaktive_stabile_zeile_tritt_nicht_mehr_an(db):
    """Spiegel der Regel aus dem Hinweg: eine deaktivierte Zeile wurde in
    einem frueheren Lauf final entschieden. Liesse man sie erneut antreten,
    koennte sie per Ranggleichstand gewinnen und den Unique-Index verletzen --
    ohne dass eine einzige neue Information vorlaege.

    Folge: der Kanal faellt in den Restfall und wird gemeldet, statt still
    eine alte Zeile wiederzubeleben."""
    stabil = _zeile(db, "nct6798-isa-0290:pwm3")
    stabil.is_active = False
    db.commit()
    chips = {"nct6798": UnstableChip(
        hwmon_name="hwmon2", prefix="nct6798",
        pwm_channels=frozenset({3}), temp_channels=frozenset(),
        ambiguous=False)}

    bericht = reconcile_unstable_identities(db, chips=chips)
    db.commit()

    assert bericht.readopted == []
    assert _zeile(db, "nct6798-isa-0290:pwm3").is_active is False


# --- Der Restfall, den auch der Rueckweg nicht loest ------------------------


def test_ein_kanal_ohne_stabile_vorgaengerin_wird_gemeldet(db):
    """Variante A aus #585, hier als Restfall: der Luefter bleibt ungeregelt,
    aber es steht im Bericht und im Journal, warum."""
    db.add(FanConfig(fan_id="hwmon2_pwm4", name="nct6798 PWM4", mode="auto",
                     is_active=False, updated_at=_dt("2026-09-05T23:29:01")))
    db.commit()
    chips = {"nct6798": UnstableChip(
        hwmon_name="hwmon2", prefix="nct6798",
        pwm_channels=frozenset({4}), temp_channels=frozenset(),
        ambiguous=False)}

    bericht = reconcile_unstable_identities(db, chips=chips)
    db.commit()

    assert bericht.orphaned_inactive == ["hwmon2_pwm4"]
    assert _zeile(db, "hwmon2_pwm4").is_active is False


def test_ein_unbekannter_kanal_meldet_nichts(db):
    """Kein Eintrag, keine Zeile -- die Anlage-Schleife legt gleich eine an.
    Eine Warnung waere hier Rauschen."""
    chips = {"nct6798": UnstableChip(
        hwmon_name="hwmon9", prefix="nct6798",
        pwm_channels=frozenset({5}), temp_channels=frozenset(),
        ambiguous=False)}

    assert reconcile_unstable_identities(db, chips=chips).orphaned_inactive == []


# --- Zusammenspiel mit dem Hinweg ------------------------------------------


def test_rueckweg_und_hinweg_sind_zueinander_invers(db):
    """Erholt sich die Ableitung, fuehrt #532 die Zeile zurueck. Ohne diese
    Eigenschaft waere der Rueckweg eine Einbahnstrasse mit umgekehrtem
    Vorzeichen -- also derselbe Fehler noch einmal."""
    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()
    assert _zeile(db, "hwmon2_pwm1").is_active is True

    reconcile_fan_identities(
        db,
        chips={"nct6798": ChipFacts(key="nct6798-isa-0290",
                                    pwm_channels=frozenset({1, 2, 3, 7}),
                                    ambiguous=False)},
        sensor_map={"hwmon2_temp6": "hwmon:nct6798-isa-0290:temp6"},
        cpu_sensor_id="hwmon:k10temp-pci-00c3:temp1",
    )
    db.commit()

    zurueck = _zeile(db, "nct6798-isa-0290:pwm1")
    assert zurueck is not None
    assert zurueck.is_active is True
    assert zurueck.temp_sensor_id == "hwmon:nct6798-isa-0290:temp6"


def test_ein_zweiter_lauf_aendert_nichts(db):
    erster = reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()
    zweiter = reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert len(erster.readopted) == 4
    assert zweiter.readopted == []
    assert zweiter.deactivated == []


def test_verweise_ziehen_mit(db):
    """sync_fan_id und Zeitplaneintraege zeigen sonst ins Leere."""
    quelle = _zeile(db, "nct6798-isa-0290:pwm2")
    quelle.sync_fan_id = "nct6798-isa-0290:pwm1"
    db.add(FanScheduleEntry(fan_id="nct6798-isa-0290:pwm1", name="Nacht",
                            start_time="22:00", end_time="06:00",
                            curve_json="[]"))
    db.commit()

    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    assert _zeile(db, "hwmon2_pwm2").sync_fan_id == "hwmon2_pwm1"
    eintrag = db.execute(select(FanScheduleEntry)).scalar_one()
    assert eintrag.fan_id == "hwmon2_pwm1"


def test_die_juengere_zeile_gewinnt_auch_wenn_sie_die_altzeile_ist(db):
    """Der Rang entscheidet, nicht die Namensform -- dieselbe Regel wie auf
    dem Hinweg. Eine Altzeile, die neuer ist, traegt die aktuellere
    Nutzereinstellung."""
    alt = _zeile(db, "hwmon2_pwm1")
    alt.updated_at = _dt("2026-09-07T23:00:00")
    db.commit()

    reconcile_unstable_identities(db, chips=CHIPS)
    db.commit()

    gewinner = _zeile(db, "hwmon2_pwm1")
    assert gewinner.id == alt.id
    assert gewinner.is_active is True
    assert _zeile(db, "nct6798-isa-0290:pwm1") is None or \
        _zeile(db, "nct6798-isa-0290:pwm1").is_active is False


def test_split_legacy_fan_id():
    assert split_legacy_fan_id("hwmon2_pwm7") == (2, 7)
    assert split_legacy_fan_id("nct6798-isa-0290:pwm7") is None
    assert split_legacy_fan_id("") is None
