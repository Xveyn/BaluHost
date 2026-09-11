"""Agent-Logik: nur das Sitzungsgeraet, nur erlaubte Ablaeufe."""
import pytest
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface

from app.plugins.installed.bluetooth.agent import REJECTED, BluezAgent

SESSION = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_04"
FOREIGN = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_09"


class _Prompter:
    def __init__(self, icon="input-keyboard", confirm=True):
        self.device_path = SESSION
        self.device_icon = icon
        self.confirm = confirm
        self.passkeys = []
        self.pins = []
        self.cancel_count = 0

    def show_passkey(self, passkey, entered):
        self.passkeys.append((passkey, entered))

    def show_pin(self, pin):
        self.pins.append(pin)

    async def ask_confirmation(self, passkey):
        return self.confirm

    def cancelled(self):
        self.cancel_count += 1


def _rejected(call):
    with pytest.raises(DBusError) as info:
        call()
    assert info.value.type == REJECTED


class TestOnlyTheSessionDevice:
    def test_display_passkey_for_a_foreign_device_is_rejected(self):
        prompter = _Prompter()
        _rejected(lambda: BluezAgent(prompter).handle_display_passkey(FOREIGN, 1, 0))
        assert prompter.passkeys == []

    def test_authorization_for_a_foreign_device_is_rejected(self):
        _rejected(lambda: BluezAgent(_Prompter()).handle_request_authorization(FOREIGN))

    async def test_confirmation_for_a_foreign_device_is_rejected(self):
        with pytest.raises(DBusError):
            await BluezAgent(_Prompter()).handle_request_confirmation(FOREIGN, 1)


class TestFlows:
    def test_display_passkey_reaches_the_prompter(self):
        prompter = _Prompter()
        BluezAgent(prompter).handle_display_passkey(SESSION, 4821, 3)
        assert prompter.passkeys == [(4821, 3)]

    def test_request_pin_code_generates_a_six_digit_pin_for_a_keyboard(self):
        prompter = _Prompter(icon="input-keyboard")
        pin = BluezAgent(prompter).handle_request_pin_code(SESSION)
        assert len(pin) == 6 and pin.isdigit()
        assert prompter.pins == [pin]

    def test_request_pin_code_is_rejected_for_anything_but_a_keyboard(self):
        _rejected(lambda: BluezAgent(_Prompter(icon="audio-headphones")).handle_request_pin_code(SESSION))

    def test_the_pin_comes_from_secrets(self, monkeypatch):
        import app.plugins.installed.bluetooth.agent as agent_module
        monkeypatch.setattr(agent_module.secrets, "randbelow", lambda n: 42)
        assert BluezAgent(_Prompter()).handle_request_pin_code(SESSION) == "000042"

    async def test_an_accepted_confirmation_returns_normally(self):
        await BluezAgent(_Prompter(confirm=True)).handle_request_confirmation(SESSION, 123456)

    async def test_a_refused_confirmation_is_rejected(self):
        with pytest.raises(DBusError) as info:
            await BluezAgent(_Prompter(confirm=False)).handle_request_confirmation(SESSION, 123456)
        assert info.value.type == REJECTED

    def test_authorization_for_the_session_device_is_accepted(self):
        BluezAgent(_Prompter()).handle_request_authorization(SESSION)

    def test_request_passkey_is_always_rejected(self):
        _rejected(lambda: BluezAgent(_Prompter()).handle_request_passkey(SESSION))

    def test_authorize_service_is_always_rejected(self):
        _rejected(lambda: BluezAgent(_Prompter()).handle_authorize_service(SESSION, "0000110b"))

    def test_cancel_reaches_the_prompter(self):
        prompter = _Prompter()
        BluezAgent(prompter).handle_cancel()
        assert prompter.cancel_count == 1


class TestExportedSignatures:
    """Faengt den Future-Import und falsche Annotationen ab, bevor BlueZ es tut."""

    def test_the_dbus_methods_carry_the_bluez_signatures(self):
        methods = {m.name: m for m in ServiceInterface._get_methods(BluezAgent(_Prompter()))}
        assert (methods["RequestPinCode"].in_signature, methods["RequestPinCode"].out_signature) == ("o", "s")
        assert methods["DisplayPasskey"].in_signature == "ouq"
        assert (methods["RequestPasskey"].in_signature, methods["RequestPasskey"].out_signature) == ("o", "u")
        assert methods["RequestConfirmation"].in_signature == "ou"
        assert methods["AuthorizeService"].in_signature == "os"
        assert methods["DisplayPinCode"].in_signature == "os"
        assert {"Release", "Cancel", "RequestAuthorization"} <= set(methods)
