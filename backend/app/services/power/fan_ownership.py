"""Wem gehoert ein Luefterkanal -- BaluHost, der Board-Automatik, oder niemandem (#534 Punkt 1).

Reine Regeln: kein sysfs, keine Datenbank, kein Zustand. Dieselbe Bauform wie
`fan_restore.py`, aus demselben Grund -- die Entscheidung, einen Kanal
abzugeben, ist die sicherheitsrelevanteste in diesem Modul und soll ohne
Hardware pruefbar sein.

Warum ueberhaupt abgeben: BaluHost schaltet beim Start die Chip-Automatik ab
(`pwm_enable=1`). Kann es den Kanal danach nicht schreiben, regelt NIEMAND --
der Chip nicht, weil er abgeschaltet wurde, und BaluHost nicht, weil es nicht
darf. Die Rueckgabe stellt den Zustand her, der ohne BaluHost gegolten haette.
"""
from __future__ import annotations

from enum import Enum


class FanOwnership(str, Enum):
    """Wer den Kanal gerade regelt."""

    OWNED = "owned"
    """BaluHost. Der Normalfall."""

    RELEASED = "released"
    """Die Board-Automatik. Die Rueckgabe wurde geschrieben UND zurueckgelesen."""

    ABANDONED = "abandoned"
    """Niemand. Die Rueckgabe wurde versucht, der Write scheiterte aber oder
    blieb wirkungslos.

    Bei einem nicht schreibbaren Kanal ist das der wahrscheinliche Fall -- es
    ist derselbe Knoten mit denselben Rechten, an dem schon die Regelung
    scheitert. Der Zustand existiert als eigener, weil eine Oberflaeche, die
    hier "das Board regelt diesen Luefter" anzeigt, luegt.
    """


def should_release(
    *,
    at_write_cap: bool,
    ownership: FanOwnership,
    has_observed_restore_value: bool,
    is_firmware_managed: bool,
    is_active: bool,
) -> bool:
    """Ob dieser Kanal jetzt an die Board-Automatik zurueckgegeben werden soll.

    Als ZUSTAND formuliert, nicht als Flanke. Ein "erstmals am Deckel" haette
    pro Prozess hoechstens einmal gefeuert: das Backoff wird nur von einem
    erfolgreichen Write geleert, nach einer Wiederuebernahme ohne erfolgreichen
    Write steht der Zaehler also bereits am Deckel und wird nie wieder
    "erstmals" erreicht (#534).

    Args:
        at_write_cap: Das Write-Backoff dieses Kanals steht am Maximum -- mit
            den heutigen Konstanten der achte aufeinanderfolgende Fehlschlag.
            Erzwungene Writes (Nutzer, Notfall) zaehlen nicht mit hinein, sonst
            koennten acht erfolglose Klicks den Luefter abgeben.
        has_observed_restore_value: Es gibt einen SELBST GELESENEN
            pwm_enable-Wert (>= 2, vor dem ersten eigenen Write). Ohne ihn wird
            nicht zurueckgegeben -- ein geratener Treibermodus waere eine
            Annahme ueber fremde Hardware, und ein falsch geratener Wert
            stellte den Luefter still ab (#556).
        is_firmware_managed: Die Karte regelt ohnehin selbst; BaluHost hat den
            Kanal nie uebernommen, es gibt nichts zurueckzugeben (#480).
    """
    return at_write_cap and _abgabe_moeglich(
        ownership=ownership,
        has_observed_restore_value=has_observed_restore_value,
        is_firmware_managed=is_firmware_managed,
        is_active=is_active,
    )


def _abgabe_moeglich(
    *,
    ownership: FanOwnership,
    has_observed_restore_value: bool,
    is_firmware_managed: bool,
    is_active: bool,
) -> bool:
    """Die Wachen, die fuer JEDEN Abgabegrund gelten.

    Getrennt vom Ausloeser, damit ein zweiter Grund (#534 Punkt 2) sie nicht
    kopieren muss -- und damit er nicht `at_write_cap=True` an eine Funktion
    reichen muss, bei der es gar nicht um den Deckel geht.
    """
    if not is_active:
        return False
    if is_firmware_managed:
        return False
    if ownership is not FanOwnership.OWNED:
        return False
    return has_observed_restore_value


def ownership_after_release(release_succeeded: bool) -> FanOwnership:
    """Der Zustand nach einem Rueckgabeversuch.

    `release_to_board()` schreibt und LIEST ZURUECK; ein False heisst also
    nicht "Fehler beim Schreiben", sondern "der Wert liegt danach nicht an".
    Beides fuehrt zum selben Ergebnis: die Chip-Automatik ist nicht aktiv, und
    BaluHost regelt auch nicht mehr.
    """
    return FanOwnership.RELEASED if release_succeeded else FanOwnership.ABANDONED


def is_released(ownership: FanOwnership) -> bool:
    """Ob der Regelkreis diesen Kanal in Ruhe lassen soll.

    Gilt fuer BEIDE Freigabe-Zustaende: bei ABANDONED regelt zwar niemand, aber
    weiterzuschreiben brachte nichts ausser Lograuschen -- der Kanal hat gerade
    acht Fehlschlaege in Folge geliefert.
    """
    return ownership in (FanOwnership.RELEASED, FanOwnership.ABANDONED)


class ReleaseReason(str, Enum):
    """Warum ein Kanal abgegeben wurde. Fuer den Nutzer der Unterschied
    zwischen "reparier die Rechte" und "reparier den Sensor"."""

    NOT_CONTROLLABLE = "not_controllable"
    """BaluHost konnte den Kanal wiederholt nicht schreiben (#534 Punkt 1)."""

    NO_TARGET = "no_target"
    """BaluHost konnte ueber laengere Zeit keinen Zielwert bilden, weil die
    Temperaturquelle nichts liefert (#534 Punkt 2). Der Kanal WAERE
    schreibbar."""


# Kurventypen, die ohne Temperatur keinen Zielwert bilden koennen.
# `flat` liefert eine Konstante, `sync` kopiert einen anderen Luefter -- beide
# rechnen ohne Temperatur (fan_curve_eval.py:33-54). Sie bei fehlendem
# Messwert abzugeben, waere eine Freigabe ohne Ausfall.
TEMPERATURGEFUEHRTE_KURVEN = frozenset({"graph", "target", "mix"})

# Wie lange ohne Zielwert, bevor abgegeben wird. Gegen die Wanduhr, nicht
# gegen Zyklen: fan_sample_interval_seconds ist in Produktion 5 s, im
# Dev-Modus 15 s und per Env konfigurierbar -- "12 Zyklen" waeren je nach
# Umgebung eine Minute oder drei (#534).
#
# Fuenf Minuten ist lang genug, dass ein Sensor-Aussetzer oder ein Neustart
# des Monitoring-Workers keine Abgabe ausloest, und kurz genug, dass ein
# dauerhaft verschwundener Sensor nicht stundenlang unbemerkt bleibt.
KEIN_ZIELWERT_SEKUNDEN = 300.0


def braucht_temperatur(curve_type: str) -> bool:
    """Ob dieser Kurventyp ohne Temperatur keinen Zielwert bilden kann."""
    return curve_type in TEMPERATURGEFUEHRTE_KURVEN


def should_release_for_missing_target(
    *,
    mode_value: str,
    curve_type: str,
    has_sensor_configured: bool,
    missing_seconds: float,
    ownership: FanOwnership,
    has_observed_restore_value: bool,
    is_firmware_managed: bool,
    is_active: bool,
    threshold_seconds: float = KEIN_ZIELWERT_SEKUNDEN,
) -> bool:
    """Ob dieser Kanal abgegeben werden soll, weil kein Zielwert zustande kommt.

    Die Bedingung ist eng gefasst, und jede Einschraenkung hat einen Grund
    (#534, Befunde des ersten Anlaufs):

    - **Nur AUTO und SCHEDULED.** In MANUAL laeuft der Kurvenzweig gar nicht;
      der Nutzer verloere seine Handeinstellung, ohne dass etwas ausgefallen
      waere.
    - **Nur temperaturgefuehrte Kurven.** `flat` und `sync` rechnen ohne
      Temperatur -- bei ihnen ist ein fehlender Messwert folgenlos.
    - **Nur mit konfiguriertem Sensor.** `temperature is None` gilt auch, wenn
      GAR KEIN Sensor eingestellt ist. Das ist eine Konfiguration, kein
      Ausfall, und darf keine Abgabe ausloesen.
    - **Gegen die Wanduhr**, nicht gegen Zyklen.

    Die uebrigen Wachen sind dieselben wie bei Punkt 1 -- insbesondere die
    geerbte Randbedingung, dass ohne beobachteten pwm_enable-Wert nichts
    zurueckgegeben wird.
    """
    if mode_value not in ("auto", "scheduled"):
        return False
    if not braucht_temperatur(curve_type):
        return False
    if not has_sensor_configured:
        return False
    if missing_seconds < threshold_seconds:
        return False
    return _abgabe_moeglich(
        ownership=ownership,
        has_observed_restore_value=has_observed_restore_value,
        is_firmware_managed=is_firmware_managed,
        is_active=is_active,
    )
