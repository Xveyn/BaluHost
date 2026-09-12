"""Mess-Skript fuer BlueZ auf BaluNode — KEIN Produktionscode.

Befehle:

  dump [--anonymize]
      GetManagedObjects als JSON auf stdout: Adapter plus GEKOPPELTE Geraete
      (fremde Geraete in Funkreichweite bleiben draussen). Mit --anonymize
      werden MAC-Adressen konsistent ersetzt; genau diese Ausgabe ist
      backend/tests/plugins/fixtures/bluez_balunode.json. Neu messen statt
      von Hand editieren.

  probe-pair MAC
      Sucht das Geraet (bis 30 s Discovery), meldet einen Agenten mit
      KeyboardDisplay an (NICHT als Standard-Agent), ruft Device1.Pair() und
      protokolliert JEDEN Agent-Aufruf. Rueckfragen werden im Terminal
      beantwortet. Nach Erfolg: Trusted=true und Connect().

Aufruf auf BaluNode mit dem venv des Backends, z. B.:
  /opt/baluhost/backend/.venv/bin/python ~/bluez_probe.py dump --anonymize
"""
import argparse
import asyncio
import json
import re
import sys
import time

from dbus_next import BusType, Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, method

BLUEZ = "org.bluez"
ADAPTER_PATH = "/org/bluez/hci0"
AGENT_PATH = "/org/baluhost/bluetooth/probe_agent"
MAC_RE = re.compile(r"(?:[0-9A-F]{2}([:_])){5}[0-9A-F]{2}")

# D-Bus-Typen als Konstanten: als String-Literal in der Annotation meldet
# pyflakes sie als undefinierte Namen (F821).
OBJ = "o"
STR = "s"
U32 = "u"
U16 = "q"


def log(text: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def unwrap(value):
    """Loest Variants rekursiv auf; ay wird zu Hex, Dict-Schluessel zu str."""
    if isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {str(k): unwrap(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [unwrap(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


async def call(bus, path, interface, member, signature="", body=None):
    reply = await bus.call(Message(
        destination=BLUEZ, path=path, interface=interface, member=member,
        signature=signature, body=list(body or []),
    ))
    if reply.message_type == MessageType.ERROR:
        raise DBusError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def managed_objects(bus) -> dict:
    body = await call(bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    return unwrap(body[0])


def only_adapter_and_paired(objects: dict) -> dict:
    """Filter to Adapter1 and paired Device1 only; drop child objects of unpaired devices."""
    excluded_device_paths = set()
    for path, ifaces in objects.items():
        device = ifaces.get("org.bluez.Device1")
        if device is not None and not device.get("Paired"):
            excluded_device_paths.add(path)

    kept = {}
    for path, ifaces in objects.items():
        if path in excluded_device_paths:
            continue
        if any(path.startswith(excluded + "/") for excluded in excluded_device_paths):
            continue
        kept[path] = ifaces
    return kept


def anonymize(objects: dict) -> dict:
    mapping: dict[str, str] = {}

    def assign(address: str) -> None:
        if address not in mapping:
            mapping[address] = f"AA:AA:AA:AA:AA:{len(mapping) + 1:02d}"

    for path in sorted(objects):
        adapter = objects[path].get("org.bluez.Adapter1")
        if adapter:
            assign(str(adapter["Address"]).upper())
    for path in sorted(objects):
        device = objects[path].get("org.bluez.Device1")
        if device:
            assign(str(device["Address"]).upper())

    text = json.dumps(objects, sort_keys=True)

    def replace(match: re.Match) -> str:
        sep = match.group(1)
        normalized = match.group(0).replace("_", ":")
        fake = mapping.get(normalized)
        if fake is None:
            return match.group(0)
        return fake.replace(":", sep)

    text = MAC_RE.sub(replace, text)

    def has_unanonymized_mac(s: str) -> bool:
        for match in MAC_RE.finditer(s):
            mac = match.group(0)
            if not mac.replace("_", ":").upper().startswith("AA:AA:AA:AA:AA:"):
                return True
        return False

    if has_unanonymized_mac(text):
        raise SystemExit("Unanonymisierte MAC im Mitschnitt — abgebrochen")

    return json.loads(text)


class ProbeAgent(ServiceInterface):
    def __init__(self) -> None:
        super().__init__("org.bluez.Agent1")

    @method()
    def Release(self):
        log("Agent: Release()")

    @method()
    async def RequestPinCode(self, device: OBJ) -> STR:
        log(f"Agent: RequestPinCode({device})")
        return (await asyncio.to_thread(input, "PIN fuer das Geraet: ")).strip()

    @method()
    def DisplayPinCode(self, device: OBJ, pincode: STR):
        log(f"Agent: DisplayPinCode({device}, {pincode})")

    @method()
    async def RequestPasskey(self, device: OBJ) -> U32:
        log(f"Agent: RequestPasskey({device})")
        return int(await asyncio.to_thread(input, "Passkey: "))

    @method()
    def DisplayPasskey(self, device: OBJ, passkey: U32, entered: U16):
        log(f"Agent: DisplayPasskey({device}, {passkey:06d}, entered={entered})")

    @method()
    async def RequestConfirmation(self, device: OBJ, passkey: U32):
        log(f"Agent: RequestConfirmation({device}, {passkey:06d})")
        answer = await asyncio.to_thread(input, "Stimmt der Code? [j/n] ")
        if answer.strip().lower() != "j":
            raise DBusError("org.bluez.Error.Rejected", "abgelehnt")

    @method()
    async def RequestAuthorization(self, device: OBJ):
        log(f"Agent: RequestAuthorization({device})")
        answer = await asyncio.to_thread(input, "Kopplung erlauben? [j/n] ")
        if answer.strip().lower() != "j":
            raise DBusError("org.bluez.Error.Rejected", "abgelehnt")

    @method()
    def AuthorizeService(self, device: OBJ, uuid: STR):
        log(f"Agent: AuthorizeService({device}, {uuid}) -> Rejected")
        raise DBusError("org.bluez.Error.Rejected", "Probe lehnt Dienste ab")

    @method()
    def Cancel(self):
        log("Agent: Cancel()")


async def wait_for_device(bus, device_path: str, seconds: float) -> bool:
    await call(bus, ADAPTER_PATH, "org.bluez.Adapter1", "StartDiscovery")
    log("Discovery gestartet")
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if device_path in await managed_objects(bus):
                return True
            await asyncio.sleep(1)
        return False
    finally:
        await call(bus, ADAPTER_PATH, "org.bluez.Adapter1", "StopDiscovery")
        log("Discovery beendet")


async def probe_pair(mac: str) -> int:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    device_path = f"{ADAPTER_PATH}/dev_{mac.upper().replace(':', '_')}"
    if not await wait_for_device(bus, device_path, 30):
        log("Geraet nicht gefunden — Kopplungsmodus aktiv?")
        return 1
    agent = ProbeAgent()
    bus.export(AGENT_PATH, agent)
    await call(bus, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent", "os",
               [AGENT_PATH, "KeyboardDisplay"])
    log("Agent registriert (KeyboardDisplay, nicht Standard)")
    try:
        await asyncio.wait_for(call(bus, device_path, "org.bluez.Device1", "Pair"), 90)
        log("Pair() -> OK")
        await call(bus, device_path, "org.freedesktop.DBus.Properties", "Set", "ssv",
                   ["org.bluez.Device1", "Trusted", Variant("b", True)])
        log("Trusted=true")
        await call(bus, device_path, "org.bluez.Device1", "Connect")
        log("Connect() -> OK")
        return 0
    except DBusError as exc:
        log(f"FEHLER {exc.type}: {exc.text}")
        return 1
    finally:
        try:
            await call(bus, "/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent", "o",
                       [AGENT_PATH])
        except DBusError as exc:
            log(f"UnregisterAgent: {exc.type}")
        bus.unexport(AGENT_PATH)


async def dump(anonymized: bool) -> int:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    objects = only_adapter_and_paired(await managed_objects(bus))
    if anonymized:
        objects = anonymize(objects)
    json.dump(objects, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    dump_parser = sub.add_parser("dump")
    dump_parser.add_argument("--anonymize", action="store_true")
    pair_parser = sub.add_parser("probe-pair")
    pair_parser.add_argument("mac")
    args = parser.parse_args()
    if args.command == "dump":
        return asyncio.run(dump(args.anonymize))
    return asyncio.run(probe_pair(args.mac))


if __name__ == "__main__":
    sys.exit(main())
