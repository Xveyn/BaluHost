"""start_prod.py trusts X-Forwarded-For exactly like the systemd unit (#621).

Behind nginx, request.client.host is 127.0.0.1 unless uvicorn runs with
--proxy-headers; then is_private_or_local_ip() is True for every client and the
LAN gates (Bluetooth pairing, game launch, ...) let the internet through. The
unit had the flags, start_prod.py - documented as the "Production launcher" -
did not. The second test pins the two paths together so they can't drift again.
"""
import importlib.util
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
UNIT = REPO_ROOT / "deploy" / "install" / "templates" / "baluhost-backend.service"
TRUST_FLAGS = ("--proxy-headers", "--forwarded-allow-ips=127.0.0.1")


def _load_start_prod():
    spec = importlib.util.spec_from_file_location("start_prod", REPO_ROOT / "start_prod.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_backend_command_trusts_only_the_local_proxy():
    cmd = _load_start_prod().build_backend_cmd("python")

    for flag in TRUST_FLAGS:
        assert flag in cmd
    assert cmd[:4] == ["python", "-m", "uvicorn", "app.main:app"]


def test_start_prod_and_unit_use_the_same_trust_flags():
    exec_start = re.search(r"^ExecStart=.*?(?<!\\)$", UNIT.read_text(encoding="utf-8"), re.M | re.S).group(0)
    unit_flags = {f for f in re.findall(r"--[\w-]+(?:=\S+)?", exec_start) if "proxy" in f or "forwarded" in f}
    prod_flags = {f for f in _load_start_prod().build_backend_cmd("python") if "proxy" in f or "forwarded" in f}

    assert unit_flags == set(TRUST_FLAGS)
    assert prod_flags == unit_flags
