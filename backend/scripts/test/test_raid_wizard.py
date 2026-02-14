"""Test script for RAID setup wizard functionality."""

import requests
import json

BASE_URL = "http://localhost:8000"

def login():
    """Login and get token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "admin", "password": "admin"}
    )
    response.raise_for_status()
    data = response.json()
    return data["access_token"]

def get_raid_status(token):
    """Get current RAID status."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/api/system/raid/status", headers=headers)
    response.raise_for_status()
    return response.json()

def get_available_disks(token):
    """Get available disks."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/api/system/raid/available-disks", headers=headers)
    response.raise_for_status()
    return response.json()

def create_raid_array(token, name, level, devices):
    """Create a new RAID array."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": name,
        "level": level,
        "devices": devices
    }
    response = requests.post(
        f"{BASE_URL}/api/system/raid/create-array",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    return response.json()

def main():
    print("🔐 Login...")
    token = login()
    print("✅ Erfolgreich eingeloggt\n")

    print("📊 Aktueller RAID-Status:")
    status = get_raid_status(token)
    print(f"Anzahl Arrays: {len(status['arrays'])}")
    for array in status["arrays"]:
        print(f"  - {array['name']}: {array['level']} ({array['status']})")
        print(f"    Geräte: {', '.join(d['name'] for d in array['devices'])}")
    print()

    print("💾 Verfügbare Festplatten:")
    disks_response = get_available_disks(token)
    disks = disks_response["disks"]
    print(f"Gefunden: {len(disks)} Festplatten")
    for disk in disks:
        status_text = "🟢 In RAID" if disk["in_raid"] else "🔵 Verfügbar"
        print(f"  {status_text} {disk['name']}: {disk['model']}")
    print()

    # Finde freie Disks für neues Array
    free_disks = [d for d in disks if not d["in_raid"]]
    if len(free_disks) >= 2:
        print(f"🛠️  Erstelle neues RAID1 Array mit {free_disks[0]['name']} und {free_disks[1]['name']}...")
        # Konvertiere zu Partition-Namen
        devices = [
            free_disks[0]["partitions"][0] if free_disks[0]["partitions"] else f"{free_disks[0]['name']}1",
            free_disks[1]["partitions"][0] if free_disks[1]["partitions"] else f"{free_disks[1]['name']}1",
        ]
        
        result = create_raid_array(token, "md1", "raid1", devices)
        print(f"✅ {result['message']}\n")

        print("📊 Neuer RAID-Status:")
        status = get_raid_status(token)
        print(f"Anzahl Arrays: {len(status['arrays'])}")
        for array in status["arrays"]:
            print(f"  - {array['name']}: {array['level']} ({array['status']})")
            print(f"    Geräte: {', '.join(d['name'] for d in array['devices'])}")
            # Berechne Größe in GB
            size_gb = array['size_bytes'] / (1024 ** 3)
            print(f"    Kapazität: {size_gb:.2f} GB")
    else:
        print(f"⚠️  Nicht genug freie Festplatten ({len(free_disks)}/2 verfügbar)")
        print("   Tipp: Lösche ein bestehendes Array oder nutze die UI zum Testen")

if __name__ == "__main__":
    main()
