"""The unit template must stay a user unit and stay unprivileged.

Geprueft werden **geparste Direktiven**, keine Teilzeichenketten. Der
Unterschied ist nicht akademisch: die Vorgaengerfassung suchte im ganzen
Dateitext, und ein *Kommentar*, der eine Direktive buchstabiert, reichte ihr
als Beweis. `Restart=always` blieb so unentdeckt, weil ein Kommentar die
Zeichenkette `Restart=on-failure` weitertrug; ein geloeschter
`[Install]`-Abschnitt blieb unentdeckt, weil `After=graphical-session.target`
dieselbe Zeichenkette enthaelt. Was systemd liest, ist die Direktive — also
pruefen wir die.
"""

from configparser import ConfigParser
from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "deploy" / "install" / "templates" / "baluhost-tray.service"
)

# Was process_template ersetzt. Beides muss vorkommen und nach dem Rendern
# verschwunden sein.
PLACEHOLDER_VALUES = {
    "@@VENV_BIN@@": "/opt/baluhost/backend/.venv/bin",
    "@@WEB_URL@@": "https://baluhost.local",
}

# Diese drei Direktiven wuerden die Exit-Code-Teilung aushebeln, auf der die
# Unit aufbaut: 0 heisst dauerhaft erledigt (kein Neustart), 3 heisst
# moeglicherweise voruebergehend (Neustart). Wer Exit 3 zum Erfolg erklaert
# oder vom Neustart ausnimmt, dreht genau das um.
EXIT_CODE_OVERRIDES = (
    "SuccessExitStatus",
    "RestartPreventExitStatus",
    "RestartForceExitStatus",
)


def _parse(text: str) -> ConfigParser:
    """systemd-Unit als INI lesen.

    `interpolation=None`, weil `%h` in `ConditionPathExists` eine
    systemd-Spezifikation ist und configparser sie sonst als eigene
    Interpolation missversteht. `optionxform = str` haelt die
    Gross-/Kleinschreibung fest — systemd-Schluessel sind case sensitive,
    configparser kleinschreibt per Vorgabe. `strict=True` (Vorgabe) faellt
    ausserdem ueber doppelte Schluessel.
    """
    parser = ConfigParser(
        allow_no_value=True,
        comment_prefixes=("#",),
        interpolation=None,
    )
    parser.optionxform = str  # type: ignore[method-assign]
    parser.read_string(text)
    return parser


def _seconds(value: str) -> int:
    """`10s` → 10. Eine nackte Zahl ist fuer systemd ebenfalls eine Sekunde."""
    stripped = value.strip()
    if stripped.endswith("s"):
        stripped = stripped[:-1]
    return int(stripped)


@pytest.fixture
def text() -> str:
    return TEMPLATE.read_text()


@pytest.fixture
def unit(text: str) -> ConfigParser:
    return _parse(text)


def test_template_exists():
    assert TEMPLATE.exists()


def test_has_the_three_sections_systemd_needs(unit: ConfigParser):
    assert set(unit.sections()) == {"Unit", "Service", "Install"}


def test_is_bound_to_the_graphical_session(unit: ConfigParser):
    assert unit["Unit"]["After"] == "graphical-session.target"
    assert unit["Unit"]["PartOf"] == "graphical-session.target"


def test_autostart_is_wired_up(unit: ConfigParser):
    """Ohne [Install] gibt es kein `systemctl --user enable` und keinen Autostart."""
    assert unit.has_section("Install")
    assert unit["Install"]["WantedBy"] == "graphical-session.target"


def test_restarts_on_failure_only(unit: ConfigParser):
    """`always` wuerde auch Exit 0 neu starten — den dauerhaft erledigten Fall."""
    assert unit["Service"]["Restart"] == "on-failure"


def test_exit_code_split_is_not_overridden(unit: ConfigParser):
    for key in EXIT_CODE_OVERRIDES:
        assert key not in unit["Service"], (
            f"{key} in [Service] wuerde die Bedeutung von Exit 3 umdrehen"
        )
        assert key not in unit["Unit"]


def test_the_start_limit_is_actually_reachable(unit: ConfigParser):
    """Sonst laeuft ein dauerhafter Exit 3 endlos im Zehnsekundentakt.

    systemd-Vorgabe auf Debian 13 ist `DefaultStartLimitIntervalUSec=10s` bei
    `DefaultStartLimitBurst=5`. Mit `RestartSec=10s` faellt hoechstens ein
    Start in jedes Fenster, die fuenf werden nie erreicht, und das Limit
    greift nie. Deshalb setzt die Unit das Fenster selbst — und zwar weit
    genug, dass `burst` Versuche hineinpassen.
    """
    restart_sec = _seconds(unit["Service"]["RestartSec"])
    interval = _seconds(unit["Unit"]["StartLimitIntervalSec"])
    burst = int(unit["Unit"]["StartLimitBurst"])

    assert restart_sec == 10
    assert interval == 300
    assert burst == 5
    assert burst * restart_sec <= interval, (
        f"{burst} Versuche im Abstand von {restart_sec}s brauchen mehr als "
        f"{interval}s — das Startlimit waere unerreichbar"
    )


def test_does_not_start_before_there_is_a_pairing(unit: ConfigParser):
    """Der genaue Pfad zaehlt: ein falscher liesse die Unit nie starten."""
    assert unit["Unit"]["ConditionPathExists"] == "%h/.baluhost/tray-tokens.json"


def test_never_asks_for_root(unit: ConfigParser):
    """Ein User=root hier waere ein Bruch der Zusage aus der Spec."""
    assert "User" not in unit["Service"]
    assert unit["Service"]["NoNewPrivileges"] == "yes"
    assert "sudo" not in unit["Service"]["ExecStart"]


def test_uses_the_repo_placeholder_convention(text: str, unit: ConfigParser):
    """@@KEY@@ plus process_template, nicht rohes sed.

    `@@VENV_BIN@@` und nicht `@@INSTALL_DIR@@/backend/.venv/bin`: die anderen
    Unit-Vorlagen nutzen VENV_BIN, und Modul 10 laesst es ueberschreiben.
    """
    for placeholder in PLACEHOLDER_VALUES:
        assert placeholder in text
    assert "@@INSTALL_DIR@@" not in text
    assert unit["Service"]["ExecStart"].startswith("@@VENV_BIN@@/baluhost-tray")


def test_opens_the_web_ui_not_the_api_port(unit: ConfigParser):
    """Die Unit startet ohne Argumente sonst immer mit dem Default."""
    assert "--web-url @@WEB_URL@@" in unit["Service"]["ExecStart"]


def test_rendering_leaves_no_placeholder_behind(text: str):
    """Ein uebersehener Platzhalter landete sonst woertlich in der Unit."""
    rendered = text
    for placeholder, value in PLACEHOLDER_VALUES.items():
        rendered = rendered.replace(placeholder, value)
    assert "@@" not in rendered

    unit = _parse(rendered)
    assert unit["Service"]["ExecStart"] == (
        "/opt/baluhost/backend/.venv/bin/baluhost-tray "
        "--web-url https://baluhost.local"
    )
