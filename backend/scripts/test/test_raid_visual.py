"""
Quick visual test of RAID wizard functionality.
Shows available disks and creates a test RAID1 array if possible.
"""

import requests
import sys
import pytest

# This is a visual/manual script that expects a running server on localhost.
# Skip when running pytest to avoid failing automated test runs.
pytest.skip("visual RAID script - requires running dev server", allow_module_level=True)
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def login() -> str:
    """Login and return token."""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            data={"username": "admin", "password": "admin"},
            timeout=5
        )
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        print(f"❌ Login failed: {e}")
        print("   Make sure the server is running (python start_dev.py)")
        sys.exit(1)

def format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"

def test_wizard():
    """Main test function."""
    print_section("🧪 RAID Setup Wizard Test")
    
    # Login
    print("\n🔐 Authentifizierung...")
    token = login()
    print("✅ Login erfolgreich")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get available disks
    print_section("💾 Verfügbare Festplatten")
    response = requests.get(f"{BASE_URL}/api/system/raid/available-disks", headers=headers)
    response.raise_for_status()
    disks_data = response.json()
    
    disks = disks_data["disks"]
    free_disks = [d for d in disks if not d["in_raid"]]
    used_disks = [d for d in disks if d["in_raid"]]
    
    print(f"\n📊 Gesamt: {len(disks)} Festplatten")
    print(f"   🔵 Verfügbar: {len(free_disks)}")
    print(f"   🟢 Im RAID: {len(used_disks)}")
    
    if used_disks:
        print("\n🟢 Im RAID verwendet:")
        for disk in used_disks:
            print(f"   • {disk['name']:6s} {format_bytes(disk['size_bytes']):>8s}  {disk['model']}")
    
    if free_disks:
        print("\n🔵 Verfügbar für neue Arrays:")
        for disk in free_disks:
            partitions = ', '.join(disk['partitions']) if disk['partitions'] else 'keine'
            print(f"   • {disk['name']:6s} {format_bytes(disk['size_bytes']):>8s}  {disk['model']}")
            print(f"     Partitionen: {partitions}")
    
    # Get current RAID status
    print_section("📊 Aktuelle RAID Arrays")
    response = requests.get(f"{BASE_URL}/api/system/raid/status", headers=headers)
    response.raise_for_status()
    status = response.json()
    
    if status["arrays"]:
        for array in status["arrays"]:
            status_icon = "✅" if array["status"] == "optimal" else "⚠️"
            print(f"\n{status_icon} {array['name']} - {array['level'].upper()} ({array['status']})")
            print(f"   Kapazität: {format_bytes(array['size_bytes'])}")
            print(f"   Geräte: {', '.join(d['name'] for d in array['devices'])}")
            if array.get('resync_progress') is not None:
                print(f"   Resync: {array['resync_progress']:.1f}%")
    else:
        print("\n⚠️  Keine RAID Arrays gefunden")
    
    # Test wizard capabilities
    print_section("🛠️  RAID Wizard Funktionalität")
    
    print("\n✅ Wizard kann testen:")
    print(f"   • Disk-Auswahl: {len(free_disks)} Disks verfügbar")
    print("   • RAID-Level: RAID 0, 1, 5, 6, 10 unterstützt")
    
    if len(free_disks) >= 2:
        print("   • ✅ Kann RAID 0/1 erstellen (2+ Disks vorhanden)")
    else:
        print(f"   • ❌ RAID 0/1 nicht möglich (nur {len(free_disks)} Disk)")
    
    if len(free_disks) >= 3:
        print("   • ✅ Kann RAID 5 erstellen (3+ Disks vorhanden)")
    else:
        print(f"   • ❌ RAID 5 nicht möglich (nur {len(free_disks)} Disks)")
    
    if len(free_disks) >= 4:
        print("   • ✅ Kann RAID 6/10 erstellen (4+ Disks vorhanden)")
    else:
        print(f"   • ❌ RAID 6/10 nicht möglich (nur {len(free_disks)} Disks)")
    
    print("\n" + "="*60)
    print("🎉 Test abgeschlossen!")
    print("="*60)
    print("\n💡 Nächste Schritte:")
    print("   1. Öffne http://localhost:5173 im Browser")
    print("   2. Login mit admin/admin")
    print("   3. Navigiere zu 'RAID Control'")
    print("   4. Klicke 'Neues Array erstellen'")
    print("   5. Folge dem Wizard-Assistenten\n")

if __name__ == "__main__":
    test_wizard()
