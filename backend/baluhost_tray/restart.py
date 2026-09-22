"""The tray's outgoing path: restarting the BaluHost services.

Everything decidable lives here so it can be tested without Qt, without
systemd and without a running backend. tray.py only shows dialogs.

Two routes, deliberately: while the API answers, the backend restarts its own
units after a BaluHost step-up. When it does not answer, nobody can verify a
BaluHost password any more — then systemd does the work and polkit asks the
question that still has an honest answer.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import httpx

HEALTH_PATH = "/api/health"
ME_PATH = "/api/auth/me"
TOTP_STATUS_PATH = "/api/auth/2fa/status"
RESTART_ALL_PATH = "/api/system/restart-all"

# Long enough that a busy backend still counts as alive, short enough that the
# dialog does not feel stuck in the case this feature exists for.
PROBE_TIMEOUT = 2.0
# The API path restarts four units synchronously (20 s each in the worst case)
# before it answers. Below that, a slow restart would look like a dead backend.
API_TIMEOUT = 120.0
LOCAL_TIMEOUT = 120.0

UNITS: tuple[str, ...] = (
    "baluhost-scheduler",
    "baluhost-monitoring",
    "baluhost-webdav",
    "baluhost-backend-local",
    "baluhost-backend",
)


@dataclass(frozen=True)
class RestartOutcome:
    """What happened, and what the dialog should do next."""

    ok: bool
    message: str
    retry_secret: bool = False   # wrong password/code — ask again
    offer_local: bool = False    # API died mid-flight — offer the fallback
    totp_required: bool = False  # the route wants a code, not a password


@dataclass(frozen=True)
class AccountFacts:
    """``is_admin is None`` means "could not ask", not "not an admin"."""

    is_admin: bool | None
    totp_enabled: bool


_UNKNOWN = AccountFacts(is_admin=None, totp_enabled=False)


def probe_api(client) -> bool:
    """Does the API answer right now?

    Deliberately not derived from the icon colour: that one tracks the
    websocket, and a stale ws-token paints the icon grey while /api/health is
    perfectly fine.
    """
    try:
        # < 500, nicht == 200: /api/health teilt sich sein IP-Rate-Limit mit
        # allem anderen auf localhost. Ein ausgeschöpftes Limit (429) heisst
        # "Backend lebt, gerade gedrosselt" — nicht "Backend tot". Mit == 200
        # würde ein 429 den Notweg auslösen: kein BaluHost-Step-up, kein
        # App-Audit, obwohl die API antwortet.
        return client.get(HEALTH_PATH, timeout=PROBE_TIMEOUT).status_code < 500
    except httpx.HTTPError:
        return False


def fetch_account_facts(
    client,
    on_auth_expired: Callable[[], None] | None = None,
) -> AccountFacts:
    """Role and 2FA state of the paired account. Never raises.

    Refreshes once on a 401: an expired access token is the normal state at
    tray start (#692), and without the retry a 2FA account would be asked three
    times for a password the route does not accept.
    """
    refreshed = False
    while True:
        try:
            response = client.get(ME_PATH, timeout=PROBE_TIMEOUT)
        except httpx.HTTPError:
            return _UNKNOWN

        if response.status_code == 401 and on_auth_expired is not None and not refreshed:
            try:
                on_auth_expired()
            except Exception:       # noqa: BLE001 — PairingLost, TemporaryFailure, network, anything
                return _UNKNOWN
            refreshed = True
            continue

        if response.status_code != 200:
            return _UNKNOWN

        try:
            is_admin = response.json().get("role") == "admin"
        except (ValueError, AttributeError):
            return _UNKNOWN
        break

    totp_enabled = False
    try:
        status_response = client.get(TOTP_STATUS_PATH, timeout=PROBE_TIMEOUT)
        if status_response.status_code == 200:
            totp_enabled = bool(status_response.json().get("enabled"))
    except (httpx.HTTPError, ValueError, AttributeError):
        # A missing 2FA state only mislabels the dialog, and the route's 401
        # carries `totp_required` anyway.
        pass

    return AccountFacts(is_admin=is_admin, totp_enabled=totp_enabled)


def menu_visible(is_admin: bool | None, api_reachable: bool) -> bool:
    """Show the entry for admins — and for anyone when we could not ask.

    The middle case is the point: without it the button would be missing in
    exactly the situation it exists for, where the backend has been dead since
    login and the role was never learned. It weakens nothing, because on that
    route polkit decides, not the visibility of a menu entry.
    """
    if is_admin:
        return True
    if is_admin is None:
        return True
    return not api_reachable


def _unit_states(
    runner: Callable[..., Any], units: Sequence[str], timeout: float
) -> dict[str, str]:
    """`systemctl is-active` für alle Units. Lesend — kein polkit, kein Dialog.

    Returns an empty mapping when the query itself fails; the caller must not
    turn a successful restart into a failure just because the follow-up look
    did not work.
    """
    try:
        completed = runner(
            ["systemctl", "is-active", *units],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    lines = (completed.stdout or "").splitlines()
    return {unit: (lines[i].strip() if i < len(lines) else "") for i, unit in enumerate(units)}


def restart_via_systemctl(
    runner: Callable[..., Any] = subprocess.run,
    units: Sequence[str] = UNITS,
    timeout: float = LOCAL_TIMEOUT,
) -> RestartOutcome:
    """The fallback: ask systemd directly, let polkit ask the user.

    No sudo. systemd checks the caller against
    ``org.freedesktop.systemd1.manage-units`` (auth_admin_keep), so KDE's own
    agent prompts.

    **One call for all units, on purpose.** polkit binds the temporary
    authorisation to the requesting *process* — five separate systemctl calls
    would be five processes and five password prompts. One call is one process
    making five D-Bus requests, so the agent asks once.

    **And it stays a short-lived subprocess.** Calling
    org.freedesktop.systemd1.Manager.RestartUnit over D-Bus from this
    long-lived tray process would keep that authorisation alive for five
    minutes — and `manage-units` also covers StartTransientUnit, i.e. running
    anything as root. The process boundary is what keeps the radius small.
    """
    try:
        completed = runner(
            ["systemctl", "restart", *units],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RestartOutcome(
            False,
            "Zeitüberschreitung beim Neustart. Die Dienste können trotzdem "
            "gerade hochfahren — bitte den Zustand prüfen.",
        )
    except Exception as exc:
        return RestartOutcome(
            False, f"systemctl konnte nicht ausgeführt werden: {exc}"
        )

    if completed.returncode == 0:
        return RestartOutcome(True, f"{len(units)} Dienste neu gestartet.")

    # Erst hier abgefragt: bei Erfolg braucht niemand das Ergebnis, und ein
    # zusätzlicher `systemctl is-active`-Aufruf wäre verschwendet.
    states = _unit_states(runner, units, timeout)

    detail = (completed.stderr or completed.stdout or "").strip()
    detail = detail or f"exit {completed.returncode}"

    if not states:
        # Der is-active-Aufruf selbst ist gescheitert — der Zustand ist unbekannt
        tail = "\n\nWelche Dienste jetzt laufen, konnte nicht ermittelt werden."
    else:
        inactive = [unit for unit, state in states.items() if state != "active"]
        tail = (
            "\n\nNicht aktiv: " + ", ".join(inactive)
            if inactive
            else "\n\nAlle Dienste laufen trotzdem."
        )

    return RestartOutcome(
        False,
        f"Neustart fehlgeschlagen — abgebrochen oder keine Berechtigung.\n\n"
        f"{detail}{tail}",
    )


def _detail(response) -> Any:
    try:
        return response.json().get("detail")
    except (ValueError, AttributeError):
        return None


def restart_via_api(
    client,
    secret: str,
    totp: bool,
    on_auth_expired: Callable[[], None] | None = None,
) -> RestartOutcome:
    """The normal route: the backend restarts its own units after the step-up.

    ``secret`` is a password or a TOTP code; ``totp`` decides which field it
    goes into. ``on_auth_expired`` is called at most once, for a plain 401.
    """
    body = {"code": secret} if totp else {"current_password": secret}
    refreshed = False

    while True:
        try:
            response = client.post(RESTART_ALL_PATH, json=body, timeout=API_TIMEOUT)
        except httpx.TimeoutException:
            # Nicht als "Backend tot" behandeln: die Route startet vier Units
            # synchron. Wer hier den Notweg anböte, liesse den Nutzer alles ein
            # zweites Mal starten, waehrend es gerade ordentlich laeuft.
            return RestartOutcome(
                False,
                "Der Neustart dauert länger als erwartet. Er läuft "
                "wahrscheinlich noch — bitte den Zustand prüfen, bevor du es "
                "erneut versuchst.",
            )
        except httpx.HTTPError as exc:
            return RestartOutcome(
                False,
                f"Das Backend hat die Verbindung abgebrochen ({exc}).",
                offer_local=True,
            )

        code = response.status_code
        detail = _detail(response)

        if code == 401:
            if isinstance(detail, dict) and detail.get("error") == "step_up_failed":
                return RestartOutcome(
                    False,
                    "Passwort bzw. 2FA-Code stimmt nicht.",
                    retry_secret=True,
                    totp_required=bool(detail.get("totp_required")),
                )
            if on_auth_expired is not None and not refreshed:
                try:
                    on_auth_expired()
                except Exception as exc:        # noqa: BLE001 — PairingLost u.a.
                    return RestartOutcome(
                        False, f"Anmeldung konnte nicht erneuert werden: {exc}"
                    )
                refreshed = True
                continue
            return RestartOutcome(
                False,
                "Die Kopplung ist abgelaufen. Einmalig ausführen: "
                "baluhost-tray --pair",
            )

        if code == 403:
            if isinstance(detail, dict) and detail.get("error") == "local_network_required":
                return RestartOutcome(
                    False, "Der Neustart ist nur aus dem lokalen Netz möglich."
                )
            if isinstance(detail, dict) and detail.get("error") == "api_key_not_allowed":
                # Heute unerreichbar — das Tray spricht mit einem JWT, nie mit
                # einem API-Key —, aber der 403-Vertrag hat drei Formen auf der
                # Route, also pflegen wir sie auch hier zu dritt.
                return RestartOutcome(
                    False,
                    "Dieser Vorgang verlangt eine erneute Anmeldung und ist "
                    "mit einem API-Schlüssel nicht möglich.",
                )
            return RestartOutcome(False, "Dieses Konto ist kein BaluHost-Admin.")
        if code == 429:
            return RestartOutcome(
                False, "Zu viele Versuche. In einer Minute erneut probieren."
            )
        if code != 200:
            return RestartOutcome(
                False, f"Das Backend hat den Neustart abgelehnt ({code})."
            )

        try:
            units = response.json()["units"]
            failed = [u["name"] for u in units if not u.get("success")]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return RestartOutcome(
                False, f"Unerwartete Antwort des Backends ({exc})."
            )

        if failed:
            return RestartOutcome(False, "Nicht neu gestartet: " + ", ".join(failed))
        return RestartOutcome(
            True,
            "Dienste neu gestartet. Das Backend startet gleich ebenfalls neu — "
            "das Symbol wird kurz grau.",
        )


MAX_SECRET_ATTEMPTS = 3


def restart_flow(
    client,
    prompt: Callable[[str], str | None],
    probe: Callable[..., bool] = probe_api,
    facts: Callable[..., AccountFacts] = fetch_account_facts,
    api: Callable[..., RestartOutcome] = restart_via_api,
    local: Callable[..., RestartOutcome] = restart_via_systemctl,
    on_auth_expired: Callable[[], None] | None = None,
) -> RestartOutcome:
    """One click, start to finish. No Qt in here.

    ``prompt(mode)`` returns what the user typed, or None if they cancelled.
    Every collaborator is injected so the whole sequence is testable without a
    backend, without systemd and without a display.
    """
    if not probe(client):
        return _local_flow(prompt, local)

    account = facts(client, on_auth_expired=on_auth_expired)
    if account.is_admin is False:
        return RestartOutcome(
            False,
            "Dieses Konto ist kein BaluHost-Admin. Neustart nicht möglich.",
        )

    totp = account.totp_enabled
    for attempt in range(MAX_SECRET_ATTEMPTS):
        mode = "totp" if totp else "password"
        secret = prompt(mode if attempt == 0 else f"{mode}_retry")
        if secret is None:
            return RestartOutcome(False, "Abgebrochen.")

        outcome = api(client, secret, totp, on_auth_expired=on_auth_expired)
        if outcome.offer_local:
            return _local_flow(prompt, local)
        if not outcome.retry_secret:
            return outcome
        # Die Route weiss besser als der vorher geholte 2FA-Status, was sie
        # erwartet — beim naechsten Versuch danach fragen.
        totp = outcome.totp_required or totp

    return RestartOutcome(False, "Passwort bzw. 2FA-Code dreimal falsch.")


def _local_flow(
    prompt: Callable[[str], str | None],
    local: Callable[..., RestartOutcome],
) -> RestartOutcome:
    """Confirm, then hand over to systemd — polkit does the asking."""
    if prompt("local") is None:
        return RestartOutcome(False, "Abgebrochen.")
    return local()
