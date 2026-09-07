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
    if not is_active:
        return False
    if is_firmware_managed:
        return False
    if ownership is not FanOwnership.OWNED:
        return False
    if not has_observed_restore_value:
        return False
    return at_write_cap


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
