"""LAN-IP der Box bestimmen (IPv4, privat)."""
import json
import re
import subprocess

from app.plugins.installed.local_tls.providers.base import is_private_ipv4

_IFACE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,15}$")
_TIMEOUT = 5


class AddressError(Exception):
    """LAN-IP nicht bestimmbar oder nicht privat -- kein Update."""


def current_lan_ip(interface: str | None = None, *, run=subprocess.run) -> str:
    if interface:
        if not _IFACE_RE.fullmatch(interface):
            raise AddressError("invalid interface name")
        cmd = ["ip", "-j", "-4", "addr", "show", "dev", interface]
    else:
        cmd = ["ip", "-j", "route", "get", "1.1.1.1"]
    try:
        proc = run(cmd, capture_output=True, text=True, errors="replace", timeout=_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        raise AddressError("could not determine LAN address") from None
    if proc.returncode != 0:
        raise AddressError("no route / interface found")
    try:
        data = json.loads(proc.stdout)
        if interface:
            ip = next(
                a["local"]
                for entry in data
                for a in entry.get("addr_info", [])
                if a.get("family") == "inet"
            )
        else:
            ip = data[0]["prefsrc"]
    except (ValueError, KeyError, IndexError, TypeError, StopIteration):
        raise AddressError("no IPv4 address found") from None
    if not isinstance(ip, str) or not is_private_ipv4(ip):
        raise AddressError("address is not a private IPv4 address")
    return ip
