"""org.bluez.Agent1 — beantwortet Rueckfragen von BlueZ waehrend EINER Kopplung.

Der Agent wird pro Kopplung angemeldet (``RegisterAgent`` mit
``KeyboardDisplay``, NIE ``RequestDefaultAgent``) und danach wieder
abgemeldet. BlueZ fragt einen solchen Agenten nur zu Kopplungen, die dieselbe
Bus-Verbindung per ``Pair()`` angestossen hat; eingehende Anfragen bleiben
bei KDE (BlueDevil).

NB 1: kein ``from __future__ import annotations``. dbus-next liest die
D-Bus-Signaturen aus den Annotationen; PEP 563 machte aus ``'o'`` die
Zeichenkette ``"'o'"``. Die Typen stehen als Konstanten da, weil pyflakes ein
String-Literal wie ``'o'`` als undefinierten Namen meldet.

NB 2: dbus-nexts ``@method()`` verwirft den Rueckgabewert, wenn man die
dekorierte Methode direkt aufruft. Die Logik steckt in ``handle_*``; die
dekorierten Methoden sind nur Huellen.
"""
import logging
import secrets

from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, method

from app.plugins.installed.bluetooth.pairing import PairingPrompter

logger = logging.getLogger(__name__)

AGENT_PATH = "/org/baluhost/bluetooth/agent"
AGENT_CAPABILITY = "KeyboardDisplay"
REJECTED = "org.bluez.Error.Rejected"

OBJ = "o"
STR = "s"
U32 = "u"
U16 = "q"


class BluezAgent(ServiceInterface):
    """Antwortet ausschliesslich zum Geraet der laufenden Sitzung."""

    def __init__(self, prompter: PairingPrompter) -> None:
        super().__init__("org.bluez.Agent1")
        self._prompter = prompter

    def _require_session_device(self, device: str) -> None:
        if device != self._prompter.device_path:
            logger.warning("Bluetooth-Agent: Anfrage fuer fremdes Geraet abgelehnt")
            raise DBusError(REJECTED, "Nicht Teil dieser Kopplung")

    # --- Logik -----------------------------------------------------------

    def handle_display_passkey(self, device: str, passkey: int, entered: int) -> None:
        self._require_session_device(device)
        self._prompter.show_passkey(int(passkey), int(entered))

    def handle_display_pin_code(self, device: str, pincode: str) -> None:
        self._require_session_device(device)
        self._prompter.show_pin(str(pincode))

    def handle_request_pin_code(self, device: str) -> str:
        self._require_session_device(device)
        if self._prompter.device_icon != "input-keyboard":
            # Legacy-Geraete mit fester PIN ("0000") gehoeren nicht zu v1.
            raise DBusError(REJECTED, "Legacy-Geraet mit fester PIN nicht unterstuetzt")
        pin = f"{secrets.randbelow(10**6):06d}"
        self._prompter.show_pin(pin)
        return pin

    async def handle_request_confirmation(self, device: str, passkey: int) -> None:
        self._require_session_device(device)
        if not await self._prompter.ask_confirmation(int(passkey)):
            raise DBusError(REJECTED, "Abgelehnt")

    def handle_request_authorization(self, device: str) -> None:
        # Der Klick auf genau dieses Geraet ist die Zustimmung.
        self._require_session_device(device)

    def handle_request_passkey(self, device: str) -> int:
        self._require_session_device(device)
        raise DBusError(REJECTED, "Passkey-Eingabe am Rechner nicht unterstuetzt")

    def handle_authorize_service(self, device: str, uuid: str) -> None:
        self._require_session_device(device)
        raise DBusError(REJECTED, "Dienstfreigaben entscheidet dieser Agent nicht")

    def handle_cancel(self) -> None:
        self._prompter.cancelled()

    # --- D-Bus-Huellen ---------------------------------------------------

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: OBJ) -> STR:
        return self.handle_request_pin_code(device)

    @method()
    def DisplayPinCode(self, device: OBJ, pincode: STR):
        self.handle_display_pin_code(device, pincode)

    @method()
    def RequestPasskey(self, device: OBJ) -> U32:
        return self.handle_request_passkey(device)

    @method()
    def DisplayPasskey(self, device: OBJ, passkey: U32, entered: U16):
        self.handle_display_passkey(device, passkey, entered)

    @method()
    async def RequestConfirmation(self, device: OBJ, passkey: U32):
        await self.handle_request_confirmation(device, passkey)

    @method()
    def RequestAuthorization(self, device: OBJ):
        self.handle_request_authorization(device)

    @method()
    def AuthorizeService(self, device: OBJ, uuid: STR):
        self.handle_authorize_service(device, uuid)

    @method()
    def Cancel(self):
        self.handle_cancel()
