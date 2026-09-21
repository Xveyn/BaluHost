"""Was der Installer sagt, wenn er den Autostart *nicht* einrichten konnte.

Der else-Zweig greift, sobald der Zielbenutzer beim Installieren keine
Sitzung hat — `/run/user/$uid` fehlt oder `daemon-reload` scheitert. Das ist
bei einer Erstinstallation per SSH als root der **Normalfall**, nicht die
Ausnahme: dann laeuft `systemctl --user enable` nie, es gibt keinen Symlink
in `graphical-session.target.wants/`, und `WantedBy=` bleibt wirkungslos.

Geprueft wird deshalb genau dieser Zweig: eine Erfolgsmeldung an dieser
Stelle ist schlimmer als gar keine, weil sie den Menschen davon abhaelt,
nachzusehen.
"""

from pathlib import Path

import pytest

MODULE = (
    Path(__file__).resolve().parents[3]
    / "deploy" / "install" / "modules" / "10-systemd-services.sh"
)

ENABLE_COMMAND = "systemctl --user enable baluhost-tray.service"


def _fallback_block(text: str) -> list[str]:
    """Die Zeilen des else-Zweigs von `if [ -d "$runtime" ]`.

    Bewusst ueber die Zeilenstruktur und nicht ueber eine Suche im ganzen
    Dateitext: eine Zeichenkette, die irgendwo in der Datei vorkommt, sagt
    nichts darueber, ob sie in *diesem* Zweig steht. Die `|| { ... }`-Bloecke
    dazwischen klammern mit `{`/`}`, nicht mit `else`/`fi`, also ist das
    erste `fi` nach dem `else` das zugehoerige.
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().startswith('if [ -d "$runtime" ]')]
    assert len(starts) == 1, f"erwartet genau eine Runtime-Pruefung, gefunden: {len(starts)}"

    rest = lines[starts[0]:]
    else_at = next(i for i, line in enumerate(rest) if line.strip() == "else")
    fi_at = next(i for i, line in enumerate(rest) if i > else_at and line.strip() == "fi")
    return rest[else_at + 1:fi_at]


@pytest.fixture
def fallback() -> list[str]:
    return _fallback_block(MODULE.read_text())


def test_the_module_exists():
    assert MODULE.exists()


def test_the_fallback_does_not_report_success(fallback: list[str]):
    """`log_info` liest sich wie erledigt — hier ist nichts erledigt."""
    infos = [line.strip() for line in fallback if line.strip().startswith("log_info")]
    assert infos == [], (
        "der Zweig ohne Sitzung darf keinen Erfolg melden: " + "; ".join(infos)
    )


def test_the_fallback_warns(fallback: list[str]):
    assert any(line.strip().startswith("log_warn") for line in fallback), fallback


def test_the_fallback_names_the_command_to_catch_up(fallback: list[str]):
    """Ohne den Befehl bleibt dem Leser nur die Erkenntnis, dass etwas fehlt."""
    assert ENABLE_COMMAND in "\n".join(fallback), fallback
