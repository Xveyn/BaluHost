"""Mock SMART data for dev-mode simulation.

Leaf module — lazy-imports file_service at runtime.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.system import SmartAttribute, SmartDevice, SmartSelfTest, SmartStatusResponse


def _mock_status() -> SmartStatusResponse:
    from app.core.config import settings
    from app.services import files as file_service

    now = datetime.now(tz=timezone.utc)

    # Berechne tatsächlich genutzte Bytes aus dev-storage
    try:
        actual_used_bytes = file_service.calculate_used_bytes()
    except Exception:
        actual_used_bytes = 0

    # Bei RAID1: Daten werden gespiegelt, also beide Disks zeigen gleiche Nutzung
    # Effektive Nutzung = actual_used_bytes (nicht verdoppelt)
    disk_capacity_5gb = 5 * 1024 * 1024 * 1024  # 5 GB
    disk_capacity_10gb = 10 * 1024 * 1024 * 1024  # 10 GB
    disk_capacity_20gb = 20 * 1024 * 1024 * 1024  # 20 GB

    disk_used = min(actual_used_bytes, disk_capacity_5gb)  # Cap bei Kapazität
    disk_used_percent = (disk_used / disk_capacity_5gb * 100) if disk_capacity_5gb > 0 else 0

    # Mock-Daten für Dev-Mode: Mehrere Festplatten-Konfigurationen
    # - RAID1 Pool 1: 2x5GB (md0) - Aktiver Storage
    # - RAID1 Pool 2: 2x10GB (md1) - Backup Storage
    # - RAID5 Pool: 3x20GB (md2) - Archiv Storage
    devices = [
        # === RAID1 Pool 1 (md0) - 2x5GB ===
        SmartDevice(
            name="/dev/sda",
            model="BaluHost Dev Disk 5GB (Mirror A)",
            serial="BALU-DEV-5GB-A",
            temperature=28,
            status="PASSED",
            capacity_bytes=disk_capacity_5gb,
            used_bytes=disk_used,
            used_percent=disk_used_percent,
            mount_point=None,
            raid_member_of="md0",
            last_self_test=SmartSelfTest(
                test_type="Short offline",
                status="Completed without error",
                passed=True,
                power_on_hours=1234,
            ),
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=72,
                    worst=55,
                    threshold=0,
                    raw="28",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
        SmartDevice(
            name="/dev/sdb",
            model="BaluHost Dev Disk 5GB (Mirror B)",
            serial="BALU-DEV-5GB-B",
            temperature=29,
            status="PASSED",
            capacity_bytes=disk_capacity_5gb,
            used_bytes=disk_used,
            used_percent=disk_used_percent,
            mount_point=None,
            raid_member_of="md0",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=71,
                    worst=56,
                    threshold=0,
                    raw="29",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),

        # === RAID1 Pool 2 (md1) - 2x10GB ===
        SmartDevice(
            name="/dev/sdc",
            model="BaluHost Dev Disk 10GB (Backup A)",
            serial="BALU-DEV-10GB-A",
            temperature=30,
            status="PASSED",
            capacity_bytes=disk_capacity_10gb,
            used_bytes=int(disk_capacity_10gb * 0.45),  # 45% genutzt
            used_percent=45.0,
            mount_point=None,
            raid_member_of="md1",
            last_self_test=SmartSelfTest(
                test_type="Extended offline",
                status="Completed without error",
                passed=True,
                power_on_hours=5678,
            ),
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=70,
                    worst=54,
                    threshold=0,
                    raw="30",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
        SmartDevice(
            name="/dev/sdd",
            model="BaluHost Dev Disk 10GB (Backup B)",
            serial="BALU-DEV-10GB-B",
            temperature=31,
            status="PASSED",
            capacity_bytes=disk_capacity_10gb,
            used_bytes=int(disk_capacity_10gb * 0.45),  # 45% genutzt
            used_percent=45.0,
            mount_point=None,
            raid_member_of="md1",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=69,
                    worst=53,
                    threshold=0,
                    raw="31",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),

        # === RAID5 Pool (md2) - 3x20GB ===
        SmartDevice(
            name="/dev/sde",
            model="BaluHost Dev Disk 20GB (Archive A)",
            serial="BALU-DEV-20GB-A",
            temperature=32,
            status="PASSED",
            capacity_bytes=disk_capacity_20gb,
            used_bytes=int(disk_capacity_20gb * 0.28),  # 28% genutzt
            used_percent=28.0,
            mount_point=None,
            raid_member_of="md2",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=68,
                    worst=52,
                    threshold=0,
                    raw="32",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
        SmartDevice(
            name="/dev/sdf",
            model="BaluHost Dev Disk 20GB (Archive B)",
            serial="BALU-DEV-20GB-B",
            temperature=33,
            status="PASSED",
            capacity_bytes=disk_capacity_20gb,
            used_bytes=int(disk_capacity_20gb * 0.28),  # 28% genutzt
            used_percent=28.0,
            mount_point=None,
            raid_member_of="md2",
            last_self_test=SmartSelfTest(
                test_type="Short offline",
                status="Completed: read failure",
                passed=False,
                power_on_hours=9012,
            ),
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=67,
                    worst=51,
                    threshold=0,
                    raw="33",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
        SmartDevice(
            name="/dev/sdg",
            model="BaluHost Dev Disk 20GB (Archive C)",
            serial="BALU-DEV-20GB-C",
            temperature=34,
            status="PASSED",
            capacity_bytes=disk_capacity_20gb,
            used_bytes=int(disk_capacity_20gb * 0.28),  # 28% genutzt
            used_percent=28.0,
            mount_point=None,
            raid_member_of="md2",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=66,
                    worst=50,
                    threshold=0,
                    raw="34",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
    ]
    return SmartStatusResponse(checked_at=now, devices=devices)
