"""BlueZClient gegen einen Fake-Bus: Nachrichtenform, Fehler, Timeout, Neuaufbau."""
import asyncio

import pytest
from dbus_next import MessageType, Variant

from app.plugins.installed.bluetooth.bluez import (
    ADAPTER_IFACE,
    DEVICE_IFACE,
    TIMEOUT_ERROR,
    BlueZClient,
    BlueZError,
)


class _Reply:
    def __init__(self, message_type, body=(), error_name=None):
        self.message_type = message_type
        self.body = list(body)
        self.error_name = error_name


def _ok(*body):
    return _Reply(MessageType.METHOD_RETURN, body)


class _FakeBus:
    connected = True

    def __init__(self, replies):
        self.sent = []
        self.exported = {}
        self._replies = list(replies)

    async def call(self, msg):
        self.sent.append(msg)
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if reply == "hang":
            await asyncio.sleep(10)
        return reply

    def export(self, path, interface):
        self.exported[path] = interface

    def unexport(self, path, interface=None):
        self.exported.pop(path, None)


def _client(bus):
    async def factory():
        return bus
    return BlueZClient(bus_factory=factory)


async def test_managed_objects_are_unwrapped():
    bus = _FakeBus([_ok({"/org/bluez/hci0": {ADAPTER_IFACE: {"Powered": Variant("b", True)}}})])
    objects = await _client(bus).get_managed_objects()
    assert objects["/org/bluez/hci0"][ADAPTER_IFACE]["Powered"] is True
    assert bus.sent[0].member == "GetManagedObjects"
    assert bus.sent[0].destination == "org.bluez"


async def test_an_error_reply_becomes_a_named_bluez_error():
    bus = _FakeBus([_Reply(MessageType.ERROR, ["br-connection-page-timeout"], "org.bluez.Error.Failed")])
    with pytest.raises(BlueZError) as info:
        await _client(bus).call("/org/bluez/hci0/dev_AA_AA_AA_AA_AA_02", DEVICE_IFACE, "Connect")
    assert info.value.name == "org.bluez.Error.Failed"
    assert info.value.text == "br-connection-page-timeout"


async def test_set_property_sends_a_typed_variant():
    bus = _FakeBus([_ok()])
    await _client(bus).set_property("/org/bluez/hci0", ADAPTER_IFACE, "Powered", "b", False)
    msg = bus.sent[0]
    assert (msg.interface, msg.member, msg.signature) == (
        "org.freedesktop.DBus.Properties", "Set", "ssv",
    )
    assert msg.body[0] == ADAPTER_IFACE and msg.body[1] == "Powered"
    assert msg.body[2].signature == "b" and msg.body[2].value is False


async def test_a_hanging_call_times_out_with_a_named_error():
    bus = _FakeBus(["hang"])
    with pytest.raises(BlueZError) as info:
        await _client(bus).call("/org/bluez/hci0", ADAPTER_IFACE, "StartDiscovery", timeout=0.01)
    assert info.value.name == TIMEOUT_ERROR


async def test_a_broken_bus_is_rebuilt_on_the_next_call():
    buses = [_FakeBus([EOFError()]), _FakeBus([_ok({})])]
    built = []

    async def factory():
        built.append(1)
        return buses.pop(0)

    client = BlueZClient(bus_factory=factory)
    with pytest.raises(BlueZError):
        await client.get_managed_objects()
    assert await client.get_managed_objects() == {}
    assert len(built) == 2


async def test_export_and_unexport_use_the_bus():
    bus = _FakeBus([])
    client = _client(bus)
    marker = object()
    await client.export("/org/baluhost/bluetooth/agent", marker)
    assert bus.exported["/org/baluhost/bluetooth/agent"] is marker
    client.unexport("/org/baluhost/bluetooth/agent")
    assert bus.exported == {}
