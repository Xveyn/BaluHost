"""nginx must reach the backend from an address uvicorn trusts (#641).

uvicorn honours X-Forwarded-For only from --forwarded-allow-ips (127.0.0.1).
An upstream of `localhost:8000` may resolve to ::1. Then XFF is ignored and
request.client.host is ::1 for EVERY request, internet ones included - and
is_private_or_local_ip("::1") is True, so every LAN gate (session unlock,
Bluetooth pairing, recovery reset, game launch) would silently open, and the
per-IP rate limiter would see all clients as one.

So every upstream server must be an address on the trust list, spelled
literally - not a name the resolver may map elsewhere.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SERVICE = _REPO / "deploy" / "install" / "templates" / "baluhost-backend.service"
_NGINX_CONFIGS = sorted(
    [*(_REPO / "deploy" / "nginx").glob("*.conf"),
     *(_REPO / "deploy" / "install" / "templates").glob("*nginx*.conf")]
)
# Hand-copied nginx snippets that operators paste into their own config.
_DOCS = [
    _REPO / "docs" / "deployment" / "REVERSE_PROXY_SETUP.en.md",
    _REPO / "docs" / "deployment" / "REVERSE_PROXY_SETUP.de.md",
    _REPO / "docs" / "deployment" / "SSL_SETUP.en.md",
    _REPO / "docs" / "deployment" / "SSL_SETUP.de.md",
    _REPO / "client" / "README.md",
]


def _trusted_proxies() -> set[str]:
    # Comment lines mention the flag too ("...=127.0.0.1: trust X-Forwarded-For").
    active = "\n".join(
        line for line in _SERVICE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    match = re.search(r"--forwarded-allow-ips=(\S+)", active)
    assert match, "service template lost --forwarded-allow-ips"
    return set(match.group(1).split(","))


def _upstream_servers(text: str) -> list[str]:
    """Active `server` targets inside `upstream { }` blocks (comments ignored)."""
    servers = []
    for block in re.findall(r"^\s*upstream\s+\S+\s*\{(.*?)^\s*\}", text, re.S | re.M):
        for line in block.splitlines():
            line = line.split("#", 1)[0].strip()
            if line.startswith("server "):
                servers.append(line.split()[1].rstrip(";"))
    return servers


def test_there_are_configs_to_check():
    assert len(_NGINX_CONFIGS) >= 4, _NGINX_CONFIGS
    assert all(doc.is_file() for doc in _DOCS), [d for d in _DOCS if not d.is_file()]


@pytest.mark.parametrize("config", _NGINX_CONFIGS, ids=lambda p: p.relative_to(_REPO).as_posix())
def test_every_upstream_targets_a_trusted_proxy_address(config):
    trusted = _trusted_proxies()
    for server in _upstream_servers(config.read_text(encoding="utf-8")):
        if server.startswith("unix:"):
            continue  # no IP at all -> nothing to spoof or mis-resolve
        host = server.rsplit(":", 1)[0]
        assert host in trusted, (
            f"{config.name}: upstream {server} is not on uvicorn's "
            f"--forwarded-allow-ips {sorted(trusted)}"
        )


@pytest.mark.parametrize("doc", _DOCS, ids=lambda p: p.relative_to(_REPO).as_posix())
def test_docs_do_not_teach_a_localhost_backend_upstream(doc):
    text = doc.read_text(encoding="utf-8")
    bad = re.findall(r"(?:server|proxy_pass\s+http://)\s*localhost:8000", text)
    assert not bad, f"{doc.name} still shows {bad} - use 127.0.0.1:8000"
