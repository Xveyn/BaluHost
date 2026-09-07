"""Die Rechteanzeige kann wieder auf "kein Schreibrecht" zurueckfallen (#568 Punkt 1).

`_has_write_permission` wird an drei Stellen auf True gesetzt -- der Probe beim
Start und zwei erfolgreichen Write-Pfaden -- und von NIEMANDEM auf False. Ging
das Schreibrecht zur Laufzeit verloren, meldete `GET /api/fans/permissions`
weiter `ok`: die Bedienelemente blieben frei, jede Eingabe verpuffte, und der
Nutzer bekam keinen Hinweis.

PR #567 hatte das nicht behoben, sondern vereinheitlicht -- vorher haette ein
Worker-Wechsel im 5-Sekunden-Poll wenigstens zufaellig einen anderen Wert
gezeigt, danach waren alle vier Worker einig und alle vier falsch.

Der Stand wird jetzt aus den Kanalzustaenden abgeleitet, die set_pwm ohnehin
pflegt (NO_PERMISSION bei beobachtetem EACCES, zurueck auf SUPPORTED nach dem
naechsten erfolgreichen Write).
"""
import pytest

from app.schemas.fans import PwmControl
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _backend(*, geprueft: bool, kanaele: dict) -> LinuxFanControlBackend:
    backend = object.__new__(LinuxFanControlBackend)
    backend._has_write_permission = geprueft
    backend._fan_cache = kanaele
    return backend


def test_ohne_erfolgreiche_probe_bleibt_es_bei_false():
    """Die Probe beim Start ist weiterhin die Untergrenze: was nie
    beschreibbar war, wird es nicht durch Ableitung."""
    backend = _backend(geprueft=False, kanaele={
        "nct6798:pwm1": {"pwm_control": PwmControl.SUPPORTED},
    })
    assert backend.has_write_permission() is False


def test_ein_steuerbarer_kanal_genuegt():
    backend = _backend(geprueft=True, kanaele={
        "nct6798:pwm1": {"pwm_control": PwmControl.SUPPORTED},
        "nct6798:pwm2": {"pwm_control": PwmControl.NO_PERMISSION},
    })
    assert backend.has_write_permission() is True


def test_erst_wenn_jeder_steuerbare_kanal_gesperrt_ist_faellt_es_zurueck():
    """Der eigentliche Regressionstest: vorher blieb der Wert True, egal wie
    viele Kanaele EACCES gesehen hatten."""
    backend = _backend(geprueft=True, kanaele={
        "nct6798:pwm1": {"pwm_control": PwmControl.NO_PERMISSION},
        "nct6798:pwm2": {"pwm_control": PwmControl.NO_PERMISSION},
    })
    assert backend.has_write_permission() is False


def test_ein_firmware_kanal_zaehlt_nicht_mit():
    """Auf BaluNode ist genau ein Kanal firmware-verwaltet. Er wird nie
    geschrieben und darf die Aussage ueber die anderen nicht faerben --
    dieselbe Ueberlegung wie in der Probe beim Start (#552)."""
    backend = _backend(geprueft=True, kanaele={
        "amdgpu:pwm1": {"pwm_control": PwmControl.FIRMWARE_MANAGED},
        "nct6798:pwm1": {"pwm_control": PwmControl.NO_PERMISSION},
    })
    assert backend.has_write_permission() is False


def test_nur_firmware_kanaele_lassen_den_startwert_stehen():
    """Gibt es nichts Steuerbares, stellt sich die Frage nicht -- dann ist der
    Wert der Probe die beste vorhandene Aussage, nicht ein hergeleitetes
    False."""
    backend = _backend(geprueft=True, kanaele={
        "amdgpu:pwm1": {"pwm_control": PwmControl.FIRMWARE_MANAGED},
    })
    assert backend.has_write_permission() is True


def test_ohne_erkannte_luefter_bleibt_der_startwert():
    backend = _backend(geprueft=True, kanaele={})
    assert backend.has_write_permission() is True


def test_ein_kanal_ohne_angabe_gilt_als_steuerbar():
    """Der Cache traegt pwm_control erst nach dem Scan. Ein fehlender Wert
    darf nicht als Sperre gelesen werden."""
    backend = _backend(geprueft=True, kanaele={"nct6798:pwm1": {}})
    assert backend.has_write_permission() is True


@pytest.mark.asyncio
async def test_ein_erfolgreicher_write_holt_die_anzeige_zurueck(monkeypatch, tmp_path):
    """Die Gegenrichtung funktionierte schon vorher und muss es weiter tun:
    set_pwm setzt NO_PERMISSION nach einem erfolgreichen Write zurueck, und
    damit meldet die Ableitung wieder True."""
    pwm = tmp_path / "pwm1"
    pwm.write_text("128\n")
    backend = _backend(geprueft=True, kanaele={
        "nct6798:pwm1": {
            "pwm_control": PwmControl.NO_PERMISSION,
            "pwm_path": pwm,
            "pwm_enable_path": None,
            "last_write_error": "kein Schreibrecht",
        },
    })
    backend._write_backoff = {}
    backend._monotonic = lambda: 0.0
    assert backend.has_write_permission() is False

    async def _write(path, value):
        return True, None

    monkeypatch.setattr(backend, "_write_hwmon_file", _write, raising=False)

    await backend.set_pwm("nct6798:pwm1", 50)

    assert backend.has_write_permission() is True
