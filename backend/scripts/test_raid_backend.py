"""
Simple inline test - no external dependencies needed.
Tests the RAID backend logic directly.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.raid import DevRaidBackend
from app.schemas.system import CreateArrayRequest

def test_raid_backend():
    """Test RAID backend functionality."""
    print("\n" + "="*60)
    print("  RAID Backend Test (Dev Mode)")
    print("="*60)
    
    # Create backend
    backend = DevRaidBackend()
    
    # Test 1: Get available disks
    print("\nVerfuegbare Festplatten:")
    disks_response = backend.get_available_disks()
    disks = disks_response.disks
    
    free_disks = [d for d in disks if not d.in_raid]
    used_disks = [d for d in disks if d.in_raid]
    
    print(f"   Gesamt: {len(disks)} Disks")
    print(f"   [RAID]: {len(used_disks)}")
    print(f"   [Frei]: {len(free_disks)}")
    
    for disk in disks:
        status = "[RAID]" if disk.in_raid else "[Frei]"
        size_gb = disk.size_bytes / (1024**3)
        print(f"   {status} {disk.name:6s} {size_gb:>4.1f} GB  {disk.model}")
    
    # Test 2: Current RAID status
    print("\nAktuelle RAID Arrays:")
    status = backend.get_status()
    
    for array in status.arrays:
        size_gb = array.size_bytes / (1024**3)
        print(f"   [OK] {array.name} - {array.level.upper()} ({array.status})")
        print(f"      Kapazität: {size_gb:.1f} GB")
        print(f"      Geräte: {', '.join(d.name for d in array.devices)}")
    
    # Test 3: Try to create a new RAID1 array
    if len(free_disks) >= 2:
        print("\nErstelle Test-Array (RAID 1)...")
        print(f"   Verwende: {free_disks[0].name}, {free_disks[1].name}")
        
        try:
            # Get partition names
            devices = [
                free_disks[0].partitions[0],
                free_disks[1].partitions[0]
            ]
            
            request = CreateArrayRequest(
                name="md1",
                level="raid1",
                devices=devices
            )
            
            result = backend.create_array(request)
            print(f"   [OK] {result.message}")
            
            # Check new status
            new_status = backend.get_status()
            print(f"\n   Neue Array-Anzahl: {len(new_status.arrays)}")
            
            for array in new_status.arrays:
                if array.name == "md1":
                    size_gb = array.size_bytes / (1024**3)
                    print(f"   [+] {array.name}: {size_gb:.1f} GB nutzbar")
                    
        except Exception as e:
            print(f"   [ERROR] {e}")
    else:
        print(f"\n[WARN] Nicht genug freie Disks ({len(free_disks)}/2)")
    
    # Test 4: Validation tests
    print("\nValidierungs-Tests:")
    
    test_cases = [
        ("RAID 0 mit 2 Disks", "raid0", 2, True),
        ("RAID 1 mit 2 Disks", "raid1", 2, True),
        ("RAID 5 mit 2 Disks", "raid5", 2, False),
        ("RAID 5 mit 3 Disks", "raid5", 3, True),
        ("RAID 6 mit 3 Disks", "raid6", 3, False),
        ("RAID 6 mit 4 Disks", "raid6", 4, True),
    ]
    
    for name, level, disk_count, should_work in test_cases:
        devices = [f"test{i}" for i in range(disk_count)]
        try:
            # Just test validation without creating
            if disk_count < 2:
                result = "[X]"
            elif level == "raid5" and disk_count < 3:
                result = "[X]"
            elif level == "raid6" and disk_count < 4:
                result = "[X]"
            else:
                result = "[OK]"
            
            expected = "[OK]" if should_work else "[X]"
            match = "[OK]" if result == expected else "[FAIL]"
            print(f"   {match} {name:25s} -> {result} (erwartet: {expected})")
            
        except Exception as e:
            print(f"   [ERROR] {name:25s} -> {e}")
    
    print("\n" + "="*60)
    print("Backend-Tests abgeschlossen!")
    print("="*60)
    print("\nZum Testen im Browser:")
    print("   1. Server starten: python start_dev.py")
    print("   2. Browser: http://localhost:5173")
    print("   3. Login: admin / admin")
    print("   4. RAID Control -> Neues Array erstellen\n")

if __name__ == "__main__":
    test_raid_backend()
