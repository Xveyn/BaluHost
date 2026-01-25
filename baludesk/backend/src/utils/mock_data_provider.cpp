#include "mock_data_provider.h"
#include "logger.h"

namespace baludesk {

SystemInfo MockDataProvider::getMockSystemInfo() {
    Logger::debug("Providing mock system info (dev-mode)");

    SystemInfo info;

    // Mock CPU (8 cores, 45% usage, 3.6 GHz)
    info.cpu.usage = 45.5;
    info.cpu.cores = 8;
    info.cpu.frequency = 3600;  // MHz

    // Mock RAM (16GB total, 8GB used, 8GB available)
    info.memory.total = 17179869184;      // 16 GB
    info.memory.used = 8589934592;        // 8 GB
    info.memory.available = 8589934592;   // 8 GB

    // Mock Disk (1TB total, 500GB used, 500GB available)
    info.disk.total = 1099511627776;      // 1 TB
    info.disk.used = 549755813888;        // 500 GB
    info.disk.available = 549755813888;   // 500 GB

    // Mock Uptime (5 days for system, 3 days for server)
    info.uptime = 432000;        // 5 days in seconds
    info.serverUptime = 259200;  // 3 days in seconds

    return info;
}

RaidStatus MockDataProvider::getMockRaidStatus() {
    Logger::debug("Providing mock RAID status (dev-mode)");

    RaidStatus status;
    status.dev_mode = true;

    // RAID1 Array - Optimal
    RaidArray raid1;
    raid1.name = "md0";
    raid1.level = "RAID1";
    raid1.status = "optimal";
    raid1.size_bytes = 1099511627776;  // 1 TB
    raid1.resync_progress = 0.0;

    RaidDevice dev1;
    dev1.name = "sda1";
    dev1.state = "active";

    RaidDevice dev2;
    dev2.name = "sdb1";
    dev2.state = "active";

    raid1.devices.push_back(dev1);
    raid1.devices.push_back(dev2);

    status.arrays.push_back(raid1);

    // RAID5 Array - Rebuilding
    RaidArray raid5;
    raid5.name = "md1";
    raid5.level = "RAID5";
    raid5.status = "rebuilding";
    raid5.size_bytes = 3298534883328;  // 3 TB
    raid5.resync_progress = 67.5;

    RaidDevice dev3;
    dev3.name = "sdc1";
    dev3.state = "active";

    RaidDevice dev4;
    dev4.name = "sdd1";
    dev4.state = "active";

    RaidDevice dev5;
    dev5.name = "sde1";
    dev5.state = "active";

    RaidDevice dev6;
    dev6.name = "sdf1";
    dev6.state = "spare";

    raid5.devices.push_back(dev3);
    raid5.devices.push_back(dev4);
    raid5.devices.push_back(dev5);
    raid5.devices.push_back(dev6);

    status.arrays.push_back(raid5);

    return status;
}

PowerMonitoring MockDataProvider::getMockPowerMonitoring() {
    Logger::debug("Providing mock power monitoring data (dev-mode)");

    PowerMonitoring power;

    // Mock current power consumption (87.3W)
    power.currentPower = 87.3;

    // Mock energy consumed today (1.85 kWh)
    power.energyToday = 1.85;

    // Mock trend delta (-5.2W = decreasing power consumption)
    power.trendDelta = -5.2;

    // Mock device count (3 devices monitored)
    power.deviceCount = 3;

    // Mock max power capacity (150W for progress bar calculation)
    power.maxPower = 150.0;

    return power;
}

} // namespace baludesk
