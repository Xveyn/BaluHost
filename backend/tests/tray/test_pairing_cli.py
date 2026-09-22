"""Tests fuer den Konsolen-Kopplungsablauf.

Schwerpunkt ist die Adresse, die ein Mensch abtippt. Das Backend baut sie aus
`request.base_url` — fuer eine Anfrage an den API-Port also mit `:8000` darin.
Wer dem Link folgt, landet auf der API statt auf der Seite, auf der er den Code
eingibt. Das Tray kennt die richtige Adresse ueber `--web-url` und muss sie
benutzen.
"""

from unittest.mock import MagicMock, patch

from baluhost_tray import pairing, pairing_cli


def _pending(verification_url: str) -> pairing.PendingPairing:
    return pairing.PendingPairing(
        device_code="dc",
        user_code="123456",
        verification_url=verification_url,
        expires_in=600,
        interval=5,
    )


def _run(verification_url: str, web_url: str = "https://baluhost.local") -> list[str]:
    """Kopplung einmal durchlaufen lassen, Ausgabezeilen zurueckgeben."""
    printed: list[str] = []
    with patch.object(pairing, "start_pairing", return_value=_pending(verification_url)), \
         patch.object(pairing_cli, "pairing", pairing), \
         patch.object(pairing_cli, "BackendClient", MagicMock()), \
         patch.object(pairing_cli, "save_tokens", MagicMock()), \
         patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(str(x) for x in a))), \
         patch.object(pairing, "poll_once", return_value=MagicMock()):
        pairing_cli.run_pairing_flow("http://localhost:8000", web_url)
    return printed


def _link(lines: list[str]) -> str:
    hits = [ln for ln in lines if "http" in ln and "Freigeben" in ln]
    assert hits, f"keine Freigabe-Zeile in der Ausgabe: {lines}"
    return hits[0]


def test_the_link_does_not_point_at_the_api_port():
    """Der eigentliche Fehler: der Server liefert seine eigene Adresse."""
    link = _link(_run("http://localhost:8000/devices?pair=1"))

    assert ":8000" not in link
    assert "localhost" not in link
    assert "https://baluhost.local" in link


def test_the_link_keeps_path_and_query_from_the_server():
    """Den Pfad bestimmt weiterhin der Server — nur der Ursprung wird ersetzt.

    Sonst muesste das Tray `/devices?pair=1` fest verdrahten und liefe
    stillschweigend ins Leere, sobald die Web-UI die Route umbenennt.
    """
    link = _link(_run("http://localhost:8000/geraete?pair=1&x=2"))

    assert "/geraete?pair=1&x=2" in link
    assert link.endswith("https://baluhost.local/geraete?pair=1&x=2")


def test_an_unusable_server_url_still_yields_a_reachable_link():
    """Lieber ein Link auf die bekannte Standardseite als gar keiner."""
    link = _link(_run(""))

    assert "https://baluhost.local/devices?pair=1" in link


def test_a_custom_web_url_is_honoured():
    link = _link(_run("http://localhost:8000/devices?pair=1",
                      web_url="https://nas.example.net"))

    assert "https://nas.example.net/devices?pair=1" in link


def test_no_apology_about_the_wrong_port_is_printed():
    """Der Hinweis 'zeigt der Link auf den Backend-Port' war die Umgehung des
    Fehlers statt seiner Behebung. Mit der richtigen Adresse ist er falsch."""
    lines = _run("http://localhost:8000/devices?pair=1")

    assert not any("Backend-Port" in ln for ln in lines), lines


def test_main_passes_the_web_url_into_the_pairing_flow():
    """Der Waechter fuer die eigentliche Ursache.

    `main.run_pairing()` bekam nur `base_url`; die Kopplung *konnte* die
    richtige Adresse gar nicht kennen. Ein Test, der nur pairing_cli prueft,
    haette den Fehler nie gesehen.
    """
    from baluhost_tray import main

    with patch("baluhost_tray.pairing_cli.run_pairing_flow", return_value=0) as flow:
        main.run_pairing("http://localhost:8000", "https://baluhost.local")

    args = flow.call_args[0]
    assert args[0] == "http://localhost:8000", "Die API-Adresse gehoert an den Client"
    assert args[1] == "https://baluhost.local", "Die Web-Adresse gehoert an den Link"


def test_the_cli_entry_point_reaches_the_pairing_flow_with_both_urls():
    """Deckt die Aufrufstelle in run(), nicht nur run_pairing() selbst.

    Beim Fix dieses Fehlers blieb `run_pairing(args.base_url)` einen Moment
    lang einargumentig stehen — jeder `--pair`-Aufruf waere mit einem
    TypeError gestorben, und die Tests blieben gruen, weil sie run_pairing
    direkt aufriefen statt ueber run(). Ein Waechter fuer die Verdrahtung
    gehoert an die Verdrahtung.
    """
    from baluhost_tray import main

    with patch("baluhost_tray.pairing_cli.run_pairing_flow", return_value=0) as flow, \
         patch.object(main.single_instance, "acquire", MagicMock()):
        code = main.run(["--pair", "--base-url", "http://api.test:8000",
                         "--web-url", "https://web.test"])

    assert code == 0
    assert flow.call_args[0] == ("http://api.test:8000", "https://web.test")
