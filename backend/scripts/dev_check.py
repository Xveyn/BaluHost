from __future__ import annotations

import argparse
import json
from typing import Any, Dict

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:3001/api"


def _print_section(title: str, payload: Dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, sort_keys=True))


def login(client: httpx.Client, base_url: str, username: str, password: str) -> str:
    response = client.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but no access_token returned")
    return token


def fetch_system_overview(client: httpx.Client, base_url: str) -> None:
    for endpoint, title in (
        ("/system/info", "System Info"),
        ("/system/storage", "Storage"),
        ("/system/quota", "Quota"),
        ("/system/processes", "Processes"),
        ("/system/smart/status", "SMART"),
        ("/system/raid/status", "RAID Status"),
    ):
        response = client.get(f"{base_url}{endpoint}", timeout=10)
        response.raise_for_status()
        _print_section(title, response.json())


def simulate_raid_cycle(
    client: httpx.Client,
    base_url: str,
    array: str | None,
    device: str | None,
) -> None:
    status_response = client.get(f"{base_url}/system/raid/status", timeout=10)
    status_response.raise_for_status()
    raid_status = status_response.json()
    arrays = raid_status.get("arrays", [])
    if not arrays:
        print("No RAID arrays reported; skipping simulation")
        return

    target_array = array or arrays[0]["name"]
    payload = {"array": target_array}
    if device:
        payload["device"] = device

    for endpoint, title in (
        ("/system/raid/degrade", "Simulate failure"),
        ("/system/raid/status", "Status after failure"),
        ("/system/raid/rebuild", "Start rebuild"),
        ("/system/raid/status", "Status during rebuild"),
        ("/system/raid/finalize", "Finalize rebuild"),
        ("/system/raid/status", "Status after finalize"),
    ):
        if endpoint.endswith("status"):
            response = client.get(f"{base_url}{endpoint}", timeout=10)
        else:
            response = client.post(f"{base_url}{endpoint}", json=payload, timeout=10)
        response.raise_for_status()
        _print_section(title, response.json())


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise Baluhost dev-mode backend endpoints")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (default: %(default)s)")
    parser.add_argument("--username", default="admin", help="Login username (default: %(default)s)")
    parser.add_argument("--password", default="changeme", help="Login password (default: %(default)s)")
    parser.add_argument(
        "--raid-cycle",
        action="store_true",
        help="Simulate a RAID failure/rebuild cycle (dev mode only)",
    )
    parser.add_argument("--raid-array", help="Name of the RAID array to target (default: first reported)")
    parser.add_argument("--raid-device", help="Device inside the RAID array to target")

    args = parser.parse_args()

    headers: Dict[str, str] = {}
    with httpx.Client(headers=headers) as client:
        token = login(client, args.base_url, args.username, args.password)
        client.headers["Authorization"] = f"Bearer {token}"

        fetch_system_overview(client, args.base_url)

        if args.raid_cycle:
            simulate_raid_cycle(client, args.base_url, args.raid_array, args.raid_device)


if __name__ == "__main__":
    main()
